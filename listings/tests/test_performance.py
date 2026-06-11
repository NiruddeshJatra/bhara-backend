"""
Performance-regression tests: duplicate-row filters and windowed blocked-dates.
"""

from datetime import date, timedelta

from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from listings.models import UnavailablePeriod
from listings.services import get_blocked_dates
from listings.tests.factories import ProductFactory, PricingTierFactory
from rentals.tests.factories import RentalFactory


class PriceFilterDistinctTest(TestCase):
  """A product with several tiers matching a price filter must appear once."""

  def setUp(self):
    self.product = ProductFactory()
    PricingTierFactory(product=self.product, duration_unit='day', price=500)
    PricingTierFactory(product=self.product, duration_unit='week', price=3000)

  def test_min_price_no_duplicates(self):
    r = self.client.get('/api/listings/?min_price=100')
    self.assertEqual(r.status_code, 200)
    results = r.json()['data']['results']
    ids = [item['id'] for item in results]
    self.assertEqual(ids.count(str(self.product.pk)), 1)

  def test_max_price_no_duplicates(self):
    r = self.client.get('/api/listings/?max_price=10000')
    self.assertEqual(r.status_code, 200)
    results = r.json()['data']['results']
    ids = [item['id'] for item in results]
    self.assertEqual(ids.count(str(self.product.pk)), 1)


class BlockedDatesWindowTest(TestCase):
  """Windowed get_blocked_dates only expands rows overlapping the window."""

  def setUp(self):
    self.product = ProductFactory()
    self.window_start = date.today() + timedelta(days=10)
    self.window_end = self.window_start + timedelta(days=3)

  def test_rental_outside_window_not_expanded(self):
    # Rental far in the future, no overlap with the window
    far_start = date.today() + timedelta(days=100)
    RentalFactory(
      product=self.product,
      status='accepted',
      start_date=far_start,
      end_date=far_start + timedelta(days=5),
    )
    blocked = get_blocked_dates(self.product, start=self.window_start, end=self.window_end)
    self.assertEqual(blocked, set())

  def test_overlapping_rental_still_blocks(self):
    RentalFactory(
      product=self.product,
      status='accepted',
      start_date=self.window_start,
      end_date=self.window_start + timedelta(days=1),
    )
    blocked = get_blocked_dates(self.product, start=self.window_start, end=self.window_end)
    self.assertIn(self.window_start, blocked)
    self.assertIn(self.window_start + timedelta(days=1), blocked)

  def test_unavailable_period_single_day(self):
    # Within window
    in_date = self.window_start + timedelta(days=1)
    UnavailablePeriod.objects.create(
      product=self.product,
      is_range=False,
      date=in_date,
    )
    # Outside window
    out_date = self.window_start + timedelta(days=10)
    UnavailablePeriod.objects.create(
      product=self.product,
      is_range=False,
      date=out_date,
    )
    blocked = get_blocked_dates(self.product, start=self.window_start, end=self.window_end)
    self.assertIn(in_date, blocked)
    self.assertNotIn(out_date, blocked)

  def test_unavailable_period_ranges(self):
    # Fully outside window (future)
    UnavailablePeriod.objects.create(
      product=self.product,
      is_range=True,
      date=self.window_start + timedelta(days=10),
      range_start=self.window_start + timedelta(days=10),
      range_end=self.window_start + timedelta(days=12),
    )
    # Overlapping the window
    UnavailablePeriod.objects.create(
      product=self.product,
      is_range=True,
      date=self.window_start - timedelta(days=2),
      range_start=self.window_start - timedelta(days=2),
      range_end=self.window_start + timedelta(days=1),
    )
    blocked = get_blocked_dates(self.product, start=self.window_start, end=self.window_end)
    # The overlapping one blocks start_date - 2 to start_date + 1
    # Within the window [start_date, start_date + 3], start_date and start_date + 1 should be blocked.
    self.assertIn(self.window_start, blocked)
    self.assertIn(self.window_start + timedelta(days=1), blocked)
    # But start_date + 2 should not be blocked
    self.assertNotIn(self.window_start + timedelta(days=2), blocked)
    # The range fully outside window should not be blocked
    self.assertNotIn(self.window_start + timedelta(days=10), blocked)

  def test_no_window_keeps_full_history_behavior(self):
    far_start = date.today() + timedelta(days=100)
    RentalFactory(
      product=self.product,
      status='accepted',
      start_date=far_start,
      end_date=far_start + timedelta(days=2),
    )
    blocked = get_blocked_dates(self.product)
    self.assertIn(far_start, blocked)

  def test_windowed_query_filters_in_sql(self):
    """The rental fetch must carry the overlap filter, not fetch all rows."""
    far_start = date.today() + timedelta(days=100)
    RentalFactory(
      product=self.product,
      status='accepted',
      start_date=far_start,
      end_date=far_start + timedelta(days=5),
    )
    with CaptureQueriesContext(connection) as ctx:
      get_blocked_dates(self.product, start=self.window_start, end=self.window_end)
    rental_queries = [q['sql'] for q in ctx.captured_queries if 'rentals_rental' in q['sql']]
    self.assertTrue(rental_queries)
    sql = rental_queries[0]
    self.assertIn('start_date', sql)
    self.assertIn('end_date', sql)
    # Check for the overlap operators
    self.assertIn('<=', sql)
    self.assertIn('>=', sql)
