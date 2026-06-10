import factory
from users.models import User


class UserFactory(factory.django.DjangoModelFactory):
  class Meta:
    model = User
    skip_postgeneration_save = True

  # Keep deterministic + unique across the whole test session.
  phone_number = factory.Sequence(lambda n: f'019{n:08d}')
  full_name = factory.Faker('name')
  is_active = True
  profile_completed = False
  trust_level = 'unverified'
  is_approved = None

  @factory.post_generation
  def set_password_postgen(self, create, extracted, **kwargs):
    self.set_password(extracted or 'testpass123')
    if create:
      self.save()


class VerifiedUserFactory(UserFactory):
  profile_completed = True
  trust_level = 'verified'
  is_approved = True
  district = 'Dhaka'
  thana = 'Mirpur'
  full_address = 'House 5, Road 3, Mirpur-10'
  date_of_birth = factory.LazyFunction(lambda: __import__('datetime').date(1995, 1, 1))
