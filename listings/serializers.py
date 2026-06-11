import json

from rest_framework import serializers
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from listings.models import Product, ProductImage, PricingTier, UnavailablePeriod
from listings.validators import validate_image_file, validate_purchase_year
from users.utils import compress_image


class ProductImageSerializer(serializers.ModelSerializer):
  image = serializers.SerializerMethodField()

  class Meta:
    model = ProductImage
    fields = ['id', 'image', 'created_at']
    read_only_fields = ['id', 'created_at']

  def get_image(self, obj):
    if not obj.image:
      return None
    request = self.context.get('request')
    if request:
      return request.build_absolute_uri(obj.image.url)
    return obj.image.url


class PricingTierSerializer(serializers.ModelSerializer):
  class Meta:
    model = PricingTier
    fields = ['id', 'duration_unit', 'price', 'max_period']
    read_only_fields = ['id']

  def validate_price(self, value):
    if value <= 0:
      raise serializers.ValidationError(_('Price must be greater than 0'))
    return value

  def validate_max_period(self, value):
    if value <= 0:
      raise serializers.ValidationError(_('Max period must be greater than 0'))
    return value


class UnavailablePeriodSerializer(serializers.ModelSerializer):
  date = serializers.DateField(required=False, allow_null=True)
  range_start = serializers.DateField(required=False, allow_null=True)
  range_end = serializers.DateField(required=False, allow_null=True)
  is_range = serializers.BooleanField(default=False)

  class Meta:
    model = UnavailablePeriod
    fields = ['id', 'date', 'is_range', 'range_start', 'range_end']
    read_only_fields = ['id']

  def validate(self, data):
    if data.get('is_range'):
      if not data.get('range_start') or not data.get('range_end'):
        raise serializers.ValidationError(
          _('Range start and end dates are required for date ranges')
        )
      if data['range_end'] < data['range_start']:
        raise serializers.ValidationError(_('End date must be after start date'))
      # Model requires a date even for ranges (legacy shape) — anchor on range start
      data.setdefault('date', data['range_start'])
      if data['date'] is None:
        data['date'] = data['range_start']
    elif not data.get('date'):
      raise serializers.ValidationError(_('Date is required for single dates'))
    return data


class ProductSerializer(serializers.ModelSerializer):
  # Write: list of uploaded files. Read: nested objects (see to_representation).
  # required=False so partial updates (PATCH) that don't change images pass validation.
  # create() path enforces at-least-one via validate().
  images = serializers.ListField(
    child=serializers.ImageField(allow_empty_file=False, use_url=False),
    write_only=True,
    required=False,
    min_length=1,
    max_length=8,
    error_messages={
      'min_length': _('At least 1 image is required.'),
      'max_length': _('At most 8 images are allowed.'),
    },
  )
  pricing_tiers = PricingTierSerializer(many=True, read_only=True)
  unavailable_periods = UnavailablePeriodSerializer(many=True, read_only=True)
  owner = serializers.SerializerMethodField()

  class Meta:
    model = Product
    fields = [
      'id',
      'owner',
      'title',
      'category',
      'product_type',
      'description',
      'location',
      'security_deposit',
      'purchase_year',
      'original_price',
      'ownership_history',
      'status',
      'images',
      'views_count',
      'rental_count',
      'average_rating',
      'created_at',
      'updated_at',
      'unavailable_periods',
      'pricing_tiers',
    ]
    read_only_fields = [
      'id',
      'owner',
      'status',
      'views_count',
      'rental_count',
      'average_rating',
      'created_at',
      'updated_at',
    ]

  def get_owner(self, obj):
    return {
      'id': str(obj.owner_id),
      'full_name': obj.owner.full_name,
      'trust_level': obj.owner.trust_level,
      'average_rating': str(obj.owner.average_rating),
    }

  def to_representation(self, instance):
    rep = super().to_representation(instance)
    rep['images'] = ProductImageSerializer(
      instance.images.all(), many=True, context=self.context
    ).data
    return rep

  def validate_images(self, value):
    for image in value:
      validate_image_file(image)
    # Compress during validation — i.e. before save and OUTSIDE any transaction
    return [
      compress_image(image, max_width=1200, max_height=900, quality=85)
      for image in value
    ]

  def validate_purchase_year(self, value):
    return validate_purchase_year(value)

  def validate_security_deposit(self, value):
    if value < 0:
      raise serializers.ValidationError(_('Security deposit cannot be negative.'))
    return value

  def _parse_nested_list(self, key):
    """
    Pulls a nested list out of initial_data. Multipart sends it as a JSON
    string (single key) or repeated keys (list of strings); JSON bodies send
    a real list. Returns None when absent.
    """
    if key not in self.initial_data:
      return None
    raw = self.initial_data[key]
    if hasattr(self.initial_data, 'getlist'):
      values = self.initial_data.getlist(key)
      raw = values[0] if len(values) == 1 else values
    if isinstance(raw, str):
      try:
        raw = json.loads(raw)
      except json.JSONDecodeError:
        raise serializers.ValidationError({key: [_('Invalid JSON.')]})
    if not isinstance(raw, list):
      raise serializers.ValidationError({key: [_('Expected a list.')]})
    # Normalize: multipart repeated keys yield a list of strings — parse each
    normalized = []
    for item in raw:
      if isinstance(item, str):
        try:
          normalized.append(json.loads(item))
        except json.JSONDecodeError:
          raise serializers.ValidationError({key: [_('Invalid JSON.')]})
      else:
        normalized.append(item)
    return normalized

  def _validate_nested(self, key, child_serializer_class, items):
    validated = []
    for item in items:
      child = child_serializer_class(data=item, context=self.context)
      child.is_valid(raise_exception=True)
      validated.append(child.validated_data)
    return validated

  def _replace_related(self, instance, related_manager, create_kwargs_list):
    related_manager.all().delete()
    for kwargs in create_kwargs_list:
      related_manager.create(product=instance, **kwargs)

  def validate(self, data):
    if self.instance is None and 'images' not in data:
      raise serializers.ValidationError(
        {'images': [_('At least 1 image is required.')]}
      )

    tiers = self._parse_nested_list('pricing_tiers')
    if self.instance is None and not tiers:
      raise serializers.ValidationError(
        {'pricing_tiers': [_('At least one pricing tier is required.')]}
      )
    if tiers is not None:
      units = [t.get('duration_unit') for t in tiers]
      if len(units) != len(set(units)):
        raise serializers.ValidationError(
          {'pricing_tiers': [_('Duplicate duration units are not allowed.')]}
        )
      data['pricing_tiers_data'] = self._validate_nested('pricing_tiers', PricingTierSerializer, tiers)

    periods = self._parse_nested_list('unavailable_periods')
    if periods is not None:
      data['unavailable_periods_data'] = self._validate_nested(
        'unavailable_periods', UnavailablePeriodSerializer, periods
      )
    return data

  def create(self, validated_data):
    images = validated_data.pop('images')
    tiers = validated_data.pop('pricing_tiers_data')
    periods = validated_data.pop('unavailable_periods_data', [])

    with transaction.atomic():
      product = Product.objects.create(**validated_data)
      for image in images:
        ProductImage.objects.create(product=product, image=image)
      for tier_data in tiers:
        PricingTier.objects.create(product=product, **tier_data)
      for period_data in periods:
        UnavailablePeriod.objects.create(product=product, **period_data)
    return product

  def update(self, instance, validated_data):
    images = validated_data.pop('images', None)
    tiers = validated_data.pop('pricing_tiers_data', None)
    periods = validated_data.pop('unavailable_periods_data', None)

    with transaction.atomic():
      for attr, value in validated_data.items():
        setattr(instance, attr, value)
      instance.save()

      if images is not None:
        for old in instance.images.all():
          old.delete()
        for image in images:
          ProductImage.objects.create(product=instance, image=image)
      if tiers is not None:
        self._replace_related(instance, instance.pricing_tiers, tiers)
      if periods is not None:
        self._replace_related(instance, instance.unavailable_periods, periods)
    return instance
