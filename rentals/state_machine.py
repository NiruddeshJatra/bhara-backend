"""
Single source of truth for rental status transitions (§4.2).
Views call Rental.transition(); they never assign rental.status directly.
"""

ALLOWED_TRANSITIONS = {
    'pending':     {'accepted': 'owner', 'rejected': 'owner', 'cancelled': 'renter_or_staff'},
    'accepted':    {'in_progress': 'staff', 'cancelled': 'renter_or_staff'},
    'in_progress': {'completed': 'staff'},
    'completed':   {},
    'rejected':    {},
    'cancelled':   {},
}

ALL_STATUSES = list(ALLOWED_TRANSITIONS.keys())


class TransitionError(Exception):
    """Raised when a status transition is not allowed."""
    pass


def get_actor_role(rental, actor):
    """Return 'owner', 'renter', 'staff', or None for an actor on a rental."""
    if actor.is_staff:
        return 'staff'
    if actor.pk == rental.owner_id:
        return 'owner'
    if actor.pk == rental.renter_id:
        return 'renter'
    return None


def role_matches(actor_role, required_role):
    """Return True if actor_role satisfies the required_role for a transition edge."""
    if required_role == 'renter_or_staff':
        return actor_role in ('renter', 'staff')
    return actor_role == required_role
