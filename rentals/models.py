import calendar
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from listings.models import Product
from rentals.state_machine import (
    ALLOWED_TRANSITIONS,
    TransitionError,
    get_actor_role,
    role_matches,
)

DURATION_UNIT_CHOICES = [
    ('day', _('Day')),
    ('week', _('Week')),
    ('month', _('Month')),
]

PURPOSE_CHOICES = [
    ('event', 'Event/Party'),
    ('personal', 'Personal Use'),
    ('professional', 'Professional Use'),
    ('other', 'Other'),
]

STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('accepted', 'Accepted'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ('rejected', 'Rejected'),
    ('cancelled', 'Cancelled'),
]


def compute_end_date(start_date: date, duration: int, duration_unit: str) -> date:
    """Compute end_date from start_date + duration in the given unit."""
    if duration_unit == 'day':
        return start_date + timedelta(days=duration)
    if duration_unit == 'week':
        return start_date + timedelta(weeks=duration)
    if duration_unit == 'month':
        month = start_date.month + duration
        year = start_date.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = min(start_date.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    raise ValueError(f'Unknown duration_unit: {duration_unit}')


class Rental(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='rentals')
    # owner is denormalized at create time so it survives product owner changes
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='rentals_as_owner',
    )
    renter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='rentals_as_renter',
    )
    start_date = models.DateField()
    end_date = models.DateField()
    duration = models.PositiveIntegerField()
    duration_unit = models.CharField(max_length=10, choices=DURATION_UNIT_CHOICES)

    # Pricing snapshot — frozen at request time, never recomputed (§4.3)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    base_cost = models.DecimalField(max_digits=10, decimal_places=2)
    service_fee = models.DecimalField(max_digits=10, decimal_places=2)
    owner_payout = models.DecimalField(max_digits=10, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2)

    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True
    )
    status_history = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Rental')
        verbose_name_plural = _('Rentals')
        indexes = [
            # Overlap guard, blocked-dates, has_blocking_rentals — one index covers all
            models.Index(
                fields=['product', 'status', 'start_date', 'end_date'],
                name='rental_overlap_idx',
            ),
            # Duplicate-request guard + my-rentals scoping
            models.Index(fields=['renter', 'status'], name='rental_renter_status_idx'),
            models.Index(fields=['owner', 'status'], name='rental_owner_status_idx'),
        ]

    def __str__(self):
        return f'{self.product} — {self.renter} ({self.status})'

    # ------------------------------------------------------------------
    # Public API: the ONLY way to change status (§4.2)
    # ------------------------------------------------------------------

    def transition(self, new_status, actor, note=''):
        """
        Validate and apply a status transition.
        Raises TransitionError if the transition is not allowed.
        Every transition runs in an atomic block with the rental row locked and
        its status re-read — a stale in-memory instance (e.g. two concurrent
        requests for the same rental) cannot apply a transition twice or bypass
        the matrix. For pending→accepted the product row is locked first to
        serialize concurrent accepts across rentals (§4.4).
        """
        with transaction.atomic():
            if self.status == 'pending' and new_status == 'accepted':
                # Lock the product row to serialize concurrent accepts (§4.4).
                # Lock order is always product → rental; no path locks the
                # reverse, so this cannot deadlock.
                Product.objects.select_for_update().get(pk=self.product_id)

            # Re-read own status under lock: a concurrent transition may have
            # already moved this rental while we validated against stale state
            current_status = (
                Rental.objects.select_for_update()
                .values_list('status', flat=True)
                .get(pk=self.pk)
            )
            if current_status != self.status:
                raise TransitionError(
                    f"Cannot transition '{current_status}' → '{new_status}': "
                    f"rental was modified by a concurrent request."
                )

            allowed = ALLOWED_TRANSITIONS.get(self.status, {})
            if new_status not in allowed:
                raise TransitionError(
                    f"Cannot transition '{self.status}' → '{new_status}'."
                )

            actor_role = get_actor_role(self, actor)
            if not role_matches(actor_role, allowed[new_status]):
                raise TransitionError(
                    f"Role '{actor_role}' cannot perform '{self.status}' → '{new_status}'."
                )

            if self.status == 'pending' and new_status == 'accepted':
                self._guard_accept()
            else:
                self._run_guard(new_status, actor)
            self._apply(new_status, actor, note)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply(self, new_status, actor, note):
        """Set status, append history entry, save."""
        self.status = new_status
        self.status_history = list(self.status_history) + [{
            'status': new_status,
            'timestamp': timezone.now().isoformat(),
            'actor_id': str(actor.pk) if actor else None,
            'note': note,
        }]
        self.save(update_fields=['status', 'status_history', 'updated_at'])

        if new_status == 'completed':
            # Increment rental_count on the product using F() to avoid races
            from django.db.models import F
            Product.objects.filter(pk=self.product_id).update(
                rental_count=F('rental_count') + 1
            )

    def _run_guard(self, new_status, actor):
        if new_status == 'cancelled' and self.status == 'accepted':
            self._guard_cancel_accepted(actor)
        elif new_status == 'completed':
            self._guard_complete()

    def _guard_accept(self):
        """
        Re-check for overlapping accepted/in_progress rentals (race-safe, runs
        inside select_for_update atomic). Auto-reject overlapping pending requests.
        """
        overlap_qs = Rental.objects.filter(
            product_id=self.product_id,
            status__in=['accepted', 'in_progress'],
        ).exclude(pk=self.pk).filter(
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        )
        if overlap_qs.exists():
            raise TransitionError('These dates are already booked by another rental.')

        # Auto-reject other pending rentals that overlap with these dates
        now = timezone.now()
        to_reject = []
        for other in Rental.objects.filter(
            product_id=self.product_id,
            status='pending',
        ).exclude(pk=self.pk).filter(
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ):
            other.status = 'rejected'
            other.status_history = list(other.status_history) + [{
                'status': 'rejected',
                'timestamp': now.isoformat(),
                'actor_id': None,
                'note': 'Auto-rejected: dates were booked',
            }]
            # bulk_update skips auto_now — set updated_at by hand
            other.updated_at = now
            to_reject.append(other)
        if to_reject:
            Rental.objects.bulk_update(
                to_reject, ['status', 'status_history', 'updated_at']
            )

    def _guard_cancel_accepted(self, actor):
        """Renter can only cancel an accepted rental if it hasn't started yet (§4.4)."""
        actor_role = get_actor_role(self, actor)
        if actor_role == 'renter' and self.start_date <= date.today():
            raise TransitionError(
                'Cannot cancel: rental start date has already passed.'
            )

    def _guard_complete(self):
        """
        Block completion until all required PaymentRecords exist (§5.3).
        Raises TransitionError with a specific message for each missing piece.
        """
        records = list(self.payment_records.all())

        def total(record_type):
            return sum(
                (r.amount for r in records if r.record_type == record_type),
                Decimal('0'),
            )

        rent_collected = total('rent_collected')
        if rent_collected < self.base_cost:
            raise TransitionError(
                f'Missing: rent_collected record ≥ {self.base_cost} '
                f'(recorded: {rent_collected}).'
            )

        if self.security_deposit > 0:
            deposit_collected = total('deposit_collected')
            if deposit_collected <= 0:
                raise TransitionError(
                    f'Missing: deposit_collected record '
                    f'(deposit is {self.security_deposit}).'
                )
            settled = total('deposit_returned') + total('deposit_withheld')
            if settled != deposit_collected:
                raise TransitionError(
                    f'Deposit settlement incomplete: collected {deposit_collected}, '
                    f'returned+withheld {settled} (must be equal).'
                )

        if total('owner_payout') <= 0:
            raise TransitionError('Missing: owner_payout record.')


class RentalPhoto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rental = models.ForeignKey(Rental, on_delete=models.CASCADE, related_name='photos')
    photo = models.ImageField(
        upload_to='rental_photos/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])],
    )
    photo_type = models.CharField(
        max_length=20,
        choices=[('pre_rental', 'Pre-Rental'), ('post_rental', 'Post-Rental')],
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='rental_photos_uploaded',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = _('Rental Photo')
        verbose_name_plural = _('Rental Photos')

    def __str__(self):
        return f'{self.photo_type} — Rental {self.rental_id}'


class PaymentRecord(models.Model):
    RECORD_TYPES = [
        ('rent_collected', 'Rent collected from renter'),
        ('deposit_collected', 'Security deposit collected from renter'),
        ('deposit_returned', 'Security deposit returned to renter'),
        ('deposit_withheld', 'Deposit (partially) withheld for damage'),
        ('owner_payout', 'Payout to owner (after service fee)'),
        ('refund', 'Refund to renter'),
    ]
    METHODS = [
        ('cash', 'Cash'),
        ('bkash', 'bKash'),
        ('nagad', 'Nagad'),
        ('bank', 'Bank transfer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rental = models.ForeignKey(
        Rental, on_delete=models.PROTECT, related_name='payment_records'
    )
    record_type = models.CharField(max_length=30, choices=RECORD_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=10, choices=METHODS)
    reference = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='payment_records_entered',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = _('Payment Record')
        verbose_name_plural = _('Payment Records')

    def __str__(self):
        return f'{self.record_type} {self.amount} — Rental {self.rental_id}'
