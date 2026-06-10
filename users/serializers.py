from rest_framework import serializers
from users.validators import validate_bd_phone, validate_password_strength, validate_age_18
from users.models import User
from users.utils import compress_image


class OTPRequestSerializer(serializers.Serializer):
  phone_number = serializers.CharField(max_length=15)
  purpose = serializers.ChoiceField(choices=['signup', 'password_reset'])

  def validate_phone_number(self, value):
    return validate_bd_phone(value)

  def validate(self, data):
    phone = data['phone_number']
    purpose = data['purpose']
    if purpose == 'signup':
      if User.objects.filter(phone_number=phone).exists():
        raise serializers.ValidationError({
          'phone_number': ['An account with this phone number already exists.']
        })
    elif purpose == 'password_reset':
      if not User.objects.filter(phone_number=phone).exists():
        raise serializers.ValidationError({
          'phone_number': ['No account found with this phone number.']
        })
    return data


class OTPVerifySerializer(serializers.Serializer):
  phone_number = serializers.CharField(max_length=15)
  otp = serializers.CharField(min_length=6, max_length=6)
  purpose = serializers.ChoiceField(choices=['signup', 'password_reset'])

  def validate_phone_number(self, value):
    return validate_bd_phone(value)


class SignupCompleteSerializer(serializers.Serializer):
  full_name = serializers.CharField(min_length=2, max_length=150)
  password = serializers.CharField(write_only=True)
  marketing_consent = serializers.BooleanField(default=False)

  def validate_password(self, value):
    return validate_password_strength(value)

  def validate_full_name(self, value):
    if not value.strip():
      raise serializers.ValidationError('Full name cannot be blank.')
    return value.strip()


class LoginSerializer(serializers.Serializer):
  phone_number = serializers.CharField(max_length=15)
  password = serializers.CharField(write_only=True)

  def validate_phone_number(self, value):
    return validate_bd_phone(value)


class PasswordResetCompleteSerializer(serializers.Serializer):
  password = serializers.CharField(write_only=True)

  def validate_password(self, value):
    return validate_password_strength(value)


class ProfileStep1Serializer(serializers.ModelSerializer):
  class Meta:
    model = User
    fields = [
      'profile_picture',
      'date_of_birth',
      'district',
      'thana',
      'full_address',
      'email',
    ]

  def validate_date_of_birth(self, value):
    return validate_age_18(value)

  def validate_district(self, value):
    if not value.strip():
      raise serializers.ValidationError('District is required.')
    return value.strip()

  def validate_thana(self, value):
    if not value.strip():
      raise serializers.ValidationError('Thana is required.')
    return value.strip()

  def validate_full_address(self, value):
    if not value.strip():
      raise serializers.ValidationError('Full address is required.')
    return value.strip()

  def validate(self, data):
    required = ['date_of_birth', 'district', 'thana', 'full_address']
    errors = {}
    for field in required:
      if not data.get(field):
        errors[field] = [f'{field.replace("_", " ").title()} is required.']
    if errors:
      raise serializers.ValidationError(errors)
    return data

  def update(self, instance, validated_data):
    for attr, value in validated_data.items():
      setattr(instance, attr, value)
    instance.profile_completed = True
    instance.save()
    return instance


class ProfileStep2Serializer(serializers.ModelSerializer):
  nid_image = serializers.ImageField(required=True)
  
  class Meta:
    model = User
    fields = [
      'nid_number',
      'nid_image',
      'institutional_id_image',
    ]

  def validate_nid_number(self, value):
    if not value.strip():
      raise serializers.ValidationError('NID number is required.')
    return value.strip()

  def validate_nid_image(self, value):
    if value is None:
      raise serializers.ValidationError('NID image is required.')
    if value.size > 10 * 1024 * 1024:
      raise serializers.ValidationError('Image must be under 10MB.')
    return value

  def update(self, instance, validated_data):
    for attr, value in validated_data.items():
      setattr(instance, attr, value)
    # Set pending state
    instance.is_approved = None
    instance.save()
    return instance


class UserProfileSerializer(serializers.ModelSerializer):
  trust_badge = serializers.SerializerMethodField()
  member_since = serializers.SerializerMethodField()

  class Meta:
    model = User
    fields = [
      'id',
      'phone_number',
      'full_name',
      'email',
      'profile_picture',
      'date_of_birth',
      'district',
      'thana',
      'full_address',
      'trust_level',
      'trust_badge',
      'is_approved',
      'profile_completed',
      'average_rating',
      'marketing_consent',
      'member_since',
      'created_at',
    ]
    read_only_fields = fields

  def get_trust_badge(self, obj):
    if obj.trust_level == 'partner':
      return 'partner'
    if obj.trust_level == 'verified':
      return 'verified'
    return None

  def get_member_since(self, obj):
    return obj.created_at.strftime('%B %Y')


class UpdateFullNameSerializer(serializers.ModelSerializer):
  class Meta:
    model = User
    fields = ['full_name']

  def validate_full_name(self, value):
    if not value.strip():
      raise serializers.ValidationError('Full name cannot be blank.')
    return value.strip()

  def validate(self, data):
    user = self.instance
    if user.has_completed_transactions():
      raise serializers.ValidationError(
        'Name cannot be changed after completing a transaction.'
      )
    return data
