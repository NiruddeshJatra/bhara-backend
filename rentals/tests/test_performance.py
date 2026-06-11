"""
Performance-regression tests: list endpoints must not fetch payment records.
"""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework_simplejwt.tokens import RefreshToken

from rentals.tests.factories import PaymentRecordFactory, RentalFactory, RenterFactory


def auth_headers(user):
    refresh = RefreshToken.for_user(user)
    return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}


class RentalListQueryTest(TestCase):

    def setUp(self):
        self.renter = RenterFactory()
        self.rental = RentalFactory(renter=self.renter)
        PaymentRecordFactory(rental=self.rental)

    def test_my_rentals_does_not_fetch_payment_records(self):
        """List serializer never reads payment_records — they must not be prefetched."""
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get('/api/rentals/my-rentals/', **auth_headers(self.renter))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(
            any('paymentrecord' in q['sql'].lower() for q in ctx.captured_queries),
            'my-rentals must not query payment records',
        )

    def test_detail_still_includes_payment_records(self):
        r = self.client.get(
            f'/api/rentals/{self.rental.pk}/', **auth_headers(self.renter)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['data']['payment_records']), 1)
