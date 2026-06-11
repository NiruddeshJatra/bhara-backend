from datetime import date, timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from listings.tests.factories import ProductFactory, PricingTierFactory
from rentals.models import PaymentRecord, Rental, RentalPhoto
from users.tests.factories import VerifiedUserFactory


class RenterFactory(VerifiedUserFactory):
    """Distinct verified user to serve as renter (avoids owner==renter)."""
    phone_number = factory.Sequence(lambda n: f'018{n:08d}')


class RentalFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Rental

    product = factory.SubFactory(ProductFactory)
    owner = factory.LazyAttribute(lambda o: o.product.owner)
    renter = factory.SubFactory(RenterFactory)
    start_date = factory.LazyFunction(lambda: date.today() + timedelta(days=7))
    duration = 3
    duration_unit = 'day'
    end_date = factory.LazyAttribute(lambda o: o.start_date + timedelta(days=o.duration))
    unit_price = Decimal('500.00')
    base_cost = factory.LazyAttribute(lambda o: o.unit_price * o.duration)
    service_fee = factory.LazyAttribute(
        lambda o: (o.base_cost * Decimal('0.20')).quantize(Decimal('0.01'))
    )
    owner_payout = factory.LazyAttribute(lambda o: o.base_cost - o.service_fee)
    security_deposit = Decimal('1000.00')
    purpose = 'personal'
    notes = ''
    status = 'pending'
    status_history = factory.LazyAttribute(lambda o: [{
        'status': 'pending',
        'timestamp': timezone.now().isoformat(),
        'actor_id': str(o.renter.pk),
        'note': '',
    }])


class PaymentRecordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PaymentRecord

    rental = factory.SubFactory(RentalFactory)
    record_type = 'rent_collected'
    amount = Decimal('1500.00')
    method = 'cash'
    reference = ''
    note = ''
    recorded_by = factory.SubFactory(VerifiedUserFactory)
