# backend/apps/orders/selectors.py
from django.core.exceptions import PermissionDenied
from apps.orders.models import Order

def resolve_ghost_profile(email: str) -> str:
    """
    Accepts an input customer email and returns it cleanly.
    In a standard platform, this would track or auto-instantiate 
    profile entries, but for our optimized guest checkout flow, 
    the email acts as our clean tracking key across orders.
    """
    return email.strip().lower()


def get_order_by_guest_hash(order_hash: str, customer_email: str) -> Order:
    """
    Acts as a secure route guard for public access.
    Allows guests to view their receipt using an 'order_hash', 
    but blocks malicious actors trying to guess or scrape other orders.
    """
    try:
        order = Order.objects.get(order_hash=order_hash)
    except Order.DoesNotExist:
        raise PermissionDenied("Access Denied: Invalid order context token.")

    # Explicitly check that the email matches to prevent token-guessing attacks
    if order.customer_email.lower() != customer_email.strip().lower():
        raise PermissionDenied("Access Denied: Identity confirmation failed.")

    return order


