"""
Availability helpers for the listings app (§4.6).
"""

from datetime import timedelta

from django.apps import apps
from django.db import models


def get_blocked_dates(product, start=None, end=None) -> set:
    """
    Return a set of date objects that are unavailable for rental on the given product.

    Includes:
      - Owner-declared UnavailablePeriods
      - Dates covered by accepted or in_progress rentals

    When start/end are given, only rows overlapping [start, end] are fetched
    and expanded — without them a product's entire rental history is loaded
    and every covered date materialized.

    Used by both the availability filter (listings.filters) and the create guard.
    """
    blocked = set()
    windowed = start is not None and end is not None

    periods = product.unavailable_periods.all()
    if windowed:
        periods = periods.filter(
            models.Q(is_range=False, date__gte=start, date__lte=end)
            | models.Q(is_range=True, range_start__lte=end, range_end__gte=start)
        )
    for period in periods:
        if period.is_range:
            d = period.range_start
            while d <= period.range_end:
                blocked.add(d)
                d += timedelta(days=1)
        else:
            blocked.add(period.date)

    if apps.is_installed('rentals'):
        from rentals.models import Rental
        rentals = Rental.objects.filter(
            product=product,
            status__in=['accepted', 'in_progress'],
        ).only('start_date', 'end_date')
        if windowed:
            rentals = rentals.filter(start_date__lte=end, end_date__gte=start)
        for rental in rentals:
            d = rental.start_date
            while d <= rental.end_date:
                blocked.add(d)
                d += timedelta(days=1)

    return blocked
