from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError

from apps.tickets.services import (
    validate_and_redeem_ticket_gate,
)


class GateTicketScanAPIView(APIView):
    """
    Endpoint for authorized gate staff scanning ticket QR codes.

    The backend is the authority for ticket validity.
    A successful scan permanently changes the ticket status
    from VALID to SCANNED.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        ticket_hash = request.data.get("ticket_hash")

        if not ticket_hash:
            return Response(
                {
                    "status": "REJECTED",
                    "error": "Ticket hash is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket_hash = str(ticket_hash).strip()

        try:
            ticket = validate_and_redeem_ticket_gate(
                ticket_hash=ticket_hash
            )

            return Response(
                {
                    "status": "APPROVED",
                    "message": (
                        "Ticket valid! "
                        "Welcome to Chill & Vibes."
                    ),
                    "scanned_at": ticket.scanned_at,
                },
                status=status.HTTP_200_OK,
            )

        except ValidationError as exc:
            if hasattr(exc, "messages"):
                error_message = " ".join(
                    str(message)
                    for message in exc.messages
                )
            else:
                error_message = str(exc)

            return Response(
                {
                    "status": "REJECTED",
                    "error": error_message,
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
            
            
            