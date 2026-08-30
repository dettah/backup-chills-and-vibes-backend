# backend/apps/tickets/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from apps.tickets.services import validate_and_redeem_ticket_gate

class GateTicketScanAPIView(APIView):
    """Endpoint for bouncers scanning physical entry door QR codes."""
    def post(self, request):
        ticket_hash = request.data.get("ticket_hash")
        
        if not ticket_hash:
            return Response({"error": "Missing ticket_hash payload parameters."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ticket = validate_and_redeem_ticket_gate(ticket_hash=ticket_hash)
            return Response({
                "status": "APPROVED",
                "message": "Ticket valid! Welcome to Chill & Vibes.",
                "scanned_at": ticket.scanned_at
            }, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({
                "status": "REJECTED",
                "error": str(e.message if hasattr(e, 'message') else e)
            }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
