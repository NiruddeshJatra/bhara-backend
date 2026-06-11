import uuid

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from listings.constants import (
  CATEGORY_CHOICES,
  PRODUCT_TYPE_CHOICES,
  OWNERSHIP_HISTORY_CHOICES,
  STATUS_CHOICES,
  DURATION_UNITS,
)


class Product(models.Model):
  """A rental item in the marketplace."""

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  owner = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE,
    related_name='products',
  )
  title = models.CharField(max_length=255)
  category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, db_index=True)
  product_type = models.CharField(max_length=50, choices=PRODUCT_TYPE_CHOICES)
  description = models.TextField(blank=True)
  location = models.CharField(max_length=255, db_index=True)
  security_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
  purchase_year = models.CharField(max_length=4)
  original_price = models.DecimalField(max_digits=10, decimal_places=2)
  ownership_history = models.CharField(max_length=50, choices=OWNERSHIP_HISTORY_CHOICES)
  # Listings publish directly to 'active' (creator is identity-verified).
  # Whether an item is currently out is derived from rentals, never stored here.
  status = models.CharField(
    max_length=20, choices=STATUS_CHOICES, default='active', db_index=True
  )
  views_count = models.PositiveIntegerField(default=0)
  rental_count = models.PositiveIntegerField(default=0)
  average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['-created_at']
    verbose_name = _('Product')
    verbose_name_plural = _('Products')

  def __str__(self):
    return self.title

  def has_blocking_rentals(self):
    """Update/destroy are blocked while a rental is accepted or in_progress (§3.2)."""
    if not apps.is_installed('rentals'):
      return False
    return self.rentals.filter(status__in=['accepted', 'in_progress']).exists()


class ProductImage(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
  image = models.ImageField(upload_to='product_images/', max_length=255)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['created_at']
    verbose_name = _('Product Image')
    verbose_name_plural = _('Product Images')

  def __str__(self):
    return f'Image for {self.product.title}'

  def delete(self, *args, **kwargs):
    """Clean up the image file on delete."""
    if self.image:
      self.image.delete(save=False)
    super().delete(*args, **kwargs)


class PricingTier(models.Model):
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='pricing_tiers')
  duration_unit = models.CharField(max_length=10, choices=DURATION_UNITS)
  price = models.PositiveIntegerField(help_text=_('Price per duration unit in Taka'))
  max_period = models.PositiveIntegerField(
    default=30,
    help_text=_('Maximum rental period in the specified duration unit'),
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['duration_unit', 'price']
    verbose_name = _('Pricing Tier')
    verbose_name_plural = _('Pricing Tiers')
    constraints = [
      models.UniqueConstraint(
        fields=['product', 'duration_unit'],
        name='unique_duration_unit_per_product',
      )
    ]

  def __str__(self):
    return f'{self.duration_unit} - {self.price} Taka (max {self.max_period})'


class UnavailablePeriod(models.Model):
  """
  OWNER-declared availability blocks only (single date or range).
  Rental-occupied dates are computed from rentals (§4.6), never written here.
  """

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  product = models.ForeignKey(
    Product, on_delete=models.CASCADE, related_name='unavailable_periods'
  )
  date = models.DateField(help_text=_('Single unavailable date'))
  is_range = models.BooleanField(default=False)
  range_start = models.DateField(null=True, blank=True)
  range_end = models.DateField(null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['date']
    verbose_name = _('Unavailable Period')
    verbose_name_plural = _('Unavailable Periods')
    constraints = [
      models.CheckConstraint(
        condition=models.Q(
          models.Q(is_range=False)
          | (
            models.Q(is_range=True)
            & models.Q(range_start__isnull=False)
            & models.Q(range_end__isnull=False)
            & models.Q(range_end__gte=models.F('range_start'))
          )
        ),
        name='valid_period_range',
      )
    ]

  def __str__(self):
    if self.is_range:
      return f'Unavailable from {self.range_start} to {self.range_end}'
    return f'Unavailable on {self.date}'

  def clean(self):
    if self.is_range and (not self.range_start or not self.range_end):
      raise ValidationError('Range start and end dates are required for date ranges')
    if not self.is_range and not self.date:
      raise ValidationError('Date is required for single dates')
