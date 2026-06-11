from django.contrib import admin

from reviews.models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = [
        'short_id', 'reviewer', 'reviewee', 'product',
        'rating', 'direction', 'created_at',
    ]
    list_filter = ['direction', 'rating', 'created_at']
    search_fields = [
        'reviewer__phone_number', 'reviewee__phone_number',
        'product__title', 'comment',
    ]
    ordering = ['-created_at']
    readonly_fields = [
        'id', 'rental', 'reviewer', 'reviewee',
        'product', 'direction', 'created_at',
    ]
    fields = [
        'id', 'rental', 'reviewer', 'reviewee', 'product',
        'direction', 'rating', 'comment', 'created_at',
    ]

    def short_id(self, obj):
        return str(obj.pk)[:8]
    short_id.short_description = 'ID'

    def has_change_permission(self, request, obj=None):
        return False
