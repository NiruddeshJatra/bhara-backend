"""
Infrastructure endpoints. Health check is a plain Django view — no DRF
auth/throttle layers so load balancers can always reach it.
"""

import uuid

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse


def health(request):
  try:
    connection.ensure_connection()
  except Exception:
    return JsonResponse({'status': 'error', 'component': 'database'}, status=503)

  try:
    key = f'health:{uuid.uuid4()}'
    cache.set(key, '1', timeout=5)
    if cache.get(key) != '1':
      raise ValueError('cache roundtrip failed')
    cache.delete(key)
  except Exception:
    return JsonResponse({'status': 'error', 'component': 'cache'}, status=503)

  return JsonResponse({'status': 'ok'})
