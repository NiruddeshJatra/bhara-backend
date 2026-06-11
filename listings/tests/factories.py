import factory

from listings.models import Product, PricingTier
from users.tests.factories import VerifiedUserFactory


class ProductFactory(factory.django.DjangoModelFactory):
  class Meta:
    model = Product

  owner = factory.SubFactory(VerifiedUserFactory)
  title = factory.Sequence(lambda n: f'Canon DSLR {n}')
  category = 'photography_videography'
  product_type = 'camera'
  description = 'A well-maintained camera.'
  location = 'Dhaka'
  security_deposit = 1000
  purchase_year = '2023'
  original_price = 50000
  ownership_history = 'firsthand'
  status = 'active'


class PricingTierFactory(factory.django.DjangoModelFactory):
  class Meta:
    model = PricingTier

  product = factory.SubFactory(ProductFactory)
  duration_unit = 'day'
  price = 500
  max_period = 30
