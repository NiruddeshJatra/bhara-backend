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
  original_serializer_class = getattr(viewset, 'serializer_class', None)
  viewset.serializer_class = serializer_class
  try:
    serializer_context = {}
    if hasattr(viewset, 'get_serializer_context'):
      serializer_context = viewset.get_serializer_context()
    if context:
      serializer_context.update(context)

    page = viewset.paginate_queryset(queryset)
    if page is not None:
      serializer = viewset.get_serializer(page, many=True, context=serializer_context)
      return success_response(
        viewset.paginator.get_paginated_response(serializer.data).data
      )
    serializer = viewset.get_serializer(queryset, many=True, context=serializer_context)
    return success_response({
      'count': len(serializer.data),
      'next': None,
      'previous': None,
      'results': serializer.data,
    })
  finally:
    if original_serializer_class is not None:
      viewset.serializer_class = original_serializer_class
    else:
      # If it didn't exist before, remove it to avoid leaking
      try:
        delattr(viewset, 'serializer_class')
      except AttributeError:
        pass

