from django.contrib import admin
from django.utils.html import format_html
from users.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
  list_display = [
    'full_name', 
    'phone_number', 
    'trust_level', 
    'is_approved_status',
    'profile_completed',
    'created_at'
  ]
  list_filter = [
    'trust_level', 
    'is_approved', 
    'profile_completed', 
    'is_active', 
    'marketing_consent'
  ]
  search_fields = ['full_name', 'phone_number', 'email']
  ordering = ['-created_at']
  readonly_fields = ['id', 'created_at', 'updated_at']
  
  fieldsets = (
    ('Basic Information', {
      'fields': ('id', 'phone_number', 'full_name', 'email')
    }),
    ('Profile Information', {
      'fields': (
        'profile_picture', 
        'date_of_birth', 
        'district', 
        'thana', 
        'full_address'
      )
    }),
    ('Trust & Verification', {
      'fields': (
        'trust_level', 
        'is_approved', 
        'nid_number', 
        'nid_image', 
        'institutional_id_image'
      )
    }),
    ('Status & Permissions', {
      'fields': (
        'is_active', 
        'is_staff', 
        'profile_completed', 
        'marketing_consent'
      )
    }),
    ('Timestamps', {
      'fields': ('created_at', 'updated_at'),
      'classes': ('collapse',)
    }),
  )
  
  def is_approved_status(self, obj):
    """Display is_approved status with color coding."""
    if obj.is_approved is True:
      return format_html('<span style="color: green;">✓ Approved</span>')
    elif obj.is_approved is False:
      return format_html('<span style="color: red;">✗ Rejected</span>')
    else:
      return format_html('<span style="color: orange;">⏳ Pending</span>')
  is_approved_status.short_description = 'Approval Status'
  
  actions = ['approve_users', 'reject_users', 'make_partners']
  
  def approve_users(self, request, queryset):
    """Approve selected users."""
    updated = queryset.filter(is_approved__isnull=True).update(is_approved=True)
    self.message_user(request, f'{updated} users approved successfully.')
  approve_users.short_description = 'Approve selected users'
  
  def reject_users(self, request, queryset):
    """Reject selected users."""
    updated = queryset.filter(is_approved__isnull=True).update(is_approved=False)
    self.message_user(request, f'{updated} users rejected successfully.')
  reject_users.short_description = 'Reject selected users'
  
  def make_partners(self, request, queryset):
    """Make selected users partners."""
    updated = queryset.update(trust_level='partner')
    self.message_user(request, f'{updated} users made partners successfully.')
  make_partners.short_description = 'Make selected users partners'
