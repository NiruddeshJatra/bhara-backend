from django.test import TestCase
from users.models import User
from users.tests.factories import UserFactory, VerifiedUserFactory


class UserModelTest(TestCase):
  def test_user_str(self):
    """Test __str__ returns correct format."""
    user = UserFactory(full_name='John Doe', phone_number='01712345678')
    self.assertEqual(str(user), 'John Doe (01712345678)')

  def test_create_user_requires_phone(self):
    """Test that phone number is required for user creation."""
    with self.assertRaises(ValueError):
      User.objects.create_user(phone_number='', full_name='John Doe')

  def test_create_user_requires_full_name(self):
    """Test that full name is required for user creation."""
    with self.assertRaises(ValueError):
      User.objects.create_user(phone_number='01712345678', full_name='')

  def test_create_superuser_sets_is_staff(self):
    """Test that superuser creation sets is_staff and is_superuser."""
    user = User.objects.create_superuser(
      phone_number='01712345678',
      full_name='Admin User',
      password='adminpass123'
    )
    self.assertTrue(user.is_staff)
    self.assertTrue(user.is_superuser)
    self.assertEqual(user.trust_level, 'partner')

  def test_can_transact_returns_false_for_unverified(self):
    """Test that unverified users cannot transact."""
    user = UserFactory()
    self.assertFalse(user.can_transact())

  def test_can_transact_returns_true_for_verified_and_profile_completed(self):
    """Test that verified users with completed profiles can transact."""
    user = VerifiedUserFactory()
    self.assertTrue(user.can_transact())

  def test_trust_level_default_is_unverified(self):
    """Test that default trust level is unverified."""
    user = UserFactory()
    self.assertEqual(user.trust_level, 'unverified')
