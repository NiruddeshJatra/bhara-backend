"""
Status re-check under lock: a stale in-memory Rental instance must not
apply a transition twice or bypass the matrix (concurrent-request guard).
"""

from django.test import TestCase

from rentals.models import Rental
from rentals.state_machine import TransitionError
from rentals.tests.factories import RentalFactory


class StaleInstanceTransitionTest(TestCase):

    def setUp(self):
        self.rental = RentalFactory(status='pending')
        self.owner = self.rental.owner

    def test_stale_instance_cannot_reapply_transition(self):
        stale = Rental.objects.get(pk=self.rental.pk)  # second in-memory copy

        self.rental.transition('accepted', self.owner)

        with self.assertRaises(TransitionError):
            stale.transition('accepted', self.owner)  # still thinks 'pending'

        self.rental.refresh_from_db()
        # Exactly one 'accepted' entry — the stale copy must not append another
        accepted_entries = [
            e for e in self.rental.status_history if e['status'] == 'accepted'
        ]
        self.assertEqual(len(accepted_entries), 1)

    def test_stale_instance_cannot_bypass_matrix(self):
        stale = Rental.objects.get(pk=self.rental.pk)
        self.rental.transition('rejected', self.owner)

        # 'rejected' is terminal; the stale copy still sees 'pending' and
        # would otherwise walk pending→accepted on a finished rental
        with self.assertRaises(TransitionError):
            stale.transition('accepted', self.owner)

        self.rental.refresh_from_db()
        self.assertEqual(self.rental.status, 'rejected')
