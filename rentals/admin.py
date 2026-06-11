import json

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
            return sum(r.amount for r in records if r.record_type == rtype)

        rent = total('rent_collected')
        payout = total('owner_payout')
        return f'Rent ৳{rent} | Payout ৳{payout}'
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

    def mark_in_progress(self, request, queryset):
        for rental in queryset.filter(status='accepted'):
            try:
                rental.transition('in_progress', request.user, 'Marked in_progress via admin')
                self.message_user(request, f'Rental {str(rental.pk)[:8]} marked in_progress.')
            except TransitionError as e:
                self.message_user(request, f'Rental {str(rental.pk)[:8]}: {e}', level='ERROR')
    mark_in_progress.short_description = 'Mark item handed to renter (in_progress)'

    def mark_completed(self, request, queryset):
        for rental in queryset.filter(status='in_progress'):
            try:
                rental.transition('completed', request.user, 'Marked completed via admin')
                self.message_user(request, f'Rental {str(rental.pk)[:8]} completed.')
            except TransitionError as e:
                self.message_user(request, f'Rental {str(rental.pk)[:8]}: {e}', level='ERROR')
    mark_completed.short_description = 'Mark rental completed (settled)'

    def cancel_rental(self, request, queryset):
        for rental in queryset.filter(status__in=['pending', 'accepted']):
            try:
                rental.transition('cancelled', request.user, 'Cancelled via admin')
                self.message_user(request, f'Rental {str(rental.pk)[:8]} cancelled.')
            except TransitionError as e:
                self.message_user(request, f'Rental {str(rental.pk)[:8]}: {e}', level='ERROR')
    cancel_rental.short_description = 'Cancel rental (staff)'
