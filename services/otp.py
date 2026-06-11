import hashlib
import hmac
import random
import string
from django.core.cache import cache
from django.conf import settings

OTP_MAX_ATTEMPTS = 5


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


def _attempts_key(purpose, phone_number):
  return f'otp_attempts:{purpose}:{phone_number}'


def create_otp(purpose, phone_number):
  """
  Generates OTP, stores hashed value in cache with TTL.
  Returns the plaintext OTP (to be sent via SMS).
  Purpose: 'signup' | 'password_reset'
  """
  otp = _generate_otp()
  key = _cache_key(purpose, phone_number)
  cache.set(key, _hash_otp(otp), timeout=settings.OTP_TTL_SECONDS)
  cache.delete(_attempts_key(purpose, phone_number))
  return otp


def verify_otp(purpose, phone_number, otp_input):
  """
  Verifies OTP. Returns True and deletes key on success.
  Returns False if not found or doesn't match.
  After OTP_MAX_ATTEMPTS wrong attempts the OTP key is deleted,
  forcing a re-request (brute-force protection).
  """
  key = _cache_key(purpose, phone_number)
  stored_hash = cache.get(key)
  if stored_hash is None:
    return False
  if not hmac.compare_digest(stored_hash, _hash_otp(otp_input)):
    attempts_key = _attempts_key(purpose, phone_number)
    attempts = cache.get(attempts_key, 0) + 1
    if attempts >= OTP_MAX_ATTEMPTS:
      cache.delete(key)
      cache.delete(attempts_key)
    else:
      cache.set(attempts_key, attempts, timeout=settings.OTP_TTL_SECONDS)
    return False
  cache.delete(key)
  cache.delete(_attempts_key(purpose, phone_number))
  return True
