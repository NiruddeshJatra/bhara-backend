from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated

from core.responses import success_response, error_response
from rentals.models import Rental, RentalPhoto
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
        queryset = self.get_queryset()
        obj = queryset.get(pk=self.kwargs['pk'])
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
        try:
            rental = self.get_object()
        except Rental.DoesNotExist:
            return error_response('Rental not found.', status_code=status.HTTP_404_NOT_FOUND)
        return success_response(RentalDetailSerializer(rental).data)

    # ------------------------------------------------------------------
    # List actions
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='my-rentals')
    def my_rentals(self, request):
        qs = Rental.objects.filter(renter=request.user).select_related(
            'product', 'owner', 'renter'
        )
        return success_response(RentalListSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'], url_path='my-listings-rentals')
    def my_listings_rentals(self, request):
        qs = Rental.objects.filter(owner=request.user).select_related(
            'product', 'owner', 'renter'
        )
        return success_response(RentalListSerializer(qs, many=True).data)

    # ------------------------------------------------------------------
    # Transition actions (views never set rental.status directly — §4.2)
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        try:
            rental = self.get_object()
        except Rental.DoesNotExist:
            return error_response('Rental not found.', status_code=status.HTTP_404_NOT_FOUND)
        try:
            rental.transition('accepted', request.user)
        except TransitionError as e:
            return error_response(str(e), status_code=status.HTTP_400_BAD_REQUEST)
        return success_response(
            RentalDetailSerializer(rental).data, 'Rental accepted.'
        )

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        try:
            rental = self.get_object()
        except Rental.DoesNotExist:
            return error_response('Rental not found.', status_code=status.HTTP_404_NOT_FOUND)
        note = request.data.get('note', '')
        try:
            rental.transition('rejected', request.user, note=note)
        except TransitionError as e:
            return error_response(str(e), status_code=status.HTTP_400_BAD_REQUEST)
        return success_response(
            RentalDetailSerializer(rental).data, 'Rental rejected.'
        )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        try:
            rental = self.get_object()
        except Rental.DoesNotExist:
            return error_response('Rental not found.', status_code=status.HTTP_404_NOT_FOUND)
        note = request.data.get('note', '')
        try:
            rental.transition('cancelled', request.user, note=note)
        except TransitionError as e:
            return error_response(str(e), status_code=status.HTTP_400_BAD_REQUEST)
        return success_response(
            RentalDetailSerializer(rental).data, 'Rental cancelled.'
        )

    # ------------------------------------------------------------------
    # Photos
    # ------------------------------------------------------------------

    @action(detail=True, methods=['get', 'post'], url_path='photos')
    def photos(self, request, pk=None):
        try:
            rental = self.get_object()
        except Rental.DoesNotExist:
            return error_response('Rental not found.', status_code=status.HTTP_404_NOT_FOUND)

        if request.method == 'GET':
            serializer = RentalPhotoSerializer(
                rental.photos.all(), many=True, context={'request': request}
            )
            return success_response(serializer.data)

        # POST — upload photo
        if rental.status not in ('accepted', 'in_progress', 'completed'):
            return error_response(
                'Photos can only be uploaded when rental is accepted, in_progress, or completed.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RentalPhotoSerializer(
            data=request.data, context={'request': request}
        )
        if not serializer.is_valid():
            return error_response(serializer.errors, 'Validation failed.')

        photo = serializer.save(rental=rental, uploaded_by=request.user)

        # 5 MB limit enforced here (serializer field validates extension; size checked below)
        if photo.photo.size > 5 * 1024 * 1024:
            photo.delete()
            return error_response(
                'Photo must be ≤ 5 MB.', status_code=status.HTTP_400_BAD_REQUEST
            )

        return success_response(
            RentalPhotoSerializer(photo, context={'request': request}).data,
            'Photo uploaded.',
            status.HTTP_201_CREATED,
        )
