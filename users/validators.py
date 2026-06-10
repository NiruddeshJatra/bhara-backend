import re
from datetime import date
from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError


def validate_bd_phone(phone_number):
  """
  Valid formats: 01XXXXXXXXX (11 digits) or +8801XXXXXXXXX or 8801XXXXXXXXX.
  Normalizes to 01XXXXXXXXX before storage.
  """
  phone = phone_number.strip()
  # Strip country code if present
  if phone.startswith('+880'):
    phone = '0' + phone[4:]
  elif phone.startswith('880'):
    phone = '0' + phone[3:]
  pattern = r'^01[3-9]\d{8}$'
  if not re.match(pattern, phone):
    raise ValidationError(
      'Enter a valid Bangladeshi phone number (e.g. 01712345678).'
    )
  return phone


def validate_age_18(date_of_birth):
  """User must be at least 18 years old."""
  today = date.today()
  age = relativedelta(today, date_of_birth).years
  if age < 18:
    raise ValidationError('You must be at least 18 years old.')
  return date_of_birth


def validate_password_strength(password):
  """Minimum 8 chars, at least one letter and one number."""
  if len(password) < 8:
    raise ValidationError('Password must be at least 8 characters.')
  if not re.search(r'[A-Za-z]', password):
    raise ValidationError('Password must contain at least one letter.')
  if not re.search(r'\d', password):
    raise ValidationError('Password must contain at least one number.')
  return password
