"""
Owner-side SMS notification: enqueued via transaction.on_commit when a rental
is created (status=pending) — and ONLY then. No notification on accept/reject.
"""

from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from listings.tests.factories import PricingTierFactory, ProductFactory
from rentals.tests.factories import RentalFactory, RenterFactory
from users.tests.factories import VerifiedUserFactory


def auth_headers(user):
    refresh = RefreshToken.for_user(user)
    return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}


class RentalRequestSMSTest(TestCase):

    def setUp(self):
        self.renter = VerifiedUserFactory()
        self.product = ProductFactory(title='A' * 50)  # long title — must be truncated
        PricingTierFactory(
            product=self.product, duration_unit='day', price=500, max_period=30
        )

    @patch('celery_tasks.rentals.send_rental_request_sms.delay')
    def test_task_enqueued_on_create_after_commit(self, mock_delay):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                '/api/rentals/',
                {
                    'product': str(self.product.pk),
                    'start_date': (date.today() + timedelta(days=5)).isoformat(),
                    'duration': 3,
                    'duration_unit': 'day',
                    'purpose': 'personal',
                },
                content_type='application/json',
                **auth_headers(self.renter),
            )
        self.assertEqual(response.status_code, 201, response.json())
        mock_delay.assert_called_once_with(
            self.product.owner.phone_number, 'A' * 30
        )

    @patch('celery_tasks.rentals.send_rental_request_sms.delay')
    def test_task_not_enqueued_on_accept_or_reject(self, mock_delay):
        accept_rental = RentalFactory(status='pending')
        with self.captureOnCommitCallbacks(execute=True):
            accept_rental.transition('accepted', accept_rental.owner)

        reject_rental = RentalFactory(status='pending', renter=RenterFactory())
        with self.captureOnCommitCallbacks(execute=True):
            reject_rental.transition('rejected', reject_rental.owner)

        mock_delay.assert_not_called()
