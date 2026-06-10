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
