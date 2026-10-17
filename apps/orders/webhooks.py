
import requests

from django.core.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.orders.models import Order
from apps.orders.services import (
    verify_paystack_webhook_signature,
    verify_paystack_transaction,
    fulfill_successful_order,
)
from apps.tickets.services import dispatch_ticket_delivery_email


class PaymentGatewayWebhookAPIView(APIView):
    """
    Receives Paystack webhook events.

    The signature authenticates the webhook payload.
    The transaction is also verified directly with Paystack
    before the order can be fulfilled.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        payload = request.body

        signature = request.headers.get(
            "x-paystack-signature"
        )

        if not verify_paystack_webhook_signature(
            payload=payload,
            signature=signature,
        ):
            return Response(
                {"error": "Invalid Paystack webhook signature."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        event_data = request.data

        # Paystack's successful charge event is charge.success.
        if event_data.get("event") != "charge.success":
            return Response(
                {
                    "status": "ignored",
                    "event": event_data.get("event"),
                },
                status=status.HTTP_200_OK,
            )

        transaction = event_data.get("data") or {}
        payment_reference = transaction.get("reference")

        if not payment_reference:
            return Response(
                {
                    "error": (
                        "Paystack webhook did not contain "
                        "a transaction reference."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Look up our order using the gateway reference.
            order = Order.objects.get(
                payment_reference=payment_reference
            )

        except Order.DoesNotExist:
            return Response(
                {"error": "No order matches this payment reference."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Repeated webhook delivery must not fulfil an order twice.
        if order.status == "PAID":
            return Response(
                {"status": "success", "message": "Order already paid."},
                status=status.HTTP_200_OK,
            )

        try:
            # Do not trust the webhook body alone.
            verified = verify_paystack_transaction(
                payment_reference=payment_reference
            )

        except requests.RequestException:
            return Response(
                {"error": "Unable to verify payment with Paystack."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except ValidationError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if verified.get("reference") != order.payment_reference:
            return Response(
                {"error": "Payment reference mismatch."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if verified.get("status") != "success":
            return Response(
                {"status": "ignored", "reason": "Payment not successful."},
                status=status.HTTP_200_OK,
            )

        if verified.get("currency") != "NGN":
            return Response(
                {"error": "Unexpected payment currency."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            amount_paid_kobo = int(verified.get("amount"))
        except (TypeError, ValueError):
            return Response(
                {"error": "Invalid payment amount returned."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        expected_amount_kobo = int(order.total_price * 100)

        if amount_paid_kobo != expected_amount_kobo:
            return Response(
                {"error": "Payment amount does not match the order total."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order, was_newly_paid = fulfill_successful_order(
            order_hash=order.order_hash
        )

        if was_newly_paid:
            try:
                dispatch_ticket_delivery_email(
                    order_hash=order.order_hash
                )
            except Exception as exc:
                # Payment is still successful even if email delivery fails.
                print("Ticket email delivery failed:", exc)

        return Response(
            {"status": "success"},
            status=status.HTTP_200_OK,
        )
