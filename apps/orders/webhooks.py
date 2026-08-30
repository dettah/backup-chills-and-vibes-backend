from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.orders.services import (
    verify_webhook_signature,
    fulfill_successful_order,
)

from apps.tickets.services import (
    dispatch_ticket_delivery_email,
)


class PaymentGatewayWebhookAPIView(APIView):
    """
    Paystack webhook endpoint.

    Paystack sends a server-to-server notification when a transaction
    succeeds. The webhook signature is verified using the Paystack
    secret key.

    IMPORTANT:
    The webhook does not directly manufacture tickets itself.
    It delegates fulfillment to the idempotent order service.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):

        # ============================================================
        # 1. READ RAW PAYSTACK REQUEST
        # ============================================================

        payload = request.body

        # Paystack sends this header with every webhook request.
        signature = request.headers.get(
            "X-Paystack-Signature"
        )

        # ============================================================
        # 2. VERIFY PAYSTACK SIGNATURE
        # ============================================================

        if not verify_webhook_signature(
            payload=payload,
            signature=signature,
        ):
            return Response(
                {
                    "error": "Unauthorized: Webhook signature mismatch."
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # ============================================================
        # 3. READ EVENT
        # ============================================================

        event_data = request.data

        event_name = event_data.get("event")

        # We only process successful payments.
        if event_name != "charge.success":
            return Response(
                {
                    "status": "ignored",
                    "event": event_name,
                },
                status=status.HTTP_200_OK,
            )

        # ============================================================
        # 4. EXTRACT TRANSACTION DATA
        # ============================================================

        transaction_data = event_data.get(
            "data",
            {}
        )

        reference = transaction_data.get(
            "reference"
        )

        transaction_status = transaction_data.get(
            "status"
        )

        transaction_amount = transaction_data.get(
            "amount"
        )

        if not reference:
            return Response(
                {
                    "error": "Paystack reference missing."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ============================================================
        # 5. CONFIRM TRANSACTION STATUS
        # ============================================================

        if transaction_status != "success":
            return Response(
                {
                    "status": "ignored",
                    "message": "Transaction was not successful.",
                },
                status=status.HTTP_200_OK,
            )

        # ============================================================
        # 6. FIND AND FULFILL ORDER
        # ============================================================

        try:

            order = fulfill_successful_order(
                order_hash=reference
            )

        except Exception as exc:

            return Response(
                {
                    "error": str(exc)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ============================================================
        # 7. SEND TICKET EMAIL
        # ============================================================
        #
        # dispatch_ticket_delivery_email() should itself check
        # email_sent before sending.
        #
        # This prevents duplicate emails if Paystack retries
        # the webhook.
        # ============================================================

        try:

            dispatch_ticket_delivery_email(
                order_hash=order.order_hash
            )

        except Exception as exc:

            # The payment/order should NOT be rolled back simply
            # because email delivery failed.
            #
            # The order is already PAID and tickets already exist.
            # Email can be retried separately.

            print(
                f"Ticket email failed for order "
                f"{order.order_hash}: {exc}"
            )

        # ============================================================
        # 8. ACKNOWLEDGE PAYSTACK
        # ============================================================

        return Response(
            {
                "status": "success",
                "order_hash": order.order_hash,
            },
            status=status.HTTP_200_OK,
        )
