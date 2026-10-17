# orders/views.py
import requests
from django.db.models import Prefetch
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.orders.models import Order
from decimal import Decimal

from apps.orders.services import (
    fulfill_successful_order,
    reserve_tickets_atomic,
    initialize_checkout_order,
    initialize_paystack_transaction,
    verify_paystack_transaction,
)


from apps.tickets.services import dispatch_ticket_delivery_email

from django.core.exceptions import ValidationError, PermissionDenied


from apps.orders.selectors import get_order_by_guest_hash

from requests.exceptions import (
    Timeout,
    ConnectionError as RequestsConnectionError,
    RequestException,
)

from apps.tickets.services import (
    dispatch_ticket_delivery_email,
)


class ReserveTicketAPIView(APIView):
    """Endpoint to lock 10-minute temporary stock reservations during checkout."""

    def post(self, request):
        email = request.data.get("email")
        ticket_type_id = request.data.get("ticket_type_id")
        quantity = request.data.get("quantity")

        if not all([email, ticket_type_id, quantity]):
            return Response({"error": "Missing required fields: email, ticket_type_id, or quantity."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            hold = reserve_tickets_atomic(email=email, ticket_type_id=int(
                ticket_type_id), quantity=int(quantity))
            return Response({
                "message": "Ticket stock reserved successfully.",
                "hold_id": hold.id,
                "expires_at": hold.expires_at
            }, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({"error": str(e.message if hasattr(e, 'message') else e)}, status=status.HTTP_400_BAD_REQUEST)


class CheckoutInitializeAPIView(APIView):
    """
    Creates a pending order and initializes Paystack hosted checkout.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = request.data.get("email")

        customer_name = (
            request.data.get("customer_name") or ""
        ).strip()

        customer_phone = (
            request.data.get("customer_phone") or ""
        ).strip()

        hold_ids = request.data.get("hold_ids") or []

        callback_url = settings.PAYSTACK_CALLBACK_URL

        if not email:
            return Response(
                {"error": "Customer email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(hold_ids, list) or not hold_ids:
            return Response(
                {"error": "At least one hold_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # 1. Create the pending order using existing hold logic.
            order = initialize_checkout_order(
                email=email,
                hold_ids=hold_ids,
                customer_name=customer_name,
                customer_phone=customer_phone,
            )

            # 2. Initialize Paystack hosted checkout.
            paystack_transaction = initialize_paystack_transaction(
                order=order,
                redirect_url=callback_url,
            )

            # 3. Save Paystack's reference to the existing order.
            order.payment_reference = (
                paystack_transaction["payment_reference"]
            )

            order.save(update_fields=["payment_reference"])

            # 4. Preserve the frontend's existing response contract.
            return Response(
                {
                    "order_hash": order.order_hash,
                    "total_price": str(order.total_price),
                    "gateway_config": {
                        "payment_reference": (
                            paystack_transaction["payment_reference"]
                        ),
                        "transaction_reference": (
                            paystack_transaction["transaction_reference"]
                        ),
                        "checkout_url": (
                            paystack_transaction["checkout_url"]
                        ),
                        "amount": paystack_transaction["amount"],
                        "currency": "NGN",
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        except ValidationError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except requests.RequestException:
            return Response(
                {
                    "error": (
                        "Unable to communicate with Paystack. "
                        "Please try again."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )



class GuestOrderLookupAPIView(APIView):
    """Secure endpoint for frontends to query public receipt states using tracking tokens."""

    def get(self, request):
        order_hash = request.query_params.get("order_hash")
        email = request.query_params.get("email")

        if not order_hash or not email:
            return Response({"error": "Missing order_hash or email query parameters."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = get_order_by_guest_hash(
                order_hash=order_hash, customer_email=email)
            return Response({
                "order_hash": order.order_hash,
                "customer_email": order.customer_email,
                "status": order.status,
                "total_price": str(order.total_price),
                "created_at": order.created_at
            }, status=status.HTTP_200_OK)
        except PermissionDenied as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)


class GuestOrderTicketsAPIView(APIView):
    """
    Returns the individual tickets generated for a paid order.

    The guest must provide both:
        - order_hash
        - customer email

    This prevents someone from retrieving another customer's tickets
    using only an order reference.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):

        order_hash = request.query_params.get(
            "order_hash"
        )

        email = request.query_params.get(
            "email"
        )

        if not order_hash or not email:
            return Response(
                {
                    "error": (
                        "order_hash and email are required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            order = (
                Order.objects
                .prefetch_related(
                    "items__tickets",
                    "items__ticket_type",
                )
                .get(
                    order_hash=order_hash,
                    customer_email__iexact=email.strip(),
                )
            )

        except Order.DoesNotExist:

            return Response(
                {
                    "error": "Order not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if order.status != "PAID":

            return Response(
                {
                    "error": (
                        "Tickets are not available until "
                        "payment has been confirmed."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        tickets = []

        for item in order.items.all():

            for ticket in item.tickets.all():

                tickets.append(
                    {
                        "ticket_hash": ticket.ticket_hash,
                        "status": ticket.status,
                        "ticket_type": item.ticket_type.name,
                        "price": str(
                            item.price_at_purchase
                        ),
                    }
                )

        return Response(
            {
                "order_hash": order.order_hash,
                "customer_email": order.customer_email,
                "tickets": tickets,
            },
            status=status.HTTP_200_OK
        )



class VerifyPaystackTransactionAPIView(APIView):
    """
    Verifies a payment directly against Paystack.
    The frontend callback is not proof of payment.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        payment_reference = request.data.get(
            "payment_reference"
        )

        if not payment_reference:
            return Response(
                {"error": "Payment reference is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order = Order.objects.get(
                payment_reference=payment_reference
            )
        except Order.DoesNotExist:
            return Response(
                {
                    "error": (
                        "No order was found for this "
                        "payment reference."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Idempotency: never fulfill the same order twice.
        if order.status == "PAID":
            return Response(
                {
                    "status": "success",
                    "message": (
                        "Payment has already been confirmed."
                    ),
                    "order_hash": order.order_hash,
                },
                status=status.HTTP_200_OK,
            )

        try:
            transaction_data = verify_paystack_transaction(
                payment_reference=payment_reference
            )

        except requests.RequestException:
            return Response(
                {
                    "error": (
                        "Unable to verify payment with Paystack."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except ValidationError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate the reference returned by Paystack.
        returned_reference = transaction_data.get("reference")

        if returned_reference != order.payment_reference:
            return Response(
                {"error": "Payment reference mismatch."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # The transaction must have succeeded.
        if transaction_data.get("status") != "success":
            return Response(
                {
                    "status": transaction_data.get("status"),
                    "message": (
                        "Payment has not been completed."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate the currency.
        if transaction_data.get("currency") != "NGN":
            return Response(
                {"error": "Unexpected payment currency."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Paystack reports NGN amounts in kobo.
        amount_paid_kobo = transaction_data.get("amount")

        try:
            amount_paid_kobo = int(amount_paid_kobo)
        except (TypeError, ValueError):
            return Response(
                {"error": "Invalid payment amount returned."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        expected_amount_kobo = int(
            order.total_price * Decimal("100")
        )

        if amount_paid_kobo != expected_amount_kobo:
            return Response(
                {
                    "error": (
                        "Payment amount does not match "
                        "the order total."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fulfill using the existing ticketing logic.
        order, was_newly_paid = fulfill_successful_order(
            order_hash=order.order_hash
        )

        # Email failure must not undo a successful payment.
        if was_newly_paid:
            try:
                dispatch_ticket_delivery_email(
                    order_hash=order.order_hash
                )
            except Exception as exc:
                print(
                    "Ticket email delivery failed:",
                    exc,
                )

        return Response(
            {
                "status": "success",
                "message": "Payment verified successfully.",
                "order_hash": order.order_hash,
            },
            status=status.HTTP_200_OK,
        )

#
