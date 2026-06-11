import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg

from listings.models import Product

DIRECTION_CHOICES = [
    ('renter_to_owner', 'Renter → Owner'),
    ('owner_to_renter', 'Owner → Renter'),
]


class Review(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rental = models.ForeignKey(
        'rentals.Rental', on_delete=models.CASCADE, related_name='reviews'
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_written',
    )
    reviewee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_received',
    )
    product = models.ForeignKey(
        'listings.Product', on_delete=models.CASCADE, related_name='reviews'
    )
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['rental', 'reviewer'], name='one_review_per_party'
            )
        ]

    def __str__(self):
        return f'{self.reviewer} → {self.reviewee} ({self.rating}★)'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._recompute_ratings()

    def _recompute_ratings(self):
        if self.direction == 'renter_to_owner':
            self._recompute_product_rating()
        self._recompute_reviewee_rating()

    def _recompute_product_rating(self):
        avg = (
            Review.objects.filter(
                product_id=self.product_id, direction='renter_to_owner'
            )
            .aggregate(avg=Avg('rating'))['avg']
            or 0
        )
        Product.objects.filter(pk=self.product_id).update(average_rating=avg)

    def _recompute_reviewee_rating(self):
        avg = (
            Review.objects.filter(reviewee_id=self.reviewee_id)
            .aggregate(avg=Avg('rating'))['avg']
            or 0
        )
        get_user_model().objects.filter(pk=self.reviewee_id).update(average_rating=avg)
