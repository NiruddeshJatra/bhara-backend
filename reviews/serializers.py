from datetime import datetime, timedelta
from datetime import timezone as dt_tz

from django.utils import timezone
from rest_framework import serializers

from rentals.models import Rental
from reviews.models import Review


class ReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source='reviewer.full_name', read_only=True)
    reviewee_name = serializers.CharField(source='reviewee.full_name', read_only=True)

    class Meta:
        model = Review
        fields = [
            'id', 'rental', 'reviewer', 'reviewer_name',
            'reviewee', 'reviewee_name', 'product',
            'direction', 'rating', 'comment', 'created_at',
        ]
        read_only_fields = fields


class ReviewCreateSerializer(serializers.Serializer):
    rental = serializers.PrimaryKeyRelatedField(queryset=Rental.objects.all())
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, default=''
    )

    def validate(self, data):
        reviewer = self.context['request'].user
        rental = data['rental']

        if rental.status != 'completed':
            raise serializers.ValidationError('Rental must be completed before reviewing.')

        if reviewer not in (rental.renter, rental.owner):
            raise serializers.ValidationError(
                'You are not a participant in this rental.'
            )

        # Find completion timestamp from status_history
        completion_entry = next(
            (e for e in reversed(rental.status_history) if e['status'] == 'completed'),
            None,
        )
        if not completion_entry:
            raise serializers.ValidationError('Rental has no completion record.')
        try:
            completed_at = datetime.fromisoformat(completion_entry['timestamp'])
        except (ValueError, KeyError, TypeError):
            raise serializers.ValidationError('Rental has a malformed completion record.')
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=dt_tz.utc)
        if timezone.now() - completed_at > timedelta(days=30):
            raise serializers.ValidationError(
                'Review window (30 days after completion) has passed.'
            )

        if Review.objects.filter(rental=rental, reviewer=reviewer).exists():
            raise serializers.ValidationError('You have already reviewed this rental.')

        if reviewer == rental.renter:
            data['direction'] = 'renter_to_owner'
            data['reviewee'] = rental.owner
        else:
            data['direction'] = 'owner_to_renter'
            data['reviewee'] = rental.renter

        data['reviewer'] = reviewer
        data['product'] = rental.product
        return data

    def create(self, validated_data):
        return Review.objects.create(
            rental=validated_data['rental'],
            reviewer=validated_data['reviewer'],
            reviewee=validated_data['reviewee'],
            product=validated_data['product'],
            direction=validated_data['direction'],
            rating=validated_data['rating'],
            comment=validated_data.get('comment', ''),
        )
