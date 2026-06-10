from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from io import BytesIO
from PIL import Image
from users.serializers import (
  OTPRequestSerializer, OTPVerifySerializer, SignupCompleteSerializer,
  LoginSerializer, PasswordResetCompleteSerializer, ProfileStep1Serializer,
  ProfileStep2Serializer, UserProfileSerializer, UpdateFullNameSerializer
)
from users.tests.factories import UserFactory, VerifiedUserFactory


class OTPRequestSerializerTest(TestCase):
  def test_valid_signup_request(self):
    """Test valid OTP request for signup."""
    data = {
      'phone_number': '01712345678',
      'purpose': 'signup'
    }
    serializer = OTPRequestSerializer(data=data)
    self.assertTrue(serializer.is_valid())

  def test_valid_password_reset_request(self):
    """Test valid OTP request for password reset."""
    user = UserFactory(phone_number='01712345678')
    data = {
      'phone_number': '01712345678',
      'purpose': 'password_reset'
    }
    serializer = OTPRequestSerializer(data=data)
    self.assertTrue(serializer.is_valid())

  def test_signup_fails_with_existing_phone(self):
    """Test signup request fails with existing phone number."""
    UserFactory(phone_number='01712345678')
    data = {
      'phone_number': '01712345678',
      'purpose': 'signup'
    }
    serializer = OTPRequestSerializer(data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('phone_number', serializer.errors)

  def test_password_reset_fails_with_nonexistent_phone(self):
    """Test password reset request fails with non-existent phone."""
    data = {
      'phone_number': '01712345678',
      'purpose': 'password_reset'
    }
    serializer = OTPRequestSerializer(data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('phone_number', serializer.errors)

  def test_invalid_phone_number(self):
    """Test invalid phone number format."""
    data = {
      'phone_number': '123456789',
      'purpose': 'signup'
    }
    serializer = OTPRequestSerializer(data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('phone_number', serializer.errors)


class OTPVerifySerializerTest(TestCase):
  def test_valid_tp_verification(self):
    """Test valid OTP verification data."""
    data = {
      'phone_number': '01712345678',
      'otp': '123456',
      'purpose': 'signup'
    }
    serializer = OTPVerifySerializer(data=data)
    self.assertTrue(serializer.is_valid())

  def test_invalid_otp_length(self):
    """Test invalid OTP length."""
    data = {
      'phone_number': '01712345678',
      'otp': '12345',
      'purpose': 'signup'
    }
    serializer = OTPVerifySerializer(data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('otp', serializer.errors)


class SignupCompleteSerializerTest(TestCase):
  def test_valid_signup_data(self):
    """Test valid signup completion data."""
    data = {
      'full_name': 'John Doe',
      'password': 'Testpass123',
      'marketing_consent': False
    }
    serializer = SignupCompleteSerializer(data=data)
    self.assertTrue(serializer.is_valid())

  def test_weak_password_validation(self):
    """Test weak password validation."""
    data = {
      'full_name': 'John Doe',
      'password': 'weak',
      'marketing_consent': False
    }
    serializer = SignupCompleteSerializer(data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('password', serializer.errors)

  def test_empty_full_name_validation(self):
    """Test empty full name validation."""
    data = {
      'full_name': '   ',
      'password': 'Testpass123',
      'marketing_consent': False
    }
    serializer = SignupCompleteSerializer(data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('full_name', serializer.errors)


class LoginSerializerTest(TestCase):
  def test_valid_login_data(self):
    """Test valid login data."""
    data = {
      'phone_number': '01712345678',
      'password': 'testpass123'
    }
    serializer = LoginSerializer(data=data)
    self.assertTrue(serializer.is_valid())


class PasswordResetCompleteSerializerTest(TestCase):
  def test_valid_password_reset(self):
    """Test valid password reset data."""
    data = {
      'password': 'Newpass123'
    }
    serializer = PasswordResetCompleteSerializer(data=data)
    self.assertTrue(serializer.is_valid())

  def test_weak_password_reset(self):
    """Test weak password in reset."""
    data = {
      'password': 'weak'
    }
    serializer = PasswordResetCompleteSerializer(data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('password', serializer.errors)


class ProfileStep1SerializerTest(TestCase):
  def test_valid_profile_step1_data(self):
    """Test valid profile step 1 data."""
    user = UserFactory()
    data = {
      'date_of_birth': '1995-01-01',
      'district': 'Dhaka',
      'thana': 'Mirpur',
      'full_address': 'House 5, Road 3, Mirpur-10',
      'email': 'test@example.com'
    }
    serializer = ProfileStep1Serializer(data=data)
    self.assertTrue(serializer.is_valid())

  def test_under_18_validation(self):
    """Test under 18 date of birth validation."""
    data = {
      'date_of_birth': '2010-01-01',  # Under 18
      'district': 'Dhaka',
      'thana': 'Mirpur',
      'full_address': 'House 5, Road 3, Mirpur-10'
    }
    serializer = ProfileStep1Serializer(data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('date_of_birth', serializer.errors)

  def test_required_fields_validation(self):
    """Test required fields validation."""
    data = {
      'date_of_birth': '1995-01-01'
      # Missing district, thana, full_address
    }
    serializer = ProfileStep1Serializer(data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('district', serializer.errors)
    self.assertIn('thana', serializer.errors)
    self.assertIn('full_address', serializer.errors)

  def test_empty_field_validation(self):
    """Test empty field validation."""
    data = {
      'date_of_birth': '1995-01-01',
      'district': '   ',  # Empty after strip
      'thana': 'Mirpur',
      'full_address': 'House 5, Road 3, Mirpur-10'
    }
    serializer = ProfileStep1Serializer(data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('district', serializer.errors)


class ProfileStep2SerializerTest(TestCase):
  @staticmethod
  def _fake_image():
    buffer = BytesIO()
    Image.new('RGB', (10, 10), 'white').save(buffer, format='JPEG')
    buffer.seek(0)
    return SimpleUploadedFile(
      'nid.jpg',
      buffer.read(),
      content_type='image/jpeg'
    )

  def test_valid_profile_step2_data(self):
    """Test valid profile step 2 data."""
    data = {
      'nid_number': '1234567890',
      'nid_image': self._fake_image()
    }
    serializer = ProfileStep2Serializer(data=data)
    self.assertTrue(serializer.is_valid())

  def test_empty_nid_number_validation(self):
    """Test empty NID number validation."""
    data = {
      'nid_number': '   ',  # Empty after strip
      'nid_image': self._fake_image()
    }
    serializer = ProfileStep2Serializer(data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('nid_number', serializer.errors)

  def test_missing_nid_image_validation(self):
    """Test missing NID image validation."""
    data = {
      'nid_number': '1234567890'
    }
    serializer = ProfileStep2Serializer(data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('nid_image', serializer.errors)


class UserProfileSerializerTest(TestCase):
  def test_user_profile_serialization(self):
    """Test user profile serialization."""
    user = VerifiedUserFactory()
    serializer = UserProfileSerializer(user)
    data = serializer.data
    
    self.assertEqual(data['id'], str(user.id))
    self.assertEqual(data['phone_number'], user.phone_number)
    self.assertEqual(data['full_name'], user.full_name)
    self.assertEqual(data['trust_level'], user.trust_level)
    self.assertEqual(data['trust_badge'], 'verified')
    self.assertTrue(data['profile_completed'])

  def test_trust_badge_logic(self):
    """Test trust badge logic."""
    # Unverified user
    user = UserFactory()
    serializer = UserProfileSerializer(user)
    self.assertIsNone(serializer.data['trust_badge'])
    
    # Verified user
    verified_user = VerifiedUserFactory()
    serializer = UserProfileSerializer(verified_user)
    self.assertEqual(serializer.data['trust_badge'], 'verified')
    
    # Partner user
    partner_user = UserFactory(trust_level='partner')
    serializer = UserProfileSerializer(partner_user)
    self.assertEqual(serializer.data['trust_badge'], 'partner')


class UpdateFullNameSerializerTest(TestCase):
  def test_valid_name_update(self):
    """Test valid name update."""
    user = UserFactory()
    data = {'full_name': 'New Name'}
    serializer = UpdateFullNameSerializer(instance=user, data=data)
    self.assertTrue(serializer.is_valid())

  def test_empty_name_validation(self):
    """Test empty name validation."""
    user = UserFactory()
    data = {'full_name': '   '}
    serializer = UpdateFullNameSerializer(instance=user, data=data)
    self.assertFalse(serializer.is_valid())
    self.assertIn('full_name', serializer.errors)
