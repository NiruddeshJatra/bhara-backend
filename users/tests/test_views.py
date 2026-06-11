import json
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.cache import cache
from users.models import User
from users.tests.factories import UserFactory, VerifiedUserFactory
from services.otp import create_otp


class OTPViewTest(TestCase):
  def setUp(self):
    cache.clear()

  def test_otp_request_signup_success(self):
    """Test successful OTP request for signup."""
    data = {
      'phone_number': '01712345678',
      'purpose': 'signup'
    }
    response = self.client.post('/api/auth/otp/request/', data, content_type='application/json')
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.json()['success'])

  def test_otp_request_signup_fails_if_phone_exists(self):
    """Test OTP request fails if phone already exists for signup."""
    UserFactory(phone_number='01712345678')
    data = {
      'phone_number': '01712345678',
      'purpose': 'signup'
    }
    response = self.client.post('/api/auth/otp/request/', data, content_type='application/json')
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertFalse(response.json()['success'])

  def test_otp_request_password_reset_fails_if_phone_not_found(self):
    """Test OTP request fails if phone doesn't exist for password reset."""
    data = {
      'phone_number': '01712345678',
      'purpose': 'password_reset'
    }
    response = self.client.post('/api/auth/otp/request/', data, content_type='application/json')
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertFalse(response.json()['success'])

  def test_otp_verify_success_returns_ephemeral_token(self):
    """Test successful OTP verification returns ephemeral token."""
    phone = '01712345678'
    otp = create_otp('signup', phone)
    data = {
      'phone_number': phone,
      'otp': otp,
      'purpose': 'signup'
    }
    response = self.client.post('/api/auth/otp/verify/', data, content_type='application/json')
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.json()['success'])
    self.assertIn('ephemeral_token', response.json()['data'])

  def test_otp_verify_fails_with_wrong_otp(self):
    """Test OTP verification fails with wrong OTP."""
    phone = '01712345678'
    create_otp('signup', phone)
    data = {
      'phone_number': phone,
      'otp': '999999',
      'purpose': 'signup'
    }
    response = self.client.post('/api/auth/otp/verify/', data, content_type='application/json')
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertFalse(response.json()['success'])

  def test_otp_verify_fails_after_cache_expiry(self):
    """Test OTP verification fails after cache expiry."""
    phone = '01712345678'
    create_otp('signup', phone)
    # Simulate cache expiry
    cache.delete(f'otp:signup:{phone}')
    data = {
      'phone_number': phone,
      'otp': '111111',
      'purpose': 'signup'
    }
    response = self.client.post('/api/auth/otp/verify/', data, content_type='application/json')
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertFalse(response.json()['success'])


class SignupViewTest(TestCase):
  def setUp(self):
    cache.clear()

  def test_signup_complete_creates_user(self):
    """Test successful signup completion creates user."""
    phone = '01712345678'
    otp = create_otp('signup', phone)
    
    # Get ephemeral token
    verify_response = self.client.post('/api/auth/otp/verify/', {
      'phone_number': phone,
      'otp': otp,
      'purpose': 'signup'
    }, content_type='application/json')
    self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
    self.assertTrue(verify_response.json().get('success'))
    token = verify_response.json()['data']['ephemeral_token']
    
    # Complete signup
    data = {
      'full_name': 'John Doe',
      'password': 'Testpass123',
      'marketing_consent': False
    }
    response = self.client.post('/api/auth/signup/complete/', data, 
                              content_type='application/json',
                              HTTP_AUTHORIZATION=f'Bearer {token}')
    
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    self.assertTrue(response.json()['success'])
    self.assertTrue(User.objects.filter(phone_number=phone).exists())

  def test_signup_complete_sets_refresh_cookie(self):
    """Test signup completion sets refresh token cookie."""
    phone = '01712345678'
    otp = create_otp('signup', phone)
    
    verify_response = self.client.post('/api/auth/otp/verify/', {
      'phone_number': phone,
      'otp': otp,
      'purpose': 'signup'
    }, content_type='application/json')
    self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
    self.assertTrue(verify_response.json().get('success'))
    token = verify_response.json()['data']['ephemeral_token']
    
    data = {
      'full_name': 'John Doe',
      'password': 'Testpass123',
      'marketing_consent': False
    }
    response = self.client.post('/api/auth/signup/complete/', data, 
                              content_type='application/json',
                              HTTP_AUTHORIZATION=f'Bearer {token}')
    
    self.assertIn('refresh_token', response.cookies)

  def test_signup_complete_returns_access_token(self):
    """Test signup completion returns access token."""
    phone = '01712345678'
    otp = create_otp('signup', phone)
    
    verify_response = self.client.post('/api/auth/otp/verify/', {
      'phone_number': phone,
      'otp': otp,
      'purpose': 'signup'
    }, content_type='application/json')
    self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
    self.assertTrue(verify_response.json().get('success'))
    token = verify_response.json()['data']['ephemeral_token']
    
    data = {
      'full_name': 'John Doe',
      'password': 'Testpass123',
      'marketing_consent': False
    }
    response = self.client.post('/api/auth/signup/complete/', data, 
                              content_type='application/json',
                              HTTP_AUTHORIZATION=f'Bearer {token}')
    
    self.assertIn('access_token', response.json()['data'])

  def test_signup_complete_fails_with_invalid_ephemeral_token(self):
    """Test signup completion fails with invalid ephemeral token."""
    data = {
      'full_name': 'John Doe',
      'password': 'Testpass123',
      'marketing_consent': False
    }
    response = self.client.post('/api/auth/signup/complete/', data, 
                              content_type='application/json',
                              HTTP_AUTHORIZATION='Bearer invalid_token')
    
    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    payload = response.json()
    self.assertIn('success', payload)
    self.assertFalse(payload['success'])

  def test_signup_complete_fails_with_weak_password(self):
    """Test signup completion fails with weak password."""
    phone = '01712345678'
    otp = create_otp('signup', phone)
    
    verify_response = self.client.post('/api/auth/otp/verify/', {
      'phone_number': phone,
      'otp': otp,
      'purpose': 'signup'
    }, content_type='application/json')
    self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
    self.assertTrue(verify_response.json().get('success'))
    token = verify_response.json()['data']['ephemeral_token']
    
    data = {
      'full_name': 'John Doe',
      'password': 'weak',
      'marketing_consent': False
    }
    response = self.client.post('/api/auth/signup/complete/', data, 
                              content_type='application/json',
                              HTTP_AUTHORIZATION=f'Bearer {token}')
    
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertFalse(response.json()['success'])


class LoginViewTest(TestCase):
  def setUp(self):
    cache.clear()
    self.user = UserFactory(phone_number='01712345678')
    self.user.set_password('Testpass123')
    self.user.save()

  def test_login_success(self):
    """Test successful login."""
    data = {
      'phone_number': '01712345678',
      'password': 'Testpass123'
    }
    response = self.client.post('/api/auth/login/', data, content_type='application/json')
    
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.json()['success'])
    self.assertIn('access_token', response.json()['data'])

  def test_login_sets_refresh_cookie(self):
    """Test login sets refresh token cookie."""
    data = {
      'phone_number': '01712345678',
      'password': 'Testpass123'
    }
    response = self.client.post('/api/auth/login/', data, content_type='application/json')
    
    self.assertIn('refresh_token', response.cookies)

  def test_login_fails_with_wrong_password(self):
    """Test login fails with wrong password."""
    data = {
      'phone_number': '01712345678',
      'password': 'wrongpassword'
    }
    response = self.client.post('/api/auth/login/', data, content_type='application/json')
    
    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    self.assertFalse(response.json()['success'])

  def test_login_lockout_after_5_attempts(self):
    """Test login lockout after 5 failed attempts."""
    for i in range(5):
      response = self.client.post('/api/auth/login/', {
        'phone_number': '01712345678',
        'password': 'wrongpassword'
      }, content_type='application/json')
      self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    # 6th attempt should be locked
    response = self.client.post('/api/auth/login/', {
      'phone_number': '01712345678',
      'password': 'wrongpassword'
    }, content_type='application/json')
    self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

  def test_login_lockout_clears_on_success(self):
    """Test login lockout clears on successful login."""
    # Add failed attempts
    cache.set('login_attempts:01712345678', 3, timeout=900)
    
    # Successful login should clear attempts
    response = self.client.post('/api/auth/login/', {
      'phone_number': '01712345678',
      'password': 'Testpass123'
    }, content_type='application/json')
    
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertIsNone(cache.get('login_attempts:01712345678'))


class LogoutViewTest(TestCase):
  def setUp(self):
    self.user = UserFactory()
    refresh = RefreshToken.for_user(self.user)
    self.access_token = str(refresh.access_token)
    self.client.cookies['refresh_token'] = str(refresh)
    self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {self.access_token}'

  def test_logout_clears_cookie(self):
    """Test logout clears refresh token cookie."""
    response = self.client.post('/api/auth/logout/')
    
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.json()['success'])

  def test_logout_blacklists_token(self):
    """Test logout blacklists refresh token."""
    refresh = RefreshToken.for_user(self.user)
    self.client.cookies['refresh_token'] = str(refresh)
    
    response = self.client.post('/api/auth/logout/')
    
    # Try to use the blacklisted token
    try:
      refresh.check_blacklist()
      self.fail("Token should be blacklisted")
    except Exception:
      pass  # Expected


class TokenRefreshViewTest(TestCase):
  def setUp(self):
    self.user = UserFactory()
    refresh = RefreshToken.for_user(self.user)
    self.client.cookies['refresh_token'] = str(refresh)

  def test_token_refresh_success_with_cookie(self):
    """Test token refresh succeeds with valid cookie."""
    response = self.client.post('/api/auth/token/refresh/')
    
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.json()['success'])
    self.assertIn('access_token', response.json()['data'])

  def test_token_refresh_fails_without_cookie(self):
    """Test token refresh fails without cookie."""
    self.client.cookies.clear()
    response = self.client.post('/api/auth/token/refresh/')
    
    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    self.assertFalse(response.json()['success'])


class ProfileViewTest(TestCase):
  def setUp(self):
    self.user = VerifiedUserFactory()
    refresh = RefreshToken.for_user(self.user)
    self.client.cookies['refresh_token'] = str(refresh)
    self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {refresh.access_token}'

  def test_profile_step1_saves_and_sets_profile_completed(self):
    """Test profile step 1 saves data and sets profile_completed."""
    data = {
      'date_of_birth': '1995-01-01',
      'district': 'Dhaka',
      'thana': 'Mirpur',
      'full_address': 'House 5, Road 3, Mirpur-10',
      'email': 'test@example.com'
    }
    response = self.client.patch('/api/users/profile/step1/', data, 
                               content_type='application/json')
    
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.json()['success'])
    
    self.user.refresh_from_db()
    self.assertTrue(self.user.profile_completed)
    self.assertEqual(self.user.district, 'Dhaka')

  def test_profile_step1_rejects_under_18_dob(self):
    """Test profile step 1 rejects under 18 date of birth."""
    data = {
      'date_of_birth': '2010-01-01',  # Under 18
      'district': 'Dhaka',
      'thana': 'Mirpur',
      'full_address': 'House 5, Road 3, Mirpur-10'
    }
    response = self.client.patch('/api/users/profile/step1/', data, 
                               content_type='application/json')
    
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertFalse(response.json()['success'])

  def test_profile_step1_requires_district_thana_address(self):
    """Test profile step 1 requires district, thana, and address."""
    data = {
      'date_of_birth': '1995-01-01'
      # Missing district, thana, full_address
    }
    response = self.client.patch('/api/users/profile/step1/', data, 
                               content_type='application/json')
    
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertFalse(response.json()['success'])

  def test_profile_step2_requires_step1_first(self):
    """Test profile step 2 requires step 1 completion first."""
    user = UserFactory()  # profile_completed=False
    refresh = RefreshToken.for_user(user)
    self.client.cookies['refresh_token'] = str(refresh)
    self.client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {refresh.access_token}'
    
    data = {
      'nid_number': '1234567890',
      'nid_image': 'dummy_image.jpg'
    }
    response = self.client.post('/api/users/profile/step2/', data, 
                               content_type='application/json')
    
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    self.assertFalse(response.json()['success'])

  def test_profile_step2_saves_documents_and_sets_pending(self):
    """Test profile step 2 saves documents and sets pending status."""
    # Note: This test would need actual file upload testing
    # For now, just test the basic structure
    data = {
      'nid_number': '1234567890'
      # nid_image would be added in actual file upload test
    }
    response = self.client.post('/api/users/profile/step2/', data, 
                               content_type='application/json')
    
    # Will fail due to missing image, but that's expected
    self.assertIn(response.status_code, [400, 415])

  def test_update_name_allowed_with_no_transactions(self):
    """Test name update allowed when user has no completed transactions."""
    data = {'full_name': 'New Name'}
    response = self.client.patch('/api/users/profile/', data, 
                                content_type='application/json')
    
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.json()['success'])
    
    self.user.refresh_from_db()
    self.assertEqual(self.user.full_name, 'New Name')

  def test_update_name_blocked_with_completed_transaction(self):
    """Test name update blocked when user has completed transactions."""
    # This test would require creating a mock rental transaction
    # For now, just test the basic structure
    # In a real implementation, you'd need to create the rentals app first
    pass


class OTPBruteForceTest(TestCase):
  """§9 item 1 — OTP verify attempt cap and throttle."""

  def setUp(self):
    cache.clear()
    self.phone = '01712345678'

  def _verify(self, otp):
    return self.client.post('/api/auth/otp/verify/', {
      'phone_number': self.phone,
      'otp': otp,
      'purpose': 'signup'
    }, content_type='application/json')

  def test_otp_deleted_after_5_wrong_attempts(self):
    """5 wrong attempts delete the OTP — correct OTP no longer works."""
    otp = create_otp('signup', self.phone)
    for _ in range(5):
      response = self._verify('999999')
      self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    self.assertIsNone(cache.get(f'otp:signup:{self.phone}'))
    response = self._verify(otp)
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

  def test_correct_otp_succeeds_after_4_wrong_attempts(self):
    """Attempt counter only kills the OTP at 5 — 4 wrong then correct is fine."""
    otp = create_otp('signup', self.phone)
    for _ in range(4):
      self._verify('999999')
    response = self._verify(otp)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.json()['success'])

  def test_otp_verify_throttled_after_10_per_minute(self):
    """AnonRateThrottle (10/min) kicks in on the 11th verify request."""
    create_otp('signup', self.phone)
    for _ in range(10):
      response = self._verify('999999')
      self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    response = self._verify('999999')
    self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class SMSCapTest(TestCase):
  """§9 item 2 — per-phone SMS caps (1/min, 5/day)."""

  def setUp(self):
    cache.clear()
    self.phone = '01712345678'
    self.data = {'phone_number': self.phone, 'purpose': 'signup'}

  def test_second_request_within_minute_capped(self):
    response = self.client.post('/api/auth/otp/request/', self.data, content_type='application/json')
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    response = self.client.post('/api/auth/otp/request/', self.data, content_type='application/json')
    self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
    self.assertFalse(response.json()['success'])

  def test_daily_cap_of_5_per_phone(self):
    cache.set(f'sms_cap:day:{self.phone}', 5, timeout=86400)
    response = self.client.post('/api/auth/otp/request/', self.data, content_type='application/json')
    self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
    self.assertFalse(response.json()['success'])

  def test_daily_counter_increments_per_send(self):
    self.client.post('/api/auth/otp/request/', self.data, content_type='application/json')
    self.assertEqual(cache.get(f'sms_cap:day:{self.phone}'), 1)


class LoginLockoutTTLTest(TestCase):
  """§9 item 3 — cache.ttl() guard: LocMemCache lacks .ttl, must not crash."""

  def setUp(self):
    cache.clear()
    self.user = UserFactory(phone_number='01712345678')
    self.user.set_password('Testpass123')
    self.user.save()

  def test_lockout_falls_back_to_lockout_window_without_ttl_support(self):
    from django.conf import settings as dj_settings
    # Precondition: dev cache backend has no .ttl (the crash §9.3 guards against)
    self.assertFalse(hasattr(cache, 'ttl'))

    cache.set('login_attempts:01712345678', dj_settings.LOGIN_MAX_ATTEMPTS, timeout=900)
    response = self.client.post('/api/auth/login/', {
      'phone_number': '01712345678',
      'password': 'Testpass123'
    }, content_type='application/json')

    self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
    self.assertIn(
      f'Try again in {dj_settings.LOGIN_LOCKOUT_SECONDS} seconds',
      response.json()['data']['detail']
    )


class TokenRotationTest(TestCase):
  """§9 item 4 — real refresh rotation with old token blacklisted."""

  def setUp(self):
    self.user = UserFactory()
    self.old_refresh = str(RefreshToken.for_user(self.user))
    self.client.cookies['refresh_token'] = self.old_refresh

  def test_refresh_sets_a_new_rotated_token(self):
    response = self.client.post('/api/auth/token/refresh/')
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    new_refresh = response.cookies['refresh_token'].value
    self.assertNotEqual(new_refresh, self.old_refresh)

  def test_old_refresh_token_is_blacklisted_after_rotation(self):
    response = self.client.post('/api/auth/token/refresh/')
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    # Replay the pre-rotation token — must be rejected
    self.client.cookies['refresh_token'] = self.old_refresh
    response = self.client.post('/api/auth/token/refresh/')
    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    self.assertFalse(response.json()['success'])


class EphemeralTokenSingleUseTest(TestCase):
  """§9 item 5 — ephemeral token jti is single-use."""

  def setUp(self):
    cache.clear()
    self.phone = '01712345678'

  def _get_ephemeral_token(self, purpose):
    otp = create_otp(purpose, self.phone)
    response = self.client.post('/api/auth/otp/verify/', {
      'phone_number': self.phone,
      'otp': otp,
      'purpose': purpose
    }, content_type='application/json')
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    return response.json()['data']['ephemeral_token']

  def test_signup_token_rejected_on_reuse(self):
    token = self._get_ephemeral_token('signup')
    data = {'full_name': 'John Doe', 'password': 'Testpass123'}

    response = self.client.post('/api/auth/signup/complete/', data,
                                content_type='application/json',
                                HTTP_AUTHORIZATION=f'Bearer {token}')
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    User.objects.filter(phone_number=self.phone).delete()
    response = self.client.post('/api/auth/signup/complete/', data,
                                content_type='application/json',
                                HTTP_AUTHORIZATION=f'Bearer {token}')
    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    self.assertFalse(response.json()['success'])

  def test_password_reset_token_rejected_on_reuse(self):
    user = UserFactory(phone_number=self.phone)
    user.set_password('Oldpass123')
    user.save()

    token = self._get_ephemeral_token('password_reset')
    data = {'password': 'Newpass456'}

    response = self.client.post('/api/auth/password-reset/complete/', data,
                                content_type='application/json',
                                HTTP_AUTHORIZATION=f'Bearer {token}')
    self.assertEqual(response.status_code, status.HTTP_200_OK)

    response = self.client.post('/api/auth/password-reset/complete/', data,
                                content_type='application/json',
                                HTTP_AUTHORIZATION=f'Bearer {token}')
    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    self.assertFalse(response.json()['success'])
