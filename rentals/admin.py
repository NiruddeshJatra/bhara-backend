import json
from decimal import Decimal

from django.contrib import admin
from django.utils.html import format_html

from rentals.models import PaymentRecord, Rental, RentalPhoto
from rentals.state_machine import TransitionError


class PaymentRecordInline(admin.TabularInline):
    """Append-only: no change or delete permissions; recorded_by set automatically."""
    model = PaymentRecord
    extra = 1
    readonly_fields = ['id', 'recorded_by', 'created_at']
    fields = ['record_type', 'amount', 'method', 'reference', 'note', 'recorded_by', 'created_at']

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RentalPhotoInline(admin.TabularInline):
    model = RentalPhoto
    extra = 0
    readonly_fields = ['thumbnail', 'photo_type', 'uploaded_by', 'created_at']
    fields = ['thumbnail', 'photo_type', 'uploaded_by', 'created_at']

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def thumbnail(self, obj):
        if obj.photo:
            return format_html('<img src="{}" height="60"/>', obj.photo.url)
        return '—'
    thumbnail.short_description = 'Photo'


@admin.register(Rental)
class RentalAdmin(admin.ModelAdmin):
    list_display = [
        'short_id', 'product', 'renter_phone', 'owner_phone',
        'start_date', 'end_date', 'colored_status', 'settlement_summary',
    ]
    list_filter = ['status', 'start_date', 'end_date']
    search_fields = [
        'id', 'renter__phone_number', 'owner__phone_number', 'product__title',
    ]
    ordering = ['-created_at']
    readonly_fields = [
        'id', 'product', 'owner', 'renter',
        'start_date', 'end_date', 'duration', 'duration_unit',
        'unit_price', 'base_cost', 'service_fee', 'owner_payout', 'security_deposit',
        'purpose', 'notes', 'status', 'pretty_history',
        'created_at', 'updated_at',
    ]
    # status is deliberately excluded from editable fields — transitions only (§6)
    fields = [
        'id', 'product', 'owner', 'renter',
        'start_date', 'end_date', 'duration', 'duration_unit',
        'unit_price', 'base_cost', 'service_fee', 'owner_payout', 'security_deposit',
        'purpose', 'notes', 'status', 'pretty_history',
        'created_at', 'updated_at',
    ]
    inlines = [PaymentRecordInline, RentalPhotoInline]
    actions = ['mark_in_progress', 'mark_completed', 'cancel_rental']

    def short_id(self, obj):
        return str(obj.pk)[:8]
    short_id.short_description = 'ID'

    def renter_phone(self, obj):
        return obj.renter.phone_number
    renter_phone.short_description = 'Renter'

    def owner_phone(self, obj):
        return obj.owner.phone_number
    owner_phone.short_description = 'Owner'

    STATUS_COLORS = {
        'pending': 'orange',
        'accepted': 'blue',
        'in_progress': 'green',
        'completed': 'purple',
        'rejected': 'red',
        'cancelled': 'darkorange',
    }

    def colored_status(self, obj):
        color = self.STATUS_COLORS.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )
    colored_status.short_description = 'Status'

    def settlement_summary(self, obj):
        records = list(obj.payment_records.all())

        def total(rtype):
            return sum(
                (r.amount for r in records if r.record_type == rtype),
                Decimal('0'),
            )

        return f'Rent ৳{total("rent_collected")} | Payout ৳{total("owner_payout")}'
    settlement_summary.short_description = 'Settlement'

    def pretty_history(self, obj):
        return format_html(
            '<pre style="font-size:0.85em">{}</pre>',
            json.dumps(obj.status_history, indent=2),
        )
    pretty_history.short_description = 'Status history'

    def save_formset(self, request, form, formset, change):
        """Auto-set recorded_by on new PaymentRecord entries."""
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, PaymentRecord) and not instance.pk:
                instance.recorded_by = request.user
            instance.save()
        formset.save_m2m()

    # ------------------------------------------------------------------
    # Transition actions — implemented via Rental.transition() (§6)
    # ------------------------------------------------------------------

    def _bulk_transition(self, request, queryset, *, from_statuses, to_status, note, msg):
        status_filter = (
            {'status': from_statuses}
            if isinstance(from_statuses, str)
            else {'status__in': from_statuses}
        )
        for rental in queryset.filter(**status_filter):
            pk_short = str(rental.pk)[:8]
            try:
                rental.transition(to_status, request.user, note)
                self.message_user(request, msg.format(pk=pk_short))
            except TransitionError as e:
                self.message_user(request, f'Rental {pk_short}: {e}', level='ERROR')

    def mark_in_progress(self, request, queryset):
        self._bulk_transition(
            request, queryset,
            from_statuses='accepted', to_status='in_progress',
            note='Marked in_progress via admin',
            msg='Rental {pk} marked in_progress.',
        )
    mark_in_progress.short_description = 'Mark item handed to renter (in_progress)'

    def mark_completed(self, request, queryset):
        self._bulk_transition(
            request, queryset,
            from_statuses='in_progress', to_status='completed',
            note='Marked completed via admin',
            msg='Rental {pk} completed.',
        )
    mark_completed.short_description = 'Mark rental completed (settled)'

    def cancel_rental(self, request, queryset):
        self._bulk_transition(
            request, queryset,
            from_statuses=['pending', 'accepted'], to_status='cancelled',
            note='Cancelled via admin',
            msg='Rental {pk} cancelled.',
        )
    cancel_rental.short_description = 'Cancel rental (staff)'
