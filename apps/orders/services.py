from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
from apps.events.models import TicketType
from apps.tickets.models import Ticket
from apps.orders.models import Order, OrderItem, TicketHold
from typing import List, Dict, Any
from decimal import Decimal
import hmac
import hashlib


def reserve_tickets_atomic(email: str, ticket_type_id: int, quantity: int, hold_duration_minutes: int = 10) -> TicketHold:
    """
    Executes a high-concurrency safe row lock on a TicketType to temporarily reserve tickets.
    Safely handles single and multiple ticket holds without race conditions.
    """
    if quantity <= 0:
        raise ValidationError(
            "Reservation quantity must be greater than zero.")

    # Wrap the operations tree inside an isolated database block
    with transaction.atomic():
        # SELECT ... FOR UPDATE blocks other incoming operations on this specific row until this block finishes
        ticket_type = TicketType.objects.select_for_update().get(id=ticket_type_id)

        # Calculate availability matching live remaining inventory configurations
        if ticket_type.quantity_available < quantity:
            raise ValidationError(
                f"Requested quantity ({quantity}) exceeds available stock ({ticket_type.quantity_available})"
                f"for tier '{ticket_type.name}'."
            )

        # Deduct the public stock directly
        ticket_type.quantity_available -= quantity
        ticket_type.save()

        # Instantiate the temporary hold tracking entry
        expiration_time = timezone.now() + timedelta(minutes=hold_duration_minutes)
        hold = TicketHold.objects.create(
            ticket_type=ticket_type,
            email=email,
            quantity=quantity,
            expires_at=expiration_time
        )
        return hold


def release_expired_holds_atomic() -> int:
    """
    Finds unreleased expired holds, frees them up sequentially using row locks, 
    and returns ticket amounts cleanly back into public active inventory.
    Returns the total count of processed holds.
    """
    now = timezone.now()
    processed_count = 0

    # Process unreleased entries whose expiration timers have lapsed
    expired_holds = TicketHold.objects.filter(
        expires_at__lt=now,
        is_released=False
    ).select_related('ticket_type')

    for hold in expired_holds:
        with transaction.atomic():
            # Lock both the hold row and its target ticket tier type row
            locked_hold = TicketHold.objects.select_for_update().get(id=hold.id)
            if not locked_hold.is_released:
                ticket_type = TicketType.objects.select_for_update().get(
                    id=locked_hold.ticket_type.id)

                # Revert stock allocations safely
                ticket_type.quantity_available += locked_hold.quantity
                ticket_type.save()

                # Mark safety tracking flag state
                locked_hold.is_released = True
                locked_hold.save()
                processed_count += 1

    return processed_count


def initialize_checkout_order(email: str, hold_ids: List[int]) -> Order:
    """
    Validates a collection of active ticket holds, aggregates their pricing metrics,
    and commits a verified pending master Order with itemized line breakdowns.
    """
    if not hold_ids:
        raise ValidationError(
            "Cannot initialize a checkout with an empty list of reservation holds.")

    now = timezone.now()

    with transaction.atomic():
        # Fetch the requested holds, ensuring they belong to this buyer and haven't expired
        active_holds = TicketHold.objects.filter(
            id__in=hold_ids,
            email__iexact=email.strip().lower(),
            is_released=False,
            expires_at__gt=now
        ).select_related('ticket_type')

        if len(active_holds) != len(hold_ids):
            raise ValidationError(
                "One or more ticket reservations have expired or are invalid.")

        # Create the base master order record first
        order = Order.objects.create(
            customer_email=email.strip().lower(),
            status='PENDING',
            total_price=Decimal('0.00')
        )

        calculated_running_total = Decimal('0.00')

        # Build individual line item breakdowns per active hold allocation
        for hold in active_holds:
            line_cost = hold.ticket_type.price * hold.quantity
            calculated_running_total += line_cost

            OrderItem.objects.create(
                order=order,
                ticket_type=hold.ticket_type,
                quantity=hold.quantity,
                price_at_purchase=hold.ticket_type.price
            )

        # Commit the computed financial sum total back to the master order row
        order.total_price = calculated_running_total
        order.save()

        return order


def prepare_payment_gateway_payload(order: Order, redirect_url: str) -> Dict[str, Any]:
    """
    Maps your pending order variables into the universally structured dictionary format
    required by transactional merchant aggregates (like Paystack, Flutterwave, or Stripe).
    """
    if order.status != 'PENDING':
        raise ValidationError(
            "Only pending transactions can be routed into the payment processor cycle.")

    # Convert decimal monetary values into kobo/cents integer units (standard for absolute payment processors)
    amount_in_lowest_currency_units = int(order.total_price * 100)
    reference = order.order_hash
    payload = {
        "email": order.customer_email,
        "amount": amount_in_lowest_currency_units,
        "currency": "NGN",
        "reference": reference,
        "callback_url": redirect_url,
        "metadata": {
            "order_id": order.id,
            "system_source": "chill_and_vibes_backend"
        }
    }
    if redirect_url:
        payload["callback_url"] = redirect_url
        return payload


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verifies that a webhook request genuinely came from Paystack.

    Paystack signs webhook payloads using HMAC-SHA512
    with the Paystack secret key.
    """

    if not signature:
        return False

    secret_key = getattr(settings, "PAYSTACK_SECRET_KEY", None)

    if not secret_key:
        return False

    computed_signature = hmac.new(
        secret_key.encode("utf-8"),
        payload,
        hashlib.sha512,
    ).hexdigest()

    return hmac.compare_digest(
        computed_signature,
        signature,
    )

def fulfill_successful_order(order_hash: str):
    """
    Converts a pending order into PAID and creates individual tickets.

    Returns:
        (order, True)  -> newly fulfilled
        (order, False) -> already fulfilled
    """

    with transaction.atomic():

        # ============================================================
        # LOCK ORDER
        # ============================================================

        order = (
            Order.objects
            .select_for_update()
            .get(order_hash=order_hash)
        )

        # ============================================================
        # IDEMPOTENCY GUARD
        # ============================================================

        if order.status == "PAID":
            return order, False

        # ============================================================
        # MARK ORDER AS PAID
        # ============================================================

        order.status = "PAID"
        order.save(update_fields=["status"])

        # ============================================================
        # CREATE INDIVIDUAL TICKETS
        # ============================================================

        order_line_items = (
            order.items
            .all()
            .select_related("ticket_type")
        )

        for item in order_line_items:
             # Check whether tickets already exist for this item.
            existing_ticket_count = item.tickets.count()

            tickets_needed = (
                item.quantity - existing_ticket_count
            )

            for _ in range(tickets_needed):

                Ticket.objects.create(
                    order_item=item,
                    status="VALID",
                )

        return order, True

# ...
# ..
# .
