from django.contrib import admin
from django.utils.html import format_html

from listings.models import Product, ProductImage, PricingTier


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    readonly_fields = ['thumbnail', 'created_at']
    fields = ['thumbnail', 'image', 'created_at']

    def thumbnail(self, obj):
        if obj.image:
            return format_html('<img src="{}" height="60"/>', obj.image.url)
        return '—'
    thumbnail.short_description = 'Preview'


class PricingTierInline(admin.TabularInline):
    model = PricingTier
    extra = 1
    fields = ['duration_unit', 'price', 'max_period']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['title', 'owner_phone', 'status', 'category', 'created_at']
    list_filter = ['status', 'category']
    search_fields = ['title', 'owner__phone_number', 'owner__full_name']
    ordering = ['-created_at']
    readonly_fields = ['id', 'views_count', 'rental_count', 'average_rating', 'created_at', 'updated_at']
    inlines = [ProductImageInline, PricingTierInline]
    actions = ['suspend_products', 're_activate_products']

    def owner_phone(self, obj):
        return obj.owner.phone_number
    owner_phone.short_description = 'Owner phone'

    def suspend_products(self, request, queryset):
        updated = queryset.filter(status='active').update(status='suspended')
        self.message_user(request, f'{updated} product(s) suspended.')
    suspend_products.short_description = 'Suspend selected products'

    def re_activate_products(self, request, queryset):
        updated = queryset.filter(status='suspended').update(status='active')
        self.message_user(request, f'{updated} product(s) re-activated.')
    re_activate_products.short_description = 'Re-activate selected products'
