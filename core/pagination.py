"""
Shared pagination for all list endpoints.

Single source so rentals/reviews don't import from listings. Paginated
responses keep the {success, message, data} envelope with data =
{count, next, previous, results}.
"""

from rest_framework.pagination import PageNumberPagination

from core.responses import success_response


class StandardResultsSetPagination(PageNumberPagination):
  page_size = 20
  page_size_query_param = 'page_size'
  max_page_size = 80


def paginated_success_response(viewset, queryset, serializer_class, context=None):
  """Paginate queryset on the viewset and wrap in the standard envelope."""
  page = viewset.paginate_queryset(queryset)
  if page is not None:
    serializer = serializer_class(page, many=True, context=context or {})
    return success_response(
      viewset.paginator.get_paginated_response(serializer.data).data
    )
  serializer = serializer_class(queryset, many=True, context=context or {})
  return success_response({'results': serializer.data})
