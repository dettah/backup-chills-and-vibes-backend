# orders/views.py
import requests

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.orders.models import Order
from apps.orders.services import fulfill_successful_order
from apps.tickets.services import dispatch_ticket_delivery_email

from django.core.exceptions import ValidationError, PermissionDenied
from apps.orders.services import reserve_tickets_atomic, initialize_checkout_order, prepare_payment_gateway_payload
from apps.orders.selectors import get_order_by_guest_hash


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
    Creates the pending order and prepares the Paystack transaction.

    The order remains PENDING until Paystack confirms payment.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = request.data.get("email")
        hold_ids = request.data.get("hold_ids", [])

        callback_url = request.data.get(
            "callback_url",
            "http://localhost:5173/checkout"
        )

        if not email:
            return Response(
                {"error": "Customer email is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not hold_ids:
            return Response(
                {"error": "At least one hold_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 1. Create our PENDING order from the ticket holds
            order = initialize_checkout_order(
                email=email,
                hold_ids=hold_ids
            )

            # 2. Prepare the Paystack transaction
            gateway_payload = prepare_payment_gateway_payload(
                order,
                redirect_url=callback_url
            )

            # 3. Extract the reference generated for this transaction
            paystack_reference = gateway_payload["reference"]

            if not paystack_reference:
                raise ValidationError(
                    "Paystack transaction reference was not generated."
                )

            # 4. Store Paystack's reference against our order
            order.payment_reference = paystack_reference
            order.save(update_fields=["payment_reference"])

            return Response(
                {
                    "order_hash": order.order_hash,
                    "total_price": str(order.total_price),
                    "gateway_config": gateway_payload,
                },
                status=status.HTTP_201_CREATED
            )

        except ValidationError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
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


class VerifyPaystackTransactionAPIView(APIView):
    """
    Verifies a Paystack transaction directly from Django.

    The frontend callback is NOT trusted as proof of payment.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        reference = request.data.get("reference")

        if not reference:
            return Response(
                {"error": "Payment reference is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            order = Order.objects.get(
                payment_reference=reference
            )
        except Order.DoesNotExist:
            return Response(
                {
                    "error": "No order was found for this payment reference."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # Already fulfilled
        if order.status == "PAID":
            return Response(
                {
                    "status": "success",
                    "message": "Payment has already been confirmed.",
                    "order_hash": order.order_hash,
                },
                status=status.HTTP_200_OK
            )

        try:
            paystack_response = requests.get(
                f"https://api.paystack.co/transaction/verify/{reference}",
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                    "Cache-Control": "no-cache",
                },
                timeout=15,
            )
        except requests.RequestException:
            return Response(
                {
                    "error": "Unable to contact Paystack."
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        if paystack_response.status_code != 200:
            return Response(
                {
                    "error": "Paystack verification request failed."
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        paystack_data = paystack_response.json()

        if not paystack_data.get("status"):
            return Response(
                {
                    "error": "Paystack returned an unsuccessful verification response."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        transaction_data = paystack_data.get("data", {})

        transaction_status = transaction_data.get("status")
        transaction_reference = transaction_data.get("reference")
        transaction_amount = transaction_data.get("amount")

        # Confirm Paystack reference matches our order
        if transaction_reference != order.payment_reference:
            return Response(
                {
                    "error": "Payment reference mismatch."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if transaction_status != "success":
            return Response(
                {
                    "status": transaction_status,
                    "message": "Payment has not been completed."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        expected_amount = int(order.total_price * 100)

        if int(transaction_amount or 0) != expected_amount:
            return Response(
                {
                    "error": "Payment amount does not match order amount."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Payment is genuinely confirmed by Paystack.
        # Fulfillment should itself be idempotent.
        order, was_newly_paid = fulfill_successful_order(
            order_hash=order.order_hash
        )

        if was_newly_paid:
            dispatch_ticket_delivery_email(
                order_hash=order.order_hash
            )

        return Response(
            {
                "status": "success",
                "message": "Payment verified successfully.",
                "order_hash": order.order_hash,
            },
            status=status.HTTP_200_OK
        )
#
