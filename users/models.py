from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from uuid import uuid4
from .managers import UserManager

# Trust Level Choices
TRUST_LEVEL_UNVERIFIED = 'unverified'
TRUST_LEVEL_VERIFIED = 'verified'
TRUST_LEVEL_PARTNER = 'partner'

TRUST_LEVEL_CHOICES = [
  (TRUST_LEVEL_UNVERIFIED, 'Unverified'),
  (TRUST_LEVEL_VERIFIED, 'Verified'),
  (TRUST_LEVEL_PARTNER, 'Bhara Partner'),
]


class User(AbstractBaseUser, PermissionsMixin):
  # --- Primary Key ---
  id = models.UUIDField(
    primary_key=True,
    default=uuid4,
    editable=False
  )

  # --- Auth Fields ---
  phone_number = models.CharField(
    max_length=15,
    unique=True,
    db_index=True,
    help_text='Bangladeshi phone number (01XXXXXXXXX). Used as login identifier.'
  )
  full_name = models.CharField(
    max_length=150,
    help_text='Display name shown on listings and profile.'
  )

  # --- Status Flags ---
  is_active = models.BooleanField(default=True)
  is_staff = models.BooleanField(default=False)
  profile_completed = models.BooleanField(
    default=False,
    help_text='True after Step 1 of profile completion is submitted.'
  )
  marketing_consent = models.BooleanField(
    default=False,
    help_text='User opted in to marketing communications.'
  )

  # --- Trust System ---
  trust_level = models.CharField(
    max_length=20,
    choices=TRUST_LEVEL_CHOICES,
    default=TRUST_LEVEL_UNVERIFIED,
    help_text='unverified | verified | partner'
  )
  is_approved = models.BooleanField(
    null=True,
    default=None,
    help_text=(
      'None = no documents submitted or pending review. '
      'True = admin approved. False = admin rejected.'
    )
  )

  # --- Profile Step 1 Fields ---
  profile_picture = models.ImageField(
    upload_to='profile_pictures/',
    null=True,
    blank=True
  )
  date_of_birth = models.DateField(
    null=True,
    blank=True,
    help_text='Must be 18+ years old.'
  )
  district = models.CharField(
    max_length=100,
    blank=True,
    help_text='Selected from BD district list.'
  )
  thana = models.CharField(
    max_length=100,
    blank=True,
    help_text='Selected from thanas under chosen district.'
  )
  full_address = models.TextField(
    blank=True,
    help_text='Free-text full address after district/thana selection.'
  )
  email = models.EmailField(
    null=True,
    blank=True,
    help_text='Optional. Collected during profile completion. Not used for login.'
  )

  # --- Profile Step 2 Fields (Identity Verification) ---
  nid_number = models.CharField(
    max_length=20,
    null=True,
    blank=True,
    help_text='NID number typed by user. No format enforcement — admin visually verifies.'
  )
  nid_image = models.ImageField(
    upload_to='identity/nid/',
    null=True,
    blank=True,
    help_text='Photo of govt ID (NID front, passport, or driving license).'
  )
  institutional_id_image = models.ImageField(
    upload_to='identity/institutional/',
    null=True,
    blank=True,
    help_text='Optional. University or office ID photo.'
  )

  # --- Stats ---
  average_rating = models.DecimalField(
    max_digits=3,
    decimal_places=2,
    default=0.00,
    editable=False
  )

  # --- Timestamps ---
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  objects = UserManager()

  USERNAME_FIELD = 'phone_number'
  REQUIRED_FIELDS = ['full_name']

  class Meta:
    ordering = ['-created_at']
    verbose_name = 'User'
    verbose_name_plural = 'Users'

  def __str__(self):
    return f'{self.full_name} ({self.phone_number})'

  def can_transact(self):
    """Returns True if user can rent or list items."""
    return self.profile_completed and self.trust_level in [
      TRUST_LEVEL_VERIFIED,
      TRUST_LEVEL_PARTNER,
    ]

  def has_completed_transactions(self):
    """Used to gate name changes. Import inline to avoid circular imports."""
    try:
        from rentals.models import Rental
        return Rental.objects.filter(
            user=self, status='completed'
        ).exists()
    except ModuleNotFoundError:
        return False
