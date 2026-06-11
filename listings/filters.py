from django.apps import apps
from django.db.models import Q
from django_filters import rest_framework as filters

from listings.models import Product


class ProductFilter(filters.FilterSet):
  """Ported from legacy advertisements.filters with corrected availability logic."""

  search = filters.CharFilter(method='filter_search', label='Search by title, category, or type')
  location = filters.CharFilter(field_name='location', lookup_expr='icontains')
  min_price = filters.NumberFilter(field_name='pricing_tiers__price', lookup_expr='gte')
  max_price = filters.NumberFilter(field_name='pricing_tiers__price', lookup_expr='lte')
  start_date = filters.DateFilter(method='filter_availability', label='Available from date')
  end_date = filters.DateFilter(method='filter_availability', label='Available until date')
  duration_unit = filters.CharFilter(field_name='pricing_tiers__duration_unit', lookup_expr='iexact')
  ordering = filters.CharFilter(method='filter_ordering', label='Order by')

  class Meta:
    model = Product
    fields = [
      'search',
      'location',
      'min_price',
      'max_price',
      'start_date',
      'end_date',
      'duration_unit',
      'ordering',
    ]

  def filter_search(self, queryset, name, value):
    return queryset.filter(
      Q(title__icontains=value)
      | Q(category__iexact=value)
      | Q(product_type__iexact=value)
    ).distinct()

  def filter_availability(self, queryset, name, value):
    """
    Excludes products blocked anywhere in [start_date, end_date]:
    owner UnavailablePeriods AND overlapping accepted/in_progress rentals (§3.3).
    Runs once per provided param but the exclusion is idempotent.
    """
    start = self.form.cleaned_data.get('start_date')
    end = self.form.cleaned_data.get('end_date')
    start = start or end
    end = end or start

    blocked = Q(
      unavailable_periods__is_range=False,
      unavailable_periods__date__gte=start,
      unavailable_periods__date__lte=end,
    ) | Q(
      unavailable_periods__is_range=True,
      unavailable_periods__range_start__lte=end,
      unavailable_periods__range_end__gte=start,
    )
    if apps.is_installed('rentals'):
      blocked |= Q(
        rentals__status__in=['accepted', 'in_progress'],
        rentals__start_date__lte=end,
        rentals__end_date__gte=start,
      )
    return queryset.exclude(blocked).distinct()

  def filter_ordering(self, queryset, name, value):
    if value == 'price_asc':
      return queryset.order_by('pricing_tiers__price')
    if value == 'price_desc':
      return queryset.order_by('-pricing_tiers__price')
    if value == 'rating':
      return queryset.order_by('-average_rating')
    if value == 'views':
      return queryset.order_by('-views_count')
    return queryset
