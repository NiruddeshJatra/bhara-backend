"""
Four required test groups:
  1. Exhaustive transition matrix (§4.2)
  2. Double-booking + concurrent accept guard (§4.4)
  3. §5.3 completion guard — each missing piece with clear error
  4. Pricing snapshot immutability
Plus view integration tests for the full API lifecycle.
"""
import itertools
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework_simplejwt.tokens import RefreshToken

from listings.tests.factories import PricingTierFactory, ProductFactory
from rentals.models import Rental, RentalPhoto, compute_end_date
from rentals.state_machine import (
    ALLOWED_TRANSITIONS,
    ALL_STATUSES,
    TransitionError,
    get_actor_role,
    role_matches,
)
from rentals.tests.factories import PaymentRecordFactory, RentalFactory, RenterFactory
from users.tests.factories import VerifiedUserFactory


def auth_headers(user):
    refresh = RefreshToken.for_user(user)
    return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}


# ---------------------------------------------------------------------------
# Helper: build the complete expected allow/deny truth table from §4.2
# ---------------------------------------------------------------------------

ALL_ROLES = ['owner', 'renter', 'staff']

EXPECTED_ALLOWED = {
    ('pending', 'accepted', 'owner'),
    ('pending', 'rejected', 'owner'),
    ('pending', 'cancelled', 'renter'),
    ('pending', 'cancelled', 'staff'),
    ('accepted', 'in_progress', 'staff'),
    ('accepted', 'cancelled', 'renter'),
    ('accepted', 'cancelled', 'staff'),
    ('in_progress', 'completed', 'staff'),
}


# ===========================================================================
# 1. Exhaustive transition matrix (§4.2)
# ===========================================================================

class TestTransitionMatrix(TestCase):
    """
    Tests every (from_status, to_status, actor_role) combination against the
    ALLOWED_TRANSITIONS table using only state_machine.py logic (no guards).
    This validates the table and role-matching in isolation.
    """

    def _can_transition(self, from_s, to_s, role):
        allowed = ALLOWED_TRANSITIONS.get(from_s, {})
        if to_s not in allowed:
            return False
        return role_matches(role, allowed[to_s])

    def test_all_combinations(self):
        errors = []
        for from_s, to_s, role in itertools.product(ALL_STATUSES, ALL_STATUSES, ALL_ROLES):
            expected = (from_s, to_s, role) in EXPECTED_ALLOWED
            actual = self._can_transition(from_s, to_s, role)
            if actual != expected:
                verdict = 'ALLOW' if expected else 'DENY'
                errors.append(
                    f'  ({from_s!r}, {to_s!r}, {role!r}): expected {verdict}, got {"ALLOW" if actual else "DENY"}'
                )
        if errors:
            self.fail('Transition matrix mismatch:\n' + '\n'.join(errors))

    def test_terminal_states_have_no_outgoing_transitions(self):
        for terminal in ('completed', 'rejected', 'cancelled'):
            self.assertEqual(
                ALLOWED_TRANSITIONS[terminal],
                {},
                f'{terminal} should have no allowed transitions',
            )

    def test_get_actor_role_owner(self):
        owner = VerifiedUserFactory()
        rental = RentalFactory(owner=owner)
        self.assertEqual(get_actor_role(rental, owner), 'owner')

    def test_get_actor_role_renter(self):
        rental = RentalFactory()
        self.assertEqual(get_actor_role(rental, rental.renter), 'renter')

    def test_get_actor_role_staff(self):
        rental = RentalFactory()
        staff = VerifiedUserFactory(is_staff=True)
        self.assertEqual(get_actor_role(rental, staff), 'staff')

    def test_get_actor_role_stranger(self):
        rental = RentalFactory()
        stranger = VerifiedUserFactory()
        self.assertIsNone(get_actor_role(rental, stranger))

    def test_role_matches_renter_or_staff_allows_renter(self):
        self.assertTrue(role_matches('renter', 'renter_or_staff'))

    def test_role_matches_renter_or_staff_allows_staff(self):
        self.assertTrue(role_matches('staff', 'renter_or_staff'))

    def test_role_matches_renter_or_staff_denies_owner(self):
        self.assertFalse(role_matches('owner', 'renter_or_staff'))


# ===========================================================================
# 2. Double-booking + concurrent accept guard (§4.4)
# ===========================================================================

class TestDoubleBooking(TestCase):

    def setUp(self):
        self.product = ProductFactory()
        self.owner = self.product.owner
        PricingTierFactory(product=self.product, duration_unit='day', price=500, max_period=30)
        self.start = date.today() + timedelta(days=10)
        self.end = self.start + timedelta(days=3)

    def _make_pending(self, **kwargs):
        return RentalFactory(
            product=self.product,
            owner=self.owner,
            start_date=self.start,
            end_date=self.end,
            status='pending',
            **kwargs,
        )

    def test_accept_auto_rejects_overlapping_pending(self):
        r1 = self._make_pending()
        r2 = self._make_pending(renter=RenterFactory())

        r1.transition('accepted', self.owner)

        r2.refresh_from_db()
        self.assertEqual(r2.status, 'rejected')
        last_note = r2.status_history[-1]['note']
        self.assertEqual(last_note, 'Auto-rejected: dates were booked')

    def test_accept_does_not_reject_non_overlapping_pending(self):
        r1 = self._make_pending()
        # Non-overlapping rental: starts after r1 ends
        r2 = RentalFactory(
            product=self.product,
            owner=self.owner,
            start_date=self.end + timedelta(days=1),
            end_date=self.end + timedelta(days=4),
            status='pending',
            renter=RenterFactory(),
        )

        r1.transition('accepted', self.owner)

        r2.refresh_from_db()
        self.assertEqual(r2.status, 'pending')

    def test_cannot_accept_when_dates_already_accepted(self):
        """Simulate the race: r1 is already accepted when r2 tries."""
        r1 = self._make_pending()
        r1.status = 'accepted'
        r1.save()

        r2 = self._make_pending(renter=RenterFactory())

        with self.assertRaises(TransitionError) as ctx:
            r2.transition('accepted', self.owner)
        self.assertIn('already booked', str(ctx.exception))

    def test_cannot_accept_when_dates_overlap_in_progress(self):
        r1 = self._make_pending()
        r1.status = 'in_progress'
        r1.save()

        r2 = self._make_pending(renter=RenterFactory())

        with self.assertRaises(TransitionError):
            r2.transition('accepted', self.owner)

    def test_partial_overlap_still_blocks(self):
        """A rental that starts during an accepted window is blocked."""
        r1 = self._make_pending()
        r1.status = 'accepted'
        r1.save()

        r2 = RentalFactory(
            product=self.product,
            owner=self.owner,
            start_date=self.start + timedelta(days=1),  # starts inside r1
            end_date=self.end + timedelta(days=2),
            status='pending',
            renter=RenterFactory(),
        )

        with self.assertRaises(TransitionError):
            r2.transition('accepted', self.owner)

    def test_accepted_cancelled_by_renter_before_start(self):
        rental = self._make_pending()
        rental.transition('accepted', self.owner)
        rental.refresh_from_db()
        # start_date is in the future, so renter can cancel
        rental.transition('cancelled', rental.renter)
        self.assertEqual(rental.status, 'cancelled')

    def test_accepted_cannot_be_cancelled_by_renter_after_start(self):
        rental = RentalFactory(
            product=self.product,
            owner=self.owner,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today() + timedelta(days=2),
            status='accepted',
        )
        with self.assertRaises(TransitionError) as ctx:
            rental.transition('cancelled', rental.renter)
        self.assertIn('start date has already passed', str(ctx.exception))

    def test_staff_can_cancel_accepted_regardless_of_start(self):
        staff = VerifiedUserFactory(is_staff=True)
        rental = RentalFactory(
            product=self.product,
            owner=self.owner,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today() + timedelta(days=2),
            status='accepted',
        )
        rental.transition('cancelled', staff)
        self.assertEqual(rental.status, 'cancelled')


# ===========================================================================
# 3. §5.3 Completion guard — each missing piece with clear error
# ===========================================================================

class TestCompletionGuard(TestCase):

    def setUp(self):
        self.staff = VerifiedUserFactory(is_staff=True)
        self.rental = RentalFactory(
            status='in_progress',
            base_cost=Decimal('1500.00'),
            security_deposit=Decimal('500.00'),
            owner_payout=Decimal('1200.00'),
        )

    def _add(self, record_type, amount):
        return PaymentRecordFactory(
            rental=self.rental,
            record_type=record_type,
            amount=Decimal(str(amount)),
            recorded_by=self.staff,
        )

    def test_blocked_no_payment_records(self):
        with self.assertRaises(TransitionError) as ctx:
            self.rental.transition('completed', self.staff)
        self.assertIn('rent_collected', str(ctx.exception))

    def test_blocked_rent_collected_below_base_cost(self):
        self._add('rent_collected', '500.00')  # only partial
        with self.assertRaises(TransitionError) as ctx:
            self.rental.transition('completed', self.staff)
        self.assertIn('rent_collected', str(ctx.exception))

    def test_blocked_missing_deposit_collected(self):
        self._add('rent_collected', '1500.00')
        self._add('owner_payout', '1200.00')
        # deposit > 0 but no deposit_collected record
        with self.assertRaises(TransitionError) as ctx:
            self.rental.transition('completed', self.staff)
        self.assertIn('deposit_collected', str(ctx.exception))

    def test_blocked_deposit_settlement_incomplete(self):
        self._add('rent_collected', '1500.00')
        self._add('deposit_collected', '500.00')
        self._add('deposit_returned', '200.00')  # only partial — 200 != 500
        self._add('owner_payout', '1200.00')
        with self.assertRaises(TransitionError) as ctx:
            self.rental.transition('completed', self.staff)
        self.assertIn('settlement incomplete', str(ctx.exception))

    def test_blocked_missing_owner_payout(self):
        self._add('rent_collected', '1500.00')
        self._add('deposit_collected', '500.00')
        self._add('deposit_returned', '500.00')
        with self.assertRaises(TransitionError) as ctx:
            self.rental.transition('completed', self.staff)
        self.assertIn('owner_payout', str(ctx.exception))

    def test_completes_with_all_records_present(self):
        self._add('rent_collected', '1500.00')
        self._add('deposit_collected', '500.00')
        self._add('deposit_returned', '300.00')
        self._add('deposit_withheld', '200.00')  # 300+200 == 500 ✓
        self._add('owner_payout', '1200.00')

        self.rental.transition('completed', self.staff)
        self.assertEqual(self.rental.status, 'completed')

    def test_completes_no_deposit_if_deposit_zero(self):
        """If security_deposit == 0 the deposit records are not required."""
        rental = RentalFactory(
            status='in_progress',
            security_deposit=Decimal('0.00'),
            base_cost=Decimal('1500.00'),
            owner_payout=Decimal('1200.00'),
        )
        PaymentRecordFactory(
            rental=rental, record_type='rent_collected',
            amount=Decimal('1500.00'), recorded_by=self.staff,
        )
        PaymentRecordFactory(
            rental=rental, record_type='owner_payout',
            amount=Decimal('1200.00'), recorded_by=self.staff,
        )
        rental.transition('completed', self.staff)
        self.assertEqual(rental.status, 'completed')

    def test_completion_increments_rental_count(self):
        from listings.models import Product
        self._add('rent_collected', '1500.00')
        self._add('deposit_collected', '500.00')
        self._add('deposit_returned', '500.00')
        self._add('owner_payout', '1200.00')

        before = Product.objects.get(pk=self.rental.product_id).rental_count
        self.rental.transition('completed', self.staff)
        after = Product.objects.get(pk=self.rental.product_id).rental_count
        self.assertEqual(after, before + 1)


# ===========================================================================
# 4. Pricing snapshot immutability
# ===========================================================================

class TestPricingSnapshotImmutability(TestCase):

    def test_changing_tier_price_does_not_affect_rental(self):
        product = ProductFactory()
        tier = PricingTierFactory(product=product, price=500, duration_unit='day', max_period=30)

        start = date.today() + timedelta(days=5)
        end = start + timedelta(days=3)
        rental = RentalFactory(
            product=product,
            owner=product.owner,
            start_date=start,
            end_date=end,
            duration=3,
            duration_unit='day',
            unit_price=Decimal('500.00'),
            base_cost=Decimal('1500.00'),
            service_fee=Decimal('300.00'),
            owner_payout=Decimal('1200.00'),
        )

        # Change the tier price after the rental was created
        tier.price = 9999
        tier.save()

        rental.refresh_from_db()
        self.assertEqual(rental.unit_price, Decimal('500.00'))
        self.assertEqual(rental.base_cost, Decimal('1500.00'))
        self.assertEqual(rental.service_fee, Decimal('300.00'))
        self.assertEqual(rental.owner_payout, Decimal('1200.00'))

    def test_deleting_tier_does_not_affect_existing_rental(self):
        product = ProductFactory()
        tier = PricingTierFactory(product=product, price=800, duration_unit='week', max_period=4)

        start = date.today() + timedelta(days=5)
        end = start + timedelta(weeks=1)
        rental = RentalFactory(
            product=product,
            owner=product.owner,
            start_date=start,
            end_date=end,
            duration=1,
            duration_unit='week',
            unit_price=Decimal('800.00'),
            base_cost=Decimal('800.00'),
            service_fee=Decimal('160.00'),
            owner_payout=Decimal('640.00'),
        )

        tier.delete()

        rental.refresh_from_db()
        self.assertEqual(rental.unit_price, Decimal('800.00'))
        self.assertEqual(rental.base_cost, Decimal('800.00'))


# ===========================================================================
# 5. API integration — full lifecycle (create, accept, reject, cancel, photos)
# ===========================================================================

class TestRentalAPICreate(TestCase):

    def setUp(self):
        self.renter = VerifiedUserFactory()
        self.product = ProductFactory()
        PricingTierFactory(
            product=self.product, duration_unit='day', price=500, max_period=30
        )

    def test_create_rental_success(self):
        response = self.client.post(
            '/api/rentals/',
            {
                'product': str(self.product.pk),
                'start_date': (date.today() + timedelta(days=5)).isoformat(),
                'duration': 3,
                'duration_unit': 'day',
                'purpose': 'personal',
            },
            content_type='application/json',
            **auth_headers(self.renter),
        )
        self.assertEqual(response.status_code, 201, response.json())
        data = response.json()['data']
        self.assertEqual(data['status'], 'pending')
        self.assertEqual(Decimal(data['base_cost']), Decimal('1500.00'))
        self.assertEqual(Decimal(data['service_fee']), Decimal('300.00'))
        self.assertEqual(Decimal(data['owner_payout']), Decimal('1200.00'))

    def test_create_fails_unauthenticated(self):
        response = self.client.post('/api/rentals/', {}, content_type='application/json')
        self.assertIn(response.status_code, (401, 403))

    def test_create_fails_renter_is_owner(self):
        response = self.client.post(
            '/api/rentals/',
            {
                'product': str(self.product.pk),
                'start_date': (date.today() + timedelta(days=5)).isoformat(),
                'duration': 3,
                'duration_unit': 'day',
                'purpose': 'personal',
            },
            content_type='application/json',
            **auth_headers(self.product.owner),
        )
        self.assertEqual(response.status_code, 400)

    def test_create_fails_past_start_date(self):
        response = self.client.post(
            '/api/rentals/',
            {
                'product': str(self.product.pk),
                'start_date': (date.today() - timedelta(days=1)).isoformat(),
                'duration': 3,
                'duration_unit': 'day',
                'purpose': 'personal',
            },
            content_type='application/json',
            **auth_headers(self.renter),
        )
        self.assertEqual(response.status_code, 400)

    def test_create_fails_exceeds_max_period(self):
        response = self.client.post(
            '/api/rentals/',
            {
                'product': str(self.product.pk),
                'start_date': (date.today() + timedelta(days=5)).isoformat(),
                'duration': 999,
                'duration_unit': 'day',
                'purpose': 'personal',
            },
            content_type='application/json',
            **auth_headers(self.renter),
        )
        self.assertEqual(response.status_code, 400)

    def test_create_fails_no_tier_for_unit(self):
        response = self.client.post(
            '/api/rentals/',
            {
                'product': str(self.product.pk),
                'start_date': (date.today() + timedelta(days=5)).isoformat(),
                'duration': 2,
                'duration_unit': 'week',
                'purpose': 'personal',
            },
            content_type='application/json',
            **auth_headers(self.renter),
        )
        self.assertEqual(response.status_code, 400)

    def test_duplicate_request_rejected(self):
        start = date.today() + timedelta(days=5)
        payload = {
            'product': str(self.product.pk),
            'start_date': start.isoformat(),
            'duration': 3,
            'duration_unit': 'day',
            'purpose': 'personal',
        }
        r1 = self.client.post(
            '/api/rentals/', payload,
            content_type='application/json', **auth_headers(self.renter),
        )
        self.assertEqual(r1.status_code, 201)

        r2 = self.client.post(
            '/api/rentals/', payload,
            content_type='application/json', **auth_headers(self.renter),
        )
        self.assertEqual(r2.status_code, 400)


class TestRentalAPITransitions(TestCase):

    def setUp(self):
        self.owner = VerifiedUserFactory()
        self.renter = RenterFactory()
        self.product = ProductFactory(owner=self.owner)
        PricingTierFactory(product=self.product, duration_unit='day', price=500, max_period=30)

    def _make_rental(self, status='pending', **kwargs):
        return RentalFactory(
            product=self.product, owner=self.owner, renter=self.renter,
            status=status, **kwargs,
        )

    def test_owner_can_accept(self):
        rental = self._make_rental()
        r = self.client.post(
            f'/api/rentals/{rental.pk}/accept/',
            content_type='application/json',
            **auth_headers(self.owner),
        )
        self.assertEqual(r.status_code, 200, r.json())
        rental.refresh_from_db()
        self.assertEqual(rental.status, 'accepted')

    def test_renter_cannot_accept(self):
        rental = self._make_rental()
        r = self.client.post(
            f'/api/rentals/{rental.pk}/accept/',
            content_type='application/json',
            **auth_headers(self.renter),
        )
        self.assertEqual(r.status_code, 400)

    def test_owner_can_reject(self):
        rental = self._make_rental()
        r = self.client.post(
            f'/api/rentals/{rental.pk}/reject/',
            data={'note': 'Not available'},
            content_type='application/json',
            **auth_headers(self.owner),
        )
        self.assertEqual(r.status_code, 200)
        rental.refresh_from_db()
        self.assertEqual(rental.status, 'rejected')

    def test_renter_can_cancel_pending(self):
        rental = self._make_rental()
        r = self.client.post(
            f'/api/rentals/{rental.pk}/cancel/',
            content_type='application/json',
            **auth_headers(self.renter),
        )
        self.assertEqual(r.status_code, 200)
        rental.refresh_from_db()
        self.assertEqual(rental.status, 'cancelled')

    def test_owner_cannot_cancel_pending(self):
        rental = self._make_rental()
        r = self.client.post(
            f'/api/rentals/{rental.pk}/cancel/',
            content_type='application/json',
            **auth_headers(self.owner),
        )
        self.assertEqual(r.status_code, 400)

    def test_detail_includes_settlement(self):
        rental = self._make_rental(status='in_progress')
        r = self.client.get(
            f'/api/rentals/{rental.pk}/',
            **auth_headers(self.renter),
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn('settlement', r.json()['data'])

    def test_my_rentals_scoped_to_renter(self):
        self._make_rental()
        stranger = RenterFactory()
        r = self.client.get('/api/rentals/my-rentals/', **auth_headers(stranger))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['data']), 0)

    def test_my_rentals_returns_own(self):
        self._make_rental()
        r = self.client.get('/api/rentals/my-rentals/', **auth_headers(self.renter))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['data']), 1)


# ===========================================================================
# 6. compute_end_date utility
# ===========================================================================

class TestComputeEndDate(TestCase):

    def test_days(self):
        d = date(2024, 1, 10)
        self.assertEqual(compute_end_date(d, 5, 'day'), date(2024, 1, 15))

    def test_weeks(self):
        d = date(2024, 1, 1)
        self.assertEqual(compute_end_date(d, 2, 'week'), date(2024, 1, 15))

    def test_months_simple(self):
        d = date(2024, 1, 15)
        self.assertEqual(compute_end_date(d, 1, 'month'), date(2024, 2, 15))

    def test_months_clamp_end_of_month(self):
        # Jan 31 + 1 month → Feb 29 (2024 is leap year)
        d = date(2024, 1, 31)
        self.assertEqual(compute_end_date(d, 1, 'month'), date(2024, 2, 29))

    def test_months_cross_year(self):
        d = date(2024, 11, 30)
        self.assertEqual(compute_end_date(d, 3, 'month'), date(2025, 2, 28))

    def test_unknown_unit_raises(self):
        with self.assertRaises(ValueError):
            compute_end_date(date(2024, 1, 1), 1, 'hour')


# ===========================================================================
# 7. Photos endpoint
# ===========================================================================

def make_photo_file(name='photo.jpg', size=(100, 100)):
    img = Image.new('RGB', size, 'blue')
    buf = BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type='image/jpeg')


class TestRentalAPIPhotos(TestCase):

    def setUp(self):
        self.product = ProductFactory()
        self.owner = self.product.owner
        PricingTierFactory(product=self.product, duration_unit='day', price=500, max_period=30)
        self.rental = RentalFactory(
            product=self.product,
            owner=self.owner,
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=13),
            status='accepted',
        )
        self.renter = self.rental.renter
        self.url = f'/api/rentals/{self.rental.pk}/photos/'

    def test_get_photos_returns_list_for_participant(self):
        r = self.client.get(self.url, **auth_headers(self.renter))
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json()['data'], list)

    def test_get_photos_denied_for_stranger(self):
        from users.tests.factories import VerifiedUserFactory
        stranger = VerifiedUserFactory()
        r = self.client.get(self.url, **auth_headers(stranger))
        self.assertEqual(r.status_code, 404)

    def test_post_photo_succeeds_for_accepted(self):
        r = self.client.post(
            self.url,
            {'photo': make_photo_file(), 'photo_type': 'pre_rental'},
            **auth_headers(self.renter),
        )
        self.assertIn(r.status_code, (200, 201))
        self.assertEqual(RentalPhoto.objects.filter(rental=self.rental).count(), 1)

    def test_post_photo_succeeds_for_in_progress(self):
        self.rental.status = 'in_progress'
        self.rental.save(update_fields=['status'])
        r = self.client.post(
            self.url,
            {'photo': make_photo_file(), 'photo_type': 'post_rental'},
            **auth_headers(self.renter),
        )
        self.assertIn(r.status_code, (200, 201))

    def test_post_photo_blocked_for_pending(self):
        self.rental.status = 'pending'
        self.rental.save(update_fields=['status'])
        before = RentalPhoto.objects.filter(rental=self.rental).count()
        r = self.client.post(
            self.url,
            {'photo': make_photo_file(), 'photo_type': 'pre_rental'},
            **auth_headers(self.renter),
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(RentalPhoto.objects.filter(rental=self.rental).count(), before)

    def test_post_photo_oversized_rejected_before_save(self):
        """Size check fires before Pillow validation — no DB row created."""
        oversized = SimpleUploadedFile(
            'big.jpg',
            b'x' * (5 * 1024 * 1024 + 1),
            content_type='image/jpeg',
        )
        before = RentalPhoto.objects.filter(rental=self.rental).count()
        r = self.client.post(
            self.url,
            {'photo': oversized, 'photo_type': 'pre_rental'},
            **auth_headers(self.renter),
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn('5 MB', r.json()['message'])
        self.assertEqual(RentalPhoto.objects.filter(rental=self.rental).count(), before)
