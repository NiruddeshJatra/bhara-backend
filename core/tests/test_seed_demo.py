from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from listings.models import Product
from rentals.models import Rental
from reviews.models import Review

User = get_user_model()
SEED_PREFIX = '+88017000000'


class SeedDemoCommandTest(TestCase):

    def _run(self, *args, **kwargs):
        out = StringIO()
        call_command('seed_demo', *args, stdout=out, stderr=StringIO(), **kwargs)
        return out.getvalue()

    # --- safety guard ---

    @override_settings(DEBUG=False)
    def test_refuses_when_debug_false(self):
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn('REFUSED', str(ctx.exception))

    @override_settings(DEBUG=False)
    def test_force_flag_bypasses_guard(self):
        # Should not raise; runs the seed
        out = self._run(force_prod=True)
        self.assertIn('seeded successfully', out)

    # --- idempotency ---

    @override_settings(DEBUG=True)
    def test_runs_without_error_on_clean_db(self):
        out = self._run()
        self.assertIn('seeded successfully', out)

    @override_settings(DEBUG=True)
    def test_idempotent_double_run(self):
        self._run()
        before_users = User.objects.filter(phone_number__startswith=SEED_PREFIX).count()
        before_products = Product.objects.filter(
            owner__phone_number__startswith=SEED_PREFIX
        ).count()
        self._run()
        self.assertEqual(
            User.objects.filter(phone_number__startswith=SEED_PREFIX).count(),
            before_users,
        )
        self.assertEqual(
            Product.objects.filter(
                owner__phone_number__startswith=SEED_PREFIX
            ).count(),
            before_products,
        )

    # --- data integrity ---

    @override_settings(DEBUG=True)
    def test_creates_expected_users(self):
        self._run()
        users = User.objects.filter(phone_number__startswith=SEED_PREFIX)
        # 14 demo users + 1 ops staff
        self.assertGreaterEqual(users.count(), 15)
        for u in users.exclude(phone_number='+8801700000098'):
            self.assertTrue(u.profile_completed, f'{u.phone_number} profile_completed False')
            self.assertIn(u.trust_level, ('verified', 'partner'))

    @override_settings(DEBUG=True)
    def test_creates_products_across_categories(self):
        self._run()
        products = Product.objects.filter(
            owner__phone_number__startswith=SEED_PREFIX
        )
        self.assertGreaterEqual(products.count(), 28)
        categories = set(products.values_list('category', flat=True))
        self.assertGreaterEqual(len(categories), 5)

    @override_settings(DEBUG=True)
    def test_draft_and_suspended_products_created(self):
        self._run()
        seed_owners = User.objects.filter(phone_number__startswith=SEED_PREFIX)
        self.assertTrue(
            Product.objects.filter(owner__in=seed_owners, status='draft').exists()
        )
        self.assertTrue(
            Product.objects.filter(owner__in=seed_owners, status='suspended').exists()
        )

    @override_settings(DEBUG=True)
    def test_all_six_rental_statuses_present(self):
        self._run()
        seed_owners = User.objects.filter(phone_number__startswith=SEED_PREFIX)
        rentals = Rental.objects.filter(owner__in=seed_owners)
        statuses = set(rentals.values_list('status', flat=True))
        for expected in ('pending', 'accepted', 'in_progress', 'completed',
                         'rejected', 'cancelled'):
            self.assertIn(expected, statuses, f'Status {expected!r} missing from rentals')

    @override_settings(DEBUG=True)
    def test_completed_rentals_have_payment_records(self):
        self._run()
        seed_owners = User.objects.filter(phone_number__startswith=SEED_PREFIX)
        completed = Rental.objects.filter(owner__in=seed_owners, status='completed')
        self.assertGreater(completed.count(), 0)
        for r in completed:
            self.assertTrue(
                r.payment_records.filter(record_type='rent_collected').exists(),
                f'Rental {r.pk} missing rent_collected',
            )
            self.assertTrue(
                r.payment_records.filter(record_type='owner_payout').exists(),
                f'Rental {r.pk} missing owner_payout',
            )

    @override_settings(DEBUG=True)
    def test_reviews_created_on_completed_rentals(self):
        self._run()
        self.assertGreater(Review.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_status_history_populated_via_transition(self):
        self._run()
        seed_owners = User.objects.filter(phone_number__startswith=SEED_PREFIX)
        completed = Rental.objects.filter(owner__in=seed_owners, status='completed').first()
        self.assertIsNotNone(completed)
        # pending → accepted → in_progress → completed = 4 entries
        self.assertGreaterEqual(len(completed.status_history), 4)
        statuses_in_history = [e['status'] for e in completed.status_history]
        self.assertIn('pending', statuses_in_history)
        self.assertIn('completed', statuses_in_history)

    # --- wipe ---

    @override_settings(DEBUG=True)
    def test_wipe_removes_all_seeded_data(self):
        self._run()
        self.assertGreater(
            User.objects.filter(phone_number__startswith=SEED_PREFIX).count(), 0
        )
        self._run('--wipe')
        self.assertEqual(
            User.objects.filter(phone_number__startswith=SEED_PREFIX).count(), 0
        )
        self.assertEqual(
            Product.objects.filter(
                owner__phone_number__startswith=SEED_PREFIX
            ).count(),
            0,
        )
