from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import F
from django_filters.rest_framework import DjangoFilterBackend

from core.pagination import StandardResultsSetPagination, paginated_success_response
from core.responses import success_response, error_response
from listings.filters import ProductFilter
from listings.models import Product
from listings.serializers import ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
  serializer_class = ProductSerializer
  pagination_class = StandardResultsSetPagination
  parser_classes = [MultiPartParser, FormParser, JSONParser]
  filter_backends = [DjangoFilterBackend]
  filterset_class = ProductFilter

  def get_permissions(self):
    if self.action in ('list', 'retrieve'):
      return [AllowAny()]
    return [IsAuthenticated()]

  def get_queryset(self):
    # NO response caching anywhere — Postgres + indexes carry launch scale (§3.3)
    queryset = Product.objects.select_related('owner').prefetch_related(
      'images', 'pricing_tiers', 'unavailable_periods'
    )
    if self.action in ('list', 'retrieve'):
      return queryset.filter(status='active')
    if self.action == 'my_products':
      return queryset.filter(owner=self.request.user)
    # update / partial_update / destroy — owner only, any status
    if self.request.user.is_authenticated:
      return queryset.filter(owner=self.request.user)
    return queryset.none()

  def _paginated_response(self, queryset):
    return paginated_success_response(self, queryset, self.get_serializer_class())


  def list(self, request, *args, **kwargs):
    queryset = self.filter_queryset(self.get_queryset())
    return self._paginated_response(queryset)

  def retrieve(self, request, *args, **kwargs):
    product = self.get_object()
    if request.user != product.owner:
      Product.objects.filter(pk=product.pk).update(views_count=F('views_count') + 1)
      # Mirror the increment in memory for the response — saves a re-fetch query
      product.views_count += 1
    serializer = self.get_serializer(product)
    return success_response(serializer.data)

  def create(self, request, *args, **kwargs):
    if not request.user.can_transact():
      return error_response(
        message='Complete your profile and identity verification to list items.',
        status_code=status.HTTP_403_FORBIDDEN,
      )
    serializer = self.get_serializer(data=request.data)
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')
    serializer.save(owner=request.user)
    return success_response(serializer.data, 'Listing created.', status.HTTP_201_CREATED)

  def update(self, request, *args, **kwargs):
    partial = kwargs.pop('partial', False)
    product = self.get_object()
    if product.has_blocking_rentals():
      return error_response(
        message='This listing has an active rental and cannot be modified.',
        status_code=status.HTTP_403_FORBIDDEN,
      )
    serializer = self.get_serializer(product, data=request.data, partial=partial)
    if not serializer.is_valid():
      return error_response(serializer.errors, 'Validation failed.')
    serializer.save()
    return success_response(serializer.data, 'Listing updated.')

  def destroy(self, request, *args, **kwargs):
    product = self.get_object()
    if product.has_blocking_rentals():
      return error_response(
        message='This listing has an active rental and cannot be deleted.',
        status_code=status.HTTP_403_FORBIDDEN,
      )
    product.delete()
    return success_response(message='Listing deleted.')

  @action(detail=False, methods=['get'])
  def my_products(self, request):
    queryset = self.filter_queryset(self.get_queryset())
    return self._paginated_response(queryset)
