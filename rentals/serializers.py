from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from listings.models import PricingTier, Product
from rentals.models import (
    PURPOSE_CHOICES,
    DURATION_UNIT_CHOICES,
    Rental,
    RentalPhoto,
    PaymentRecord,
    compute_end_date,
)


class PaymentRecordSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.CharField(
        source='recorded_by.full_name', read_only=True
    )

    class Meta:
        model = PaymentRecord
        fields = [
            'id', 'record_type', 'amount', 'method',
            'reference', 'note', 'recorded_by', 'recorded_by_name', 'created_at',
        ]
        read_only_fields = ['id', 'recorded_by', 'created_at']


class RentalPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = RentalPhoto
        fields = ['id', 'photo', 'photo_type', 'uploaded_by', 'created_at']
        read_only_fields = ['id', 'uploaded_by', 'created_at']


def _public_party(user):
    """Minimal public info about a rental party — never includes the phone
    number (counter-disintermediation: contact stays on-platform)."""
    return {
        'full_name': user.full_name,
        'trust_level': user.trust_level,
        'average_rating': str(user.average_rating),
    }


class RentalListSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source='product.title', read_only=True)
    renter_info = serializers.SerializerMethodField()
    owner_info = serializers.SerializerMethodField()

    class Meta:
        model = Rental
        fields = [
            'id', 'product', 'product_title', 'renter', 'renter_info',
            'owner', 'owner_info', 'start_date', 'end_date', 'duration',
            'duration_unit', 'base_cost', 'security_deposit', 'purpose',
            'status', 'created_at',
        ]
        read_only_fields = fields

    def get_renter_info(self, obj):
        return _public_party(obj.renter)

    def get_owner_info(self, obj):
        return _public_party(obj.owner)


class RentalDetailSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source='product.title', read_only=True)
    renter_info = serializers.SerializerMethodField()
    owner_info = serializers.SerializerMethodField()
    payment_records = PaymentRecordSerializer(many=True, read_only=True)
    settlement = serializers.SerializerMethodField()

    class Meta:
        model = Rental
        fields = [
            'id', 'product', 'product_title', 'renter', 'renter_info',
            'owner', 'owner_info', 'start_date', 'end_date', 'duration',
            'duration_unit', 'unit_price', 'base_cost', 'service_fee',
            'owner_payout', 'security_deposit', 'purpose', 'notes',
            'status', 'status_history', 'payment_records', 'settlement',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_renter_info(self, obj):
        return _public_party(obj.renter)

    def get_owner_info(self, obj):
        return _public_party(obj.owner)

    def get_settlement(self, obj):
        records = list(obj.payment_records.all())

        def total(record_type):
            return sum(
                (r.amount for r in records if r.record_type == record_type),
                Decimal('0'),
            )

        return {
            'rent_paid': total('rent_collected'),
            'deposit_held': total('deposit_collected'),
            'deposit_returned': total('deposit_returned'),
            'owner_paid': total('owner_payout'),
        }


class RentalCreateSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(status='active')
    )
    start_date = serializers.DateField()
    duration = serializers.IntegerField(min_value=1)
    duration_unit = serializers.ChoiceField(
        choices=[c[0] for c in DURATION_UNIT_CHOICES]
    )
    purpose = serializers.ChoiceField(choices=[c[0] for c in PURPOSE_CHOICES])
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, data):
        request = self.context['request']
        renter = request.user
        product = data['product']

        if not renter.can_transact():
            raise serializers.ValidationError(
                'Complete your profile and identity verification to rent items.'
            )
        if renter == product.owner:
            raise serializers.ValidationError('Cannot rent your own product.')

        duration_unit = data['duration_unit']
        try:
            tier = product.pricing_tiers.get(duration_unit=duration_unit)
        except PricingTier.DoesNotExist:
            raise serializers.ValidationError(
                f'No pricing tier for duration unit "{duration_unit}".'
            )
        if data['duration'] > tier.max_period:
            raise serializers.ValidationError(
                f'Duration {data["duration"]} exceeds max {tier.max_period} '
                f'{duration_unit}(s) for this product.'
            )

        today = date.today()
        if data['start_date'] < today:
            raise serializers.ValidationError(
                'start_date must be today or in the future.'
            )

        end_date = compute_end_date(data['start_date'], data['duration'], duration_unit)

        # Delegate to get_blocked_dates so availability rules live in one place (§4.6)
        from listings.services import get_blocked_dates
        blocked = get_blocked_dates(product, start=data['start_date'], end=end_date)
        d = data['start_date']
        while d <= end_date:
            if d in blocked:
                raise serializers.ValidationError(
                    'Selected dates overlap with an unavailable period.'
                )
            d += timedelta(days=1)

        # No duplicate active request from this renter for this product
        if Rental.objects.filter(
            product=product,
            renter=renter,
            status__in=['pending', 'accepted'],
        ).exists():
            raise serializers.ValidationError(
                'You already have an active request for this product.'
            )

        data['end_date'] = end_date
        data['_tier'] = tier
        return data

    def create(self, validated_data):
        from django.db import transaction

        from celery_tasks.rentals import send_rental_request_sms

        tier = validated_data.pop('_tier')
        renter = self.context['request'].user
        product = validated_data['product']

        unit_price = Decimal(str(tier.price))
        base_cost = unit_price * validated_data['duration']
        service_fee = (base_cost * settings.SERVICE_FEE_RATE).quantize(Decimal('0.01'))
        owner_payout = base_cost - service_fee

        from django.utils import timezone
        rental = Rental.objects.create(
            renter=renter,
            owner=product.owner,
            product=product,
            start_date=validated_data['start_date'],
            end_date=validated_data['end_date'],
            duration=validated_data['duration'],
            duration_unit=validated_data['duration_unit'],
            unit_price=unit_price,
            base_cost=base_cost,
            service_fee=service_fee,
            owner_payout=owner_payout,
            security_deposit=product.security_deposit,
            purpose=validated_data['purpose'],
            notes=validated_data.get('notes', ''),
            status_history=[{
                'status': 'pending',
                'timestamp': timezone.now().isoformat(),
                'actor_id': str(renter.pk),
                'note': '',
            }],
        )

        # Notify the owner — only after the rental row is durably committed
        owner_phone = product.owner.phone_number
        title = product.title[:30]
        transaction.on_commit(
            lambda: send_rental_request_sms.delay(owner_phone, title)
        )
        return rental
