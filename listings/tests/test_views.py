import json
import os
from datetime import date
from io import BytesIO

from django.test import TestCase
from PIL import Image
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.files.uploadedfile import SimpleUploadedFile

from listings.models import Product, UnavailablePeriod
from listings.tests.factories import ProductFactory, PricingTierFactory
from users.tests.factories import UserFactory, VerifiedUserFactory


def make_image(name='test.jpg', size=(400, 400), fmt='JPEG'):
  image = Image.new('RGB', size, 'red')
  buffer = BytesIO()
  image.save(buffer, format=fmt)
  buffer.seek(0)
  content_type = 'image/png' if fmt == 'PNG' else 'image/jpeg'
  return SimpleUploadedFile(name, buffer.read(), content_type=content_type)


def make_oversize_image(name='big.png'):
  """Real PNG of random noise — incompressible, lands well above 5MB."""
  noise = Image.frombytes('RGB', (1500, 1500), os.urandom(1500 * 1500 * 3))
  buffer = BytesIO()
  noise.save(buffer, format='PNG')
  buffer.seek(0)
  return SimpleUploadedFile(name, buffer.read(), content_type='image/png')


def auth_headers(user):
  refresh = RefreshToken.for_user(user)
  return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}


class ListingVisibilityTest(TestCase):
  """§3.2 — drafts/suspended invisible publicly, visible in my_products."""

  def setUp(self):
    self.owner = VerifiedUserFactory()
    self.active = ProductFactory(owner=self.owner, status='active')
    self.draft = ProductFactory(owner=self.owner, status='draft')
    self.suspended = ProductFactory(owner=self.owner, status='suspended')

  def test_anonymous_list_sees_only_active(self):
    response = self.client.get('/api/listings/')
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    results = response.json()['data']['results']
    ids = [item['id'] for item in results]
    self.assertEqual(ids, [str(self.active.id)])

  def test_authenticated_non_owner_list_sees_only_active(self):
    other = VerifiedUserFactory()
    response = self.client.get('/api/listings/', **auth_headers(other))
    ids = [item['id'] for item in response.json()['data']['results']]
    self.assertEqual(ids, [str(self.active.id)])

  def test_anonymous_cannot_retrieve_draft(self):
    response = self.client.get(f'/api/listings/{self.draft.id}/')
    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

  def test_anonymous_cannot_retrieve_suspended(self):
    response = self.client.get(f'/api/listings/{self.suspended.id}/')
    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

  def test_non_owner_cannot_retrieve_draft(self):
    other = VerifiedUserFactory()
    response = self.client.get(f'/api/listings/{self.draft.id}/', **auth_headers(other))
    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

  def test_owner_my_products_shows_all_statuses(self):
    response = self.client.get('/api/listings/my_products/', **auth_headers(self.owner))
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    statuses = sorted(item['status'] for item in response.json()['data']['results'])
    self.assertEqual(statuses, ['active', 'draft', 'suspended'])

  def test_my_products_requires_authentication(self):
    response = self.client.get('/api/listings/my_products/')
    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

  def test_my_products_excludes_other_owners_products(self):
    other = VerifiedUserFactory()
    ProductFactory(owner=other)
    response = self.client.get('/api/listings/my_products/', **auth_headers(self.owner))
    self.assertEqual(len(response.json()['data']['results']), 3)

  def test_owner_cannot_retrieve_own_draft_via_detail(self):
    """retrieve queryset filters to status=active — even owners get 404 on their drafts."""
    response = self.client.get(f'/api/listings/{self.draft.id}/', **auth_headers(self.owner))
    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

  def test_views_count_increments_for_non_owner(self):
    other = VerifiedUserFactory()
    before = self.active.views_count
    self.client.get(f'/api/listings/{self.active.id}/', **auth_headers(other))
    self.active.refresh_from_db()
    self.assertEqual(self.active.views_count, before + 1)

  def test_views_count_not_incremented_for_owner(self):
    before = self.active.views_count
    self.client.get(f'/api/listings/{self.active.id}/', **auth_headers(self.owner))
    self.active.refresh_from_db()
    self.assertEqual(self.active.views_count, before)


class ListingCreateTest(TestCase):
  """§3.2 create permission + §3.3 serializer validation."""

  def _payload(self, **overrides):
    payload = {
      'title': 'Sony A7 III',
      'category': 'photography_videography',
      'product_type': 'camera',
      'description': 'Full-frame mirrorless.',
      'location': 'Dhaka',
      'security_deposit': '2000',
      'purchase_year': '2023',
      'original_price': '150000',
      'ownership_history': 'firsthand',
      'images': [make_image()],
      'pricing_tiers': json.dumps([{'duration_unit': 'day', 'price': 800, 'max_period': 15}]),
    }
    payload.update(overrides)
    return payload

  def test_anonymous_create_rejected(self):
    response = self.client.post('/api/listings/', self._payload())
    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

  def test_create_rejected_when_can_transact_false(self):
    unverified = UserFactory()  # profile_completed=False, trust_level='unverified'
    response = self.client.post('/api/listings/', self._payload(), **auth_headers(unverified))
    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    self.assertFalse(response.json()['success'])
    self.assertEqual(Product.objects.count(), 0)

  def test_verified_user_create_publishes_directly_to_active(self):
    user = VerifiedUserFactory()
    response = self.client.post('/api/listings/', self._payload(), **auth_headers(user))
    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    data = response.json()['data']
    self.assertEqual(data['status'], 'active')
    self.assertEqual(len(data['images']), 1)
    self.assertEqual(len(data['pricing_tiers']), 1)
    product = Product.objects.get(id=data['id'])
    self.assertEqual(product.owner, user)

  def test_create_requires_at_least_one_image(self):
    user = VerifiedUserFactory()
    payload = self._payload()
    del payload['images']
    response = self.client.post('/api/listings/', payload, **auth_headers(user))
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('images', response.json()['data'])

  def test_create_rejects_more_than_8_images(self):
    user = VerifiedUserFactory()
    payload = self._payload(images=[make_image(f'img{i}.jpg') for i in range(9)])
    response = self.client.post('/api/listings/', payload, **auth_headers(user))
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('images', response.json()['data'])

  def test_create_rejects_image_over_5mb(self):
    user = VerifiedUserFactory()
    payload = self._payload(images=[make_oversize_image()])
    response = self.client.post('/api/listings/', payload, **auth_headers(user))
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('images', response.json()['data'])

  def test_create_rejects_non_jpeg_png_image(self):
    user = VerifiedUserFactory()
    payload = self._payload(images=[make_image('anim.gif', fmt='GIF')])
    response = self.client.post('/api/listings/', payload, **auth_headers(user))
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

  def test_create_requires_pricing_tier(self):
    user = VerifiedUserFactory()
    payload = self._payload()
    del payload['pricing_tiers']
    response = self.client.post('/api/listings/', payload, **auth_headers(user))
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('pricing_tiers', response.json()['data'])


class AvailabilityFilterTest(TestCase):
  """§3.3 — availability filter excludes owner UnavailablePeriods."""

  def setUp(self):
    self.free = ProductFactory(title='Free product')
    PricingTierFactory(product=self.free)

    self.single_blocked = ProductFactory(title='Single-date blocked')
    PricingTierFactory(product=self.single_blocked)
    UnavailablePeriod.objects.create(
      product=self.single_blocked, date=date(2026, 7, 10)
    )

    self.range_blocked = ProductFactory(title='Range blocked')
    PricingTierFactory(product=self.range_blocked)
    UnavailablePeriod.objects.create(
      product=self.range_blocked,
      date=date(2026, 7, 5),
      is_range=True,
      range_start=date(2026, 7, 5),
      range_end=date(2026, 7, 15),
    )

    self.blocked_elsewhere = ProductFactory(title='Blocked outside window')
    PricingTierFactory(product=self.blocked_elsewhere)
    UnavailablePeriod.objects.create(
      product=self.blocked_elsewhere, date=date(2026, 7, 1)
    )

  def _ids(self, response):
    return {item['id'] for item in response.json()['data']['results']}

  def test_filter_excludes_products_with_overlapping_unavailable_periods(self):
    response = self.client.get('/api/listings/?start_date=2026-07-10&end_date=2026-07-12')
    self.assertEqual(response.status_code, status.HTTP_200_OK)
    ids = self._ids(response)
    self.assertIn(str(self.free.id), ids)
    self.assertIn(str(self.blocked_elsewhere.id), ids)
    self.assertNotIn(str(self.single_blocked.id), ids)
    self.assertNotIn(str(self.range_blocked.id), ids)

  def test_filter_with_only_start_date(self):
    response = self.client.get('/api/listings/?start_date=2026-07-10')
    ids = self._ids(response)
    self.assertNotIn(str(self.single_blocked.id), ids)
    self.assertNotIn(str(self.range_blocked.id), ids)
    self.assertIn(str(self.free.id), ids)

  def test_no_filter_returns_all_active(self):
    response = self.client.get('/api/listings/')
    self.assertEqual(len(self._ids(response)), 4)
