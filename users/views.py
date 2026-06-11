from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.conf import settings
from django.db import transaction
import jwt
import uuid
from datetime import datetime, timedelta, timezone

from core.responses import success_response, error_response
from users.models import User
from users.utils import compress_image
from users import serializers as user_serializers
from services.otp import create_otp, verify_otp
from celery_tasks.users import send_otp_task


def _set_refresh_cookie(response, refresh_token_str):
  """Attaches refresh token as httpOnly cookie."""
  response.set_cookie(
    key=settings.SIMPLE_JWT['AUTH_COOKIE'],
    value=refresh_token_str,
    max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
    httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
    secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
    samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE'],
  )


def _clear_refresh_cookie(response):
  response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE'])


def _issue_tokens(user):
  """Returns (access_token_str, refresh_token_obj)."""
  refresh = RefreshToken.for_user(user)
  return str(refresh.access_token), refresh


def _create_ephemeral_token(phone_number, purpose):
  """
  Creates a short-lived JWT (10 min) encoding phone_number and purpose.
  Used between OTP verification and final signup/password-reset completion.
  """
  payload = {
    'phone_number': phone_number,
    'purpose': f'{purpose}_verified',
    'jti': str(uuid.uuid4()),
    'exp': datetime.now(timezone.utc) + timedelta(minutes=10),
  }
  return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


def _decode_ephemeral_token(token, expected_purpose):
  """
  Decodes and validates ephemeral token. Raises jwt exceptions on failure.
  Rejects tokens whose jti has already been consumed (single-use).
  Returns (phone_number, jti).
  """
  payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
  if payload.get('purpose') != expected_purpose:
    raise ValueError('Token purpose mismatch.')
  jti = payload.get('jti')
  if not jti or cache.get(f'used_jti:{jti}'):
    raise ValueError('Token already used.')
  return payload['phone_number'], jti


def _mark_jti_used(jti):
  """Consumes an ephemeral token's jti — kept for the token's max lifetime."""
  cache.set(f'used_jti:{jti}', True, timeout=600)


class OTPRateThrottle(AnonRateThrottle):
    scope = 'otp_request'  # own scope — must not share throttle history with verify
    rate = '3/minute' # Max 3 OTP requests per minute per IP


class OTPVerifyRateThrottle(AnonRateThrottle):
    scope = 'otp_verify'
    rate = '10/minute' # Max 10 OTP verify attempts per minute per IP


def _check_sms_caps(phone):
  """
  Per-phone SMS caps: 1/min and 5/day. IP throttling alone fails behind
  BD carrier NAT. Returns an error message if capped, else None.
  """
  if cache.get(f'sms_cap:minute:{phone}'):
    return 'Please wait a minute before requesting another OTP.'
  if cache.get(f'sms_cap:day:{phone}', 0) >= 5:
    return 'Daily OTP limit reached. Try again tomorrow.'
  return None


def _record_sms_sent(phone):
  cache.set(f'sms_cap:minute:{phone}', 1, timeout=60)
  day_key = f'sms_cap:day:{phone}'
  try:
    cache.incr(day_key)
  except ValueError:
    cache.set(day_key, 1, timeout=86400)


class OTPRequestView(APIView):
  permission_classes = [AllowAny]
  throttle_classes = [OTPRateThrottle]

  def post(self, request):
    serializer = user_serializers.OTPRequestSerializer(data=request.data)
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    phone = serializer.validated_data['phone_number']
    purpose = serializer.validated_data['purpose']

    cap_message = _check_sms_caps(phone)
    if cap_message:
      return error_response(
        {'detail': cap_message},
        'Too many OTP requests.',
        status.HTTP_429_TOO_MANY_REQUESTS
      )

    otp = create_otp(purpose, phone)
    send_otp_task.delay(phone, otp, purpose)
    _record_sms_sent(phone)

    return success_response(message='OTP sent successfully.')


class OTPVerifyView(APIView):
  permission_classes = [AllowAny]
  throttle_classes = [OTPVerifyRateThrottle]

  def post(self, request):
    serializer = user_serializers.OTPVerifySerializer(data=request.data)
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    phone = serializer.validated_data['phone_number']
    otp = serializer.validated_data['otp']
    purpose = serializer.validated_data['purpose']

    if not verify_otp(purpose, phone, otp):
      return error_response(
        {'otp': ['Invalid or expired OTP. Please try again.']},
        'OTP verification failed.',
        status.HTTP_400_BAD_REQUEST
      )

    ephemeral_token = _create_ephemeral_token(phone, purpose)
    return success_response(
      {'ephemeral_token': ephemeral_token},
      'OTP verified successfully.'
    )


class SignupCompleteView(APIView):
  permission_classes = [AllowAny]
  # We manually validate the ephemeral token from Authorization header.
  # No SessionAuthentication: its CSRF check can 403 browsers carrying a
  # Django admin session cookie.
  authentication_classes = []

  @transaction.atomic
  def post(self, request):
    # Extract and validate ephemeral token from Authorization header
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
      return error_response(message='Ephemeral token required.', status_code=status.HTTP_401_UNAUTHORIZED)
    token = auth_header.split(' ')[1]

    try:
      phone_number, jti = _decode_ephemeral_token(token, 'signup_verified')
    except Exception:
      return error_response(message='Invalid or expired token.', status_code=status.HTTP_401_UNAUTHORIZED)

    serializer = user_serializers.SignupCompleteSerializer(data=request.data)
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    # Guard: phone should not already exist (race condition)
    if User.objects.filter(phone_number=phone_number).exists():
      return error_response(
        {'phone_number': ['An account with this phone number already exists.']},
        'Registration failed.'
      )

    user = User.objects.create_user(
      phone_number=phone_number,
      full_name=serializer.validated_data['full_name'],
      password=serializer.validated_data['password'],
      marketing_consent=serializer.validated_data.get('marketing_consent', False),
    )
    _mark_jti_used(jti)

    access_token, refresh = _issue_tokens(user)
    response = success_response(
      {
        'access_token': access_token,
        'user': {
          'id': str(user.id),
          'full_name': user.full_name,
          'phone_number': user.phone_number,
          'profile_completed': user.profile_completed,
          'trust_level': user.trust_level,
        }
      },
      'Account created successfully.',
      status.HTTP_201_CREATED
    )
    _set_refresh_cookie(response, str(refresh))
    return response


class LoginView(APIView):
  permission_classes = [AllowAny]

  def post(self, request):
    serializer = user_serializers.LoginSerializer(data=request.data)
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    phone = serializer.validated_data['phone_number']
    password = serializer.validated_data['password']

    # Check lockout
    lockout_key = f'login_attempts:{phone}'
    attempts = cache.get(lockout_key, 0)
    if attempts >= settings.LOGIN_MAX_ATTEMPTS:
      # LocMemCache (dev) lacks .ttl — fall back to the full lockout window
      remaining = cache.ttl(lockout_key) if hasattr(cache, 'ttl') else settings.LOGIN_LOCKOUT_SECONDS
      return error_response(
        {'detail': f'Account locked. Try again in {remaining} seconds.'},
        'Too many failed attempts.',
        status.HTTP_429_TOO_MANY_REQUESTS
      )

    user = authenticate(request, username=phone, password=password)

    if user is None:
      # Increment failed attempts
      cache.set(lockout_key, attempts + 1, timeout=settings.LOGIN_LOCKOUT_SECONDS)
      return error_response(
        {'detail': 'Invalid phone number or password.'},
        'Login failed.',
        status.HTTP_401_UNAUTHORIZED
      )

    if not user.is_active:
      return error_response(
        {'detail': 'This account has been deactivated.'},
        'Login failed.',
        status.HTTP_401_UNAUTHORIZED
      )

    # Clear failed attempts on success
    cache.delete(lockout_key)

    access_token, refresh = _issue_tokens(user)
    response = success_response(
      {
        'access_token': access_token,
        'user': {
          'id': str(user.id),
          'full_name': user.full_name,
          'phone_number': user.phone_number,
          'profile_completed': user.profile_completed,
          'trust_level': user.trust_level,
          'is_approved': user.is_approved,
        }
      },
      'Login successful.'
    )
    _set_refresh_cookie(response, str(refresh))
    return response


class LogoutView(APIView):
  permission_classes = [IsAuthenticated]

  def post(self, request):
    refresh_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE'])
    if refresh_token:
      try:
        token = RefreshToken(refresh_token)
        token.blacklist()
      except Exception:
        pass  # Token already invalid — still clear cookie

    response = success_response(message='Logged out successfully.')
    _clear_refresh_cookie(response)
    return response


class TokenRefreshView(APIView):
  permission_classes = [AllowAny]

  def post(self, request):
    refresh_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE'])
    if not refresh_token:
      return error_response(message='No refresh token.', status_code=status.HTTP_401_UNAUTHORIZED)
    try:
      refresh = RefreshToken(refresh_token)
      user = User.objects.get(id=refresh['user_id'], is_active=True)
      # Real rotation: blacklist the incoming token, issue a fresh one
      refresh.blacklist()
      new_refresh = RefreshToken.for_user(user)
      response = success_response({'access_token': str(new_refresh.access_token)}, 'Token refreshed.')
      _set_refresh_cookie(response, str(new_refresh))
      return response
    except Exception:
      response = error_response(message='Invalid or expired refresh token.', status_code=status.HTTP_401_UNAUTHORIZED)
      _clear_refresh_cookie(response)
      return response


class PasswordResetCompleteView(APIView):
  permission_classes = [AllowAny]
  # Uses custom ephemeral token instead of DRF JWT auth token.
  # No SessionAuthentication: its CSRF check can 403 browsers carrying a
  # Django admin session cookie.
  authentication_classes = []

  @transaction.atomic
  def post(self, request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
      return error_response(message='Ephemeral token required.', status_code=status.HTTP_401_UNAUTHORIZED)
    token = auth_header.split(' ')[1]

    try:
      phone_number, jti = _decode_ephemeral_token(token, 'password_reset_verified')
    except Exception:
      return error_response(message='Invalid or expired token.', status_code=status.HTTP_401_UNAUTHORIZED)

    serializer = user_serializers.PasswordResetCompleteSerializer(data=request.data)
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    try:
      user = User.objects.get(phone_number=phone_number)
    except User.DoesNotExist:
      return error_response(message='User not found.', status_code=status.HTTP_404_NOT_FOUND)

    user.set_password(serializer.validated_data['password'])
    user.save(update_fields=['password'])
    _mark_jti_used(jti)

    # Blacklist all existing refresh tokens for this user
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    for token_obj in OutstandingToken.objects.filter(user=user):
      try:
        token_obj.blacklist()
      except Exception:
        pass

    return success_response(message='Password reset successfully.')


class ProfileStep1View(APIView):
  permission_classes = [IsAuthenticated]

  @transaction.atomic
  def patch(self, request):
    # Compress profile picture before transaction if provided
    if 'profile_picture' in request.FILES and request.FILES['profile_picture']:
      request.FILES._mutable = True
      request.FILES['profile_picture'] = compress_image(
        request.FILES['profile_picture'],
        max_width=800,
        max_height=800,
        quality=85
      )
      request.FILES._mutable = False
    
    serializer = user_serializers.ProfileStep1Serializer(
      instance=request.user,
      data=request.data,
      partial=True
    )
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    user = serializer.save()
    return success_response(
      user_serializers.UserProfileSerializer(user).data,
      'Profile updated successfully.'
    )


class ProfileStep2View(APIView):
  permission_classes = [IsAuthenticated]

  @transaction.atomic
  def post(self, request):
    if not request.user.profile_completed:
      return error_response(
        message='Complete Step 1 of your profile first.',
        status_code=status.HTTP_403_FORBIDDEN
      )
    
    # Compress images before transaction
    if 'nid_image' in request.FILES and request.FILES['nid_image']:
      request.FILES._mutable = True
      request.FILES['nid_image'] = compress_image(
        request.FILES['nid_image'],
        max_width=1200,
        max_height=900,
        quality=90
      )
    
    if 'institutional_id_image' in request.FILES and request.FILES['institutional_id_image']:
      if not hasattr(request.FILES, '_mutable') or not request.FILES._mutable:
        request.FILES._mutable = True
      request.FILES['institutional_id_image'] = compress_image(
        request.FILES['institutional_id_image'],
        max_width=1200,
        max_height=900,
        quality=90
      )
      request.FILES._mutable = False

    serializer = user_serializers.ProfileStep2Serializer(
      instance=request.user,
      data=request.data
    )
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')

    serializer.save()
    return success_response(
      message='Identity documents submitted. Your account is under review.'
    )


class UserProfileView(APIView):
  permission_classes = [IsAuthenticated]

  def get(self, request):
    serializer = user_serializers.UserProfileSerializer(request.user)
    return success_response(serializer.data)

  @transaction.atomic
  def patch(self, request):
    serializer = user_serializers.UpdateFullNameSerializer(
      instance=request.user,
      data=request.data
    )
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')
    serializer.save()
    return success_response(
      user_serializers.UserProfileSerializer(request.user).data,
      'Name updated successfully.'
    )
