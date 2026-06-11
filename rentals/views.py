from django.core.exceptions import ValidationError as DjValidationError
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated

from core.responses import success_response, error_response
from rentals.models import Rental
from rentals.serializers import (
    RentalCreateSerializer,
    RentalDetailSerializer,
    RentalListSerializer,
    RentalPhotoSerializer,
)
from rentals.state_machine import TransitionError


class RentalViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def handle_exception(self, exc):
        """Map DoesNotExist and invalid-UUID errors to 404 instead of 500."""
        if isinstance(exc, (Rental.DoesNotExist, DjValidationError, ValueError)):
            return error_response('Rental not found.', status_code=status.HTTP_404_NOT_FOUND)
        return super().handle_exception(exc)

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Rental.objects.select_related(
                'product', 'owner', 'renter'
            ).prefetch_related('payment_records', 'photos')
        return Rental.objects.filter(
            Q(renter=user) | Q(owner=user)
        ).select_related('product', 'owner', 'renter').prefetch_related(
            'payment_records', 'photos'
        )

    def get_object(self):
        obj = self.get_queryset().get(pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, obj)
        return obj

    # ------------------------------------------------------------------
    # Standard actions
    # ------------------------------------------------------------------

    def create(self, request):
        serializer = RentalCreateSerializer(
            data=request.data, context={'request': request}
        )
        if not serializer.is_valid():
            return error_response(serializer.errors, 'Validation failed.')
        rental = serializer.save()
        return success_response(
            RentalDetailSerializer(rental).data,
            'Rental request created.',
            status.HTTP_201_CREATED,
        )

    def retrieve(self, request, pk=None):
        rental = self.get_object()
        return success_response(RentalDetailSerializer(rental).data)

    # ------------------------------------------------------------------
    # List actions — reuse get_queryset for consistent scoping + prefetch
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='my-rentals')
    def my_rentals(self, request):
        qs = self.get_queryset().filter(renter=request.user)
        return success_response(RentalListSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'], url_path='my-listings-rentals')
    def my_listings_rentals(self, request):
        qs = self.get_queryset().filter(owner=request.user)
        return success_response(RentalListSerializer(qs, many=True).data)

    # ------------------------------------------------------------------
    # Transition actions (views never set rental.status directly — §4.2)
    # ------------------------------------------------------------------

    def _perform_transition(self, rental, new_status, user, note, success_message):
        try:
            rental.transition(new_status, user, note=note)
        except TransitionError as e:
            return error_response(str(e), status_code=status.HTTP_400_BAD_REQUEST)
        return success_response(RentalDetailSerializer(rental).data, success_message)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        return self._perform_transition(
            self.get_object(), 'accepted', request.user, '', 'Rental accepted.'
        )

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._perform_transition(
            self.get_object(), 'rejected', request.user,
            request.data.get('note', ''), 'Rental rejected.',
        )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        return self._perform_transition(
            self.get_object(), 'cancelled', request.user,
            request.data.get('note', ''), 'Rental cancelled.',
        )

    # ------------------------------------------------------------------
    # Photos
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get', 'post'], url_path='photos')
    def photos(self, request, pk=None):
        rental = self.get_object()
        if request.method == 'GET':
            return success_response(
                RentalPhotoSerializer(
                    rental.photos.all(), many=True, context={'request': request}
                ).data
            )
        return self._handle_photo_upload(request, rental)

    def _handle_photo_upload(self, request, rental):
        if rental.status not in ('accepted', 'in_progress', 'completed'):
            return error_response(
                'Photos can only be uploaded when rental is accepted, in_progress, or completed.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Enforce size limit before validation to avoid storing oversized files
        uploaded = request.FILES.get('photo')
        if uploaded and uploaded.size > 5 * 1024 * 1024:
            return error_response(message='Photo must be ≤ 5 MB.', status_code=status.HTTP_400_BAD_REQUEST)

        serializer = RentalPhotoSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return error_response(serializer.errors, 'Validation failed.')

        photo = serializer.save(rental=rental, uploaded_by=request.user)
        return success_response(
            RentalPhotoSerializer(photo, context={'request': request}).data,
            'Photo uploaded.',
            status.HTTP_201_CREATED,
        )
