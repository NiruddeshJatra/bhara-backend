import os
from datetime import datetime

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _


def validate_image_file(value):
  """Spec §3.3: each image ≤5MB, jpeg/png only."""
  ext = os.path.splitext(value.name)[1].lower()
  if ext not in ['.jpg', '.jpeg', '.png']:
    raise serializers.ValidationError(_('Only JPG and PNG files are allowed.'))
  if value.size > 5 * 1024 * 1024:
    raise serializers.ValidationError(_('File size cannot exceed 5MB.'))
  return value


def validate_purchase_year(value):
  """Spec §3.3: a valid year ≤ current."""
  if not value:
    raise serializers.ValidationError(_('Purchase year is required.'))
  try:
    year = int(value)
  except (TypeError, ValueError):
    raise serializers.ValidationError(_('Purchase year must be a valid year.'))
  current_year = datetime.now().year
  if year > current_year:
    raise serializers.ValidationError(_('Purchase year cannot be in the future.'))
  if year < 1900:
    raise serializers.ValidationError(_('Purchase year seems invalid.'))
  return str(year)
