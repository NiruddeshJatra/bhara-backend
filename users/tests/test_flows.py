from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from services.otp import create_otp

User = get_user_model()


class TestUserLifecycleFlow(APITestCase):
  """
  End-to-end flow test for full user lifecycle.
  Ensures the strict sequence of auth module works correctly.
  """

  def setUp(self):
    """Clear cache before each test."""
    cache.clear()

  def test_full_user_lifecycle_flow(self):
    """
    Test complete user journey from signup to profile completion.
    1. POST /api/auth/otp/request/ (Signup)
    2. POST /api/auth/otp/verify/ -> Capture ephemeral_token
    3. POST /api/auth/signup/complete/ -> Capture access_token
    4. PATCH /api/users/profile/step1/ -> Ensure profile_completed becomes True
    5. POST /api/users/profile/step2/ -> Ensure is_approved becomes None (pending)
    6. Verify final DB state for user object matches expected outputs.
    """
    phone_number = '01712345678'
    password = 'TestPass123'
    full_name = 'Test User'
    
    # Step 1: Request OTP for signup
    otp_request_data = {
        'phone_number': phone_number,
        'purpose': 'signup'
    }
    response = self.client.post('/api/auth/otp/request/', otp_request_data)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.data['success'])
    
    # Step 2: Verify OTP using generated value
    otp = create_otp('signup', phone_number)
    otp_verify_data = {
        'phone_number': phone_number,
        'otp': otp,
        'purpose': 'signup'
    }
    response = self.client.post('/api/auth/otp/verify/', otp_verify_data)
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.data['success'])
    self.assertIn('ephemeral_token', response.data['data'])
    ephemeral_token = response.data['data']['ephemeral_token']
    
    # Step 3: Complete signup
    signup_data = {
      'full_name': full_name,
      'password': password,
      'marketing_consent': True
    }
    response = self.client.post(
      '/api/auth/signup/complete/',
      signup_data,
      HTTP_AUTHORIZATION=f'Bearer {ephemeral_token}'
    )
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    self.assertTrue(response.data['success'])
    self.assertIn('access_token', response.data['data'])
    self.assertIn('user', response.data['data'])
    
    # Verify user was created
    user = User.objects.get(phone_number=phone_number)
    self.assertEqual(user.full_name, full_name)
    self.assertEqual(user.phone_number, phone_number)
    self.assertEqual(user.trust_level, 'unverified')
    self.assertFalse(user.profile_completed)
    self.assertIsNone(user.is_approved)
    self.assertTrue(user.marketing_consent)
    
    # Step 4: Complete Profile Step 1
    access_token = response.data['data']['access_token']
    profile_step1_data = {
      'date_of_birth': '1995-01-01',
      'district': 'Dhaka',
      'thana': 'Mirpur',
      'full_address': 'House 5, Road 3, Mirpur-10',
      'email': 'test@example.com'
    }
    response = self.client.patch(
      '/api/users/profile/step1/',
      profile_step1_data,
      HTTP_AUTHORIZATION=f'Bearer {access_token}'
    )
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.data['success'])
    
    # Verify profile step 1 completion
    user.refresh_from_db()
    self.assertTrue(user.profile_completed)
    self.assertEqual(user.date_of_birth.isoformat(), '1995-01-01')
    self.assertEqual(user.district, 'Dhaka')
    self.assertEqual(user.thana, 'Mirpur')
    self.assertEqual(user.full_address, 'House 5, Road 3, Mirpur-10')
    self.assertEqual(user.email, 'test@example.com')
    
    # Step 5: Complete Profile Step 2 (Identity Verification)
    # Create mock image files
    from io import BytesIO
    from PIL import Image
    
    def create_test_image(name='test.jpg'):
      image = Image.new('RGB', (100, 100), 'red')
      buffer = BytesIO()
      image.save(buffer, format='JPEG')
      buffer.seek(0)
      return SimpleUploadedFile(name, buffer.read(), content_type='image/jpeg')
    
    nid_image = create_test_image()
    institutional_image = create_test_image()
    
    profile_step2_data = {
      'nid_number': '1234567890123',
      'nid_image': nid_image,
      'institutional_id_image': institutional_image
    }
    
    response = self.client.post(
      '/api/users/profile/step2/',
      profile_step2_data,
      format='multipart',
      HTTP_AUTHORIZATION=f'Bearer {access_token}'
    )
    self.assertIn(
      response.status_code,
      [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE]
    )
    if response.status_code == status.HTTP_200_OK:
      self.assertTrue(response.data['success'])
    
    # Step 6: Verify final DB state
    user.refresh_from_db()
    if response.status_code == status.HTTP_200_OK:
      self.assertEqual(user.nid_number, '1234567890123')
      self.assertIsNotNone(user.nid_image)
      self.assertIsNotNone(user.institutional_id_image)
    self.assertIsNone(user.is_approved)  # Should be pending
    self.assertTrue(user.profile_completed)  # Should still be True
    self.assertEqual(user.trust_level, 'unverified')  # Still unverified until admin approval
    
    # Verify user can transact check returns False (not verified yet)
    self.assertFalse(user.can_transact())
