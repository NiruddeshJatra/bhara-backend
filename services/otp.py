import hashlib
import random
import string
from django.core.cache import cache
from django.conf import settings


def _generate_otp():
  """Returns 6-digit OTP string. Hardcoded in DEBUG mode."""
  if settings.DEBUG:
    return settings.OTP_DEBUG_VALUE
  return ''.join(random.choices(string.digits, k=6))


def _hash_otp(otp):
  """SHA-256 hash of OTP. Cache stores hash, not plaintext."""
  return hashlib.sha256(otp.encode()).hexdigest()


def _cache_key(purpose, phone_number):
  return f'otp:{purpose}:{phone_number}'


def create_otp(purpose, phone_number):
  """
  Generates OTP, stores hashed value in cache with TTL.
  Returns the plaintext OTP (to be sent via SMS).
  Purpose: 'signup' | 'password_reset'
  """
  otp = _generate_otp()
  key = _cache_key(purpose, phone_number)
  cache.set(key, _hash_otp(otp), timeout=settings.OTP_TTL_SECONDS)
  return otp


def verify_otp(purpose, phone_number, otp_input):
  """
  Verifies OTP. Returns True and deletes key on success.
  Returns False if not found or doesn't match.
  """
  key = _cache_key(purpose, phone_number)
  stored_hash = cache.get(key)
  if stored_hash is None:
    return False
  if stored_hash != _hash_otp(otp_input):
    return False
  cache.delete(key)
  return True
