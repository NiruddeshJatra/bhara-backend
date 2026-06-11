from datetime import timedelta

import factory
from django.utils import timezone

from rentals.tests.factories import RentalFactory, RenterFactory
from reviews.models import Review


class CompletedRentalFactory(RentalFactory):
    """RentalFactory with status=completed and proper status_history."""
    status = 'completed'
    status_history = factory.LazyFunction(lambda: [
        {
            'status': 'pending',
            'timestamp': (timezone.now() - timedelta(days=2)).isoformat(),
            'actor_id': None,
            'note': '',
        },
        {
            'status': 'completed',
            'timestamp': timezone.now().isoformat(),
            'actor_id': None,
            'note': '',
        },
    ])


class ReviewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Review

    rental = factory.SubFactory(CompletedRentalFactory)
    reviewer = factory.LazyAttribute(lambda o: o.rental.renter)
    reviewee = factory.LazyAttribute(lambda o: o.rental.owner)
    product = factory.LazyAttribute(lambda o: o.rental.product)
    direction = 'renter_to_owner'
    rating = 4
    comment = 'Good experience'
