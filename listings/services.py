"""
Availability helpers for the listings app (§4.6).
"""

from datetime import timedelta

from django.apps import apps


def get_blocked_dates(product) -> set:
    """
    Return a set of date objects that are unavailable for rental on the given product.

    Includes:
      - Owner-declared UnavailablePeriods
      - Dates covered by accepted or in_progress rentals

    Used by both the availability filter (listings.filters) and the create guard.
    """
    blocked = set()

    for period in product.unavailable_periods.all():
        if period.is_range:
            d = period.range_start
            while d <= period.range_end:
                blocked.add(d)
                d += timedelta(days=1)
        else:
            blocked.add(period.date)

    if apps.is_installed('rentals'):
        from rentals.models import Rental
        for rental in Rental.objects.filter(
            product=product,
            status__in=['accepted', 'in_progress'],
        ).only('start_date', 'end_date'):
            d = rental.start_date
            while d <= rental.end_date:
                blocked.add(d)
                d += timedelta(days=1)

    return blocked
