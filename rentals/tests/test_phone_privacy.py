"""
Counter-disintermediation: counterparty phone numbers must never appear in
user-facing rental responses (§ phone privacy).
"""

import json

from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from rentals.tests.factories import RentalFactory, RenterFactory


def auth_headers(user):
    refresh = RefreshToken.for_user(user)
    return {'HTTP_AUTHORIZATION': f'Bearer {refresh.access_token}'}


class RentalPhonePrivacyTest(TestCase):

    def setUp(self):
        self.renter = RenterFactory()
        self.rental = RentalFactory(renter=self.renter)
        self.owner = self.rental.owner

    def test_detail_response_contains_no_counterparty_phone(self):
        # Renter's view: owner's phone must not appear anywhere in the payload
        r = self.client.get(
            f'/api/rentals/{self.rental.pk}/', **auth_headers(self.renter)
        )
        self.assertEqual(r.status_code, 200)
        body = json.dumps(r.json())
        self.assertNotIn(self.owner.phone_number, body)
        self.assertIn('renter_info', r.json()['data'])
        self.assertIn('owner_info', r.json()['data'])

        # Owner's view: renter's phone must not appear anywhere in the payload
        r = self.client.get(
            f'/api/rentals/{self.rental.pk}/', **auth_headers(self.owner)
        )
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(self.renter.phone_number, json.dumps(r.json()))

    def test_list_response_contains_no_counterparty_phone(self):
        r = self.client.get('/api/rentals/my-rentals/', **auth_headers(self.renter))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(self.owner.phone_number, json.dumps(r.json()))
