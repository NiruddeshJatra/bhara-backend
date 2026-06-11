from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from listings.tests.factories import ProductFactory
from rentals.tests.factories import RentalFactory, RenterFactory
from reviews.models import Review
from users.tests.factories import VerifiedUserFactory


def auth_headers(user):
    return {'HTTP_AUTHORIZATION': f'Bearer {AccessToken.for_user(user)}'}


def make_completed_rental(*, renter=None, owner=None, completed_days_ago=0):
    """Helper: completed rental with correct status_history timestamp."""
    completed_at = timezone.now() - timedelta(days=completed_days_ago)
    kwargs = {
        'status': 'completed',
        'status_history': [
            {
                'status': 'pending',
                'timestamp': (completed_at - timedelta(days=1)).isoformat(),
                'actor_id': None,
                'note': '',
            },
            {
                'status': 'completed',
                'timestamp': completed_at.isoformat(),
                'actor_id': None,
                'note': '',
            },
        ],
    }
    if renter:
        kwargs['renter'] = renter
    if owner:
        product = ProductFactory(owner=owner)
        kwargs['product'] = product
        kwargs['owner'] = owner
    return RentalFactory(**kwargs)


# ---------------------------------------------------------------------------
# Create rules
# ---------------------------------------------------------------------------

class TestReviewCreate(TestCase):

    def setUp(self):
        self.rental = make_completed_rental()
        self.renter = self.rental.renter
        self.owner = self.rental.owner
        self.url = '/api/reviews/'

    def _post(self, user, rental_id, rating=4, comment=''):
        return self.client.post(
            self.url,
            {'rental': str(rental_id), 'rating': rating, 'comment': comment},
            content_type='application/json',
            **auth_headers(user),
        )

    def test_renter_review_derives_renter_to_owner(self):
        r = self._post(self.renter, self.rental.pk, rating=5)
        self.assertEqual(r.status_code, 201)
        review = Review.objects.get(rental=self.rental, reviewer=self.renter)
        self.assertEqual(review.direction, 'renter_to_owner')
        self.assertEqual(review.reviewee, self.owner)
        self.assertEqual(review.product, self.rental.product)

    def test_owner_review_derives_owner_to_renter(self):
        r = self._post(self.owner, self.rental.pk, rating=3)
        self.assertEqual(r.status_code, 201)
        review = Review.objects.get(rental=self.rental, reviewer=self.owner)
        self.assertEqual(review.direction, 'owner_to_renter')
        self.assertEqual(review.reviewee, self.renter)

    def test_non_participant_rejected(self):
        stranger = VerifiedUserFactory()
        r = self._post(stranger, self.rental.pk)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Review.objects.filter(rental=self.rental).exists())

    def test_non_completed_rental_rejected(self):
        pending = RentalFactory(status='pending')
        r = self._post(pending.renter, pending.pk)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Review.objects.filter(rental=pending).exists())

    def test_duplicate_review_rejected(self):
        Review.objects.create(
            rental=self.rental,
            reviewer=self.renter,
            reviewee=self.owner,
            product=self.rental.product,
            direction='renter_to_owner',
            rating=5,
        )
        r = self._post(self.renter, self.rental.pk, rating=3)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            Review.objects.filter(rental=self.rental, reviewer=self.renter).count(), 1
        )

    def test_31_days_after_rejected(self):
        old_rental = make_completed_rental(
            renter=self.renter, completed_days_ago=31
        )
        r = self._post(self.renter, old_rental.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn('30 days', r.json()['data']['non_field_errors'][0])

    def test_30_days_exactly_still_allowed(self):
        recent_rental = make_completed_rental(
            renter=self.renter, completed_days_ago=29
        )
        r = self._post(self.renter, recent_rental.pk)
        self.assertEqual(r.status_code, 201)

    def test_unauthenticated_rejected(self):
        r = self.client.post(
            self.url,
            {'rental': str(self.rental.pk), 'rating': 5},
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 401)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

class TestReviewAggregation(TestCase):

    def test_product_average_rating_from_renter_to_owner_only(self):
        product = ProductFactory()
        owner = product.owner
        r1 = RentalFactory(product=product, owner=owner, status='completed')
        r2 = RentalFactory(product=product, owner=owner, status='completed')

        Review.objects.create(
            rental=r1, reviewer=r1.renter, reviewee=owner,
            product=product, direction='renter_to_owner', rating=4,
        )
        Review.objects.create(
            rental=r2, reviewer=r2.renter, reviewee=owner,
            product=product, direction='renter_to_owner', rating=2,
        )

        product.refresh_from_db()
        self.assertAlmostEqual(float(product.average_rating), 3.0)

    def test_owner_to_renter_reviews_excluded_from_product_rating(self):
        product = ProductFactory()
        owner = product.owner
        rental = RentalFactory(product=product, owner=owner, status='completed')

        # renter_to_owner: rating 4
        Review.objects.create(
            rental=rental, reviewer=rental.renter, reviewee=owner,
            product=product, direction='renter_to_owner', rating=4,
        )
        # owner_to_renter review on the same product
        rental2 = RentalFactory(product=product, owner=owner, status='completed')
        Review.objects.create(
            rental=rental2, reviewer=rental2.owner, reviewee=rental2.renter,
            product=product, direction='owner_to_renter', rating=1,
        )

        product.refresh_from_db()
        # Only renter_to_owner (rating=4) contributes
        self.assertAlmostEqual(float(product.average_rating), 4.0)

    def test_user_average_rating_from_all_received(self):
        owner = VerifiedUserFactory()
        r1 = RentalFactory(owner=owner, status='completed')
        r2 = make_completed_rental(renter=owner)  # owner is the renter here

        # owner receives a review as an owner (renter_to_owner)
        Review.objects.create(
            rental=r1, reviewer=r1.renter, reviewee=owner,
            product=r1.product, direction='renter_to_owner', rating=5,
        )
        # owner receives a review as a renter (owner_to_renter)
        Review.objects.create(
            rental=r2, reviewer=r2.owner, reviewee=owner,
            product=r2.product, direction='owner_to_renter', rating=3,
        )

        owner.refresh_from_db()
        self.assertAlmostEqual(float(owner.average_rating), 4.0)  # (5+3)/2

    def test_rating_updates_on_each_new_review(self):
        product = ProductFactory()
        owner = product.owner
        rentals = [RentalFactory(product=product, owner=owner, status='completed') for _ in range(3)]

        for i, (rental, rating) in enumerate(zip(rentals, [5, 3, 4])):
            Review.objects.create(
                rental=rental, reviewer=rental.renter, reviewee=owner,
                product=product, direction='renter_to_owner', rating=rating,
            )

        product.refresh_from_db()
        # (5+3+4)/3 = 4.0
        self.assertAlmostEqual(float(product.average_rating), 4.0)


# ---------------------------------------------------------------------------
# List endpoints
# ---------------------------------------------------------------------------

class TestReviewListEndpoints(TestCase):

    def setUp(self):
        self.product = ProductFactory()
        self.owner = self.product.owner

        rental1 = RentalFactory(product=self.product, owner=self.owner, status='completed')
        self.r2o = Review.objects.create(
            rental=rental1, reviewer=rental1.renter, reviewee=self.owner,
            product=self.product, direction='renter_to_owner', rating=5,
        )

        rental2 = RentalFactory(product=self.product, owner=self.owner, status='completed')
        self.o2r = Review.objects.create(
            rental=rental2, reviewer=rental2.owner, reviewee=rental2.renter,
            product=self.product, direction='owner_to_renter', rating=4,
        )

    def test_product_list_only_renter_to_owner(self):
        r = self.client.get(f'/api/reviews/?product={self.product.pk}')
        self.assertEqual(r.status_code, 200)
        data = r.json()['data']
        ids = [rv['id'] for rv in data]
        self.assertIn(str(self.r2o.pk), ids)
        self.assertNotIn(str(self.o2r.pk), ids)
        self.assertTrue(all(rv['direction'] == 'renter_to_owner' for rv in data))

    def test_user_list_returns_reviews_received(self):
        r = self.client.get(f'/api/reviews/?user={self.owner.pk}')
        self.assertEqual(r.status_code, 200)
        data = r.json()['data']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], str(self.r2o.pk))

    def test_list_requires_filter_param(self):
        r = self.client.get('/api/reviews/')
        self.assertEqual(r.status_code, 400)

    def test_product_list_public_no_auth(self):
        r = self.client.get(f'/api/reviews/?product={self.product.pk}')
        self.assertEqual(r.status_code, 200)

    def test_user_list_public_no_auth(self):
        r = self.client.get(f'/api/reviews/?user={self.owner.pk}')
        self.assertEqual(r.status_code, 200)


# ---------------------------------------------------------------------------
# Pending endpoint
# ---------------------------------------------------------------------------

class TestReviewPending(TestCase):

    def setUp(self):
        self.renter = RenterFactory()
        self.rental = make_completed_rental(renter=self.renter)

    def test_pending_shows_unreviewed_completed_rentals(self):
        r = self.client.get('/api/reviews/pending/', **auth_headers(self.renter))
        self.assertEqual(r.status_code, 200)
        ids = [item['id'] for item in r.json()['data']]
        self.assertIn(str(self.rental.pk), ids)

    def test_pending_excludes_already_reviewed(self):
        Review.objects.create(
            rental=self.rental,
            reviewer=self.renter,
            reviewee=self.rental.owner,
            product=self.rental.product,
            direction='renter_to_owner',
            rating=4,
        )
        r = self.client.get('/api/reviews/pending/', **auth_headers(self.renter))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['data']), 0)

    def test_pending_excludes_non_completed_rentals(self):
        RentalFactory(renter=self.renter, status='accepted')
        r = self.client.get('/api/reviews/pending/', **auth_headers(self.renter))
        ids = [item['id'] for item in r.json()['data']]
        # Only the completed one should appear
        self.assertNotIn(  # accepted rental not in pending
            RentalFactory.__name__, ids
        )
        self.assertEqual(len(ids), 1)

    def test_pending_requires_auth(self):
        r = self.client.get('/api/reviews/pending/')
        self.assertEqual(r.status_code, 401)
