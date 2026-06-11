from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated

from core.pagination import StandardResultsSetPagination, paginated_success_response
from core.responses import error_response, success_response
from rentals.models import Rental
from rentals.serializers import RentalListSerializer
from reviews.models import Review
from reviews.serializers import ReviewCreateSerializer, ReviewSerializer


class ReviewViewSet(viewsets.GenericViewSet):
    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.action == 'list':
            return [AllowAny()]
        return [IsAuthenticated()]

    def create(self, request):
        serializer = ReviewCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return error_response(serializer.errors, 'Validation failed.')
        review = serializer.save()
        return success_response(
            ReviewSerializer(review).data,
            'Review submitted.',
            status.HTTP_201_CREATED,
        )

    def list(self, request):
        product_id = request.query_params.get('product')
        user_id = request.query_params.get('user')

        if product_id:
            qs = Review.objects.filter(
                product_id=product_id,
                direction='renter_to_owner',
            ).select_related('reviewer', 'reviewee', 'product')
        elif user_id:
            qs = Review.objects.filter(
                reviewee_id=user_id,
            ).select_related('reviewer', 'reviewee', 'product')
        else:
            return error_response(
                message='Provide ?product=<id> or ?user=<id>.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        return paginated_success_response(self, qs, ReviewSerializer)

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Completed rentals where I'm a participant and haven't reviewed yet."""
        user = request.user
        reviewed_rental_ids = Review.objects.filter(
            reviewer=user
        ).values_list('rental_id', flat=True)
        rentals = (
            Rental.objects.filter(
                Q(renter=user) | Q(owner=user),
                status='completed',
            )
            .exclude(pk__in=reviewed_rental_ids)
            .select_related('product', 'owner', 'renter')
        )
        return paginated_success_response(self, rentals, RentalListSerializer)
