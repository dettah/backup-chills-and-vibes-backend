from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.orders.services import (
    verify_monnify_webhook_signature,
    verify_monnify_transaction,
    fulfill_successful_order,
)

from apps.tickets.services import (
    dispatch_ticket_delivery_email,
)

from django.core.exceptions import ValidationError
import requests


class PaymentGatewayWebhookAPIView(APIView):
    """
    Receives Monnify transaction-completion webhook events.

    Webhooks are treated as server-to-server payment notifications,
    not as trusted payment proof.

    We verify the signature where available and then verify the
    transaction directly against Monnify before fulfilling.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):

        payload = request.body

        signature = request.headers.get(
            "monnify-signature"
        )


        # ========================================================
        # SIGNATURE
        # ========================================================

        if not verify_monnify_webhook_signature(
            payload=payload,
            signature=signature,
        ):

            return Response(
                {
                    "error": (
                        "Invalid Monnify webhook signature."
                    )
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )


        event_data = request.data

        event_type = event_data.get(
            "eventType"
        )


        # ========================================================
        # ONLY PROCESS SUCCESSFUL TRANSACTIONS
        # ========================================================

        if event_type != (
            "SUCCESSFUL_TRANSACTION"
        ):

            return Response(
                {
                    "status": "ignored",
                    "event": event_type,
                },
                status=status.HTTP_200_OK,
            )


        event_body = event_data.get(
            "eventData",
            {}
        )

        payment_reference = (
            event_body.get(
                "paymentReference"
            )
        )


        if not payment_reference:

            return Response(
                {
                    "error": (
                        "Monnify webhook did not "
                        "contain paymentReference."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


        try:

            transaction_data = (
                verify_monnify_transaction(
                    payment_reference=
                    payment_reference
                )
            )


            if (
                transaction_data.get(
                    "paymentStatus"
                )
                != "PAID"
            ):

                return Response(
                    {
                        "status": "ignored",
                        "reason": (
                            "Transaction is not PAID."
                        ),
                    },
                    status=status.HTTP_200_OK,
                )


            order, was_newly_paid = (
                fulfill_successful_order(
                    order_hash=
                    payment_reference
                )
            )


            if was_newly_paid:

                dispatch_ticket_delivery_email(
                    order_hash=
                    order.order_hash
                )


        except ValidationError as exc:

            return Response(
                {
                    "error": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except requests.RequestException as exc:

            return Response(
                {
                    "error": (
                        "Unable to verify "
                        "transaction with Monnify."
                    ),
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )


        return Response(
            {
                "status": "success"
            },
            status=status.HTTP_200_OK,
        )
        
        # 
        