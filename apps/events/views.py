from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.events.models import Event, TicketType
from apps.events.serializers import (
    EventItemSerializer,
    EventDetailSerializer,
    TicketTypeSerializer,
)


class EventListAPIView(APIView):
    """
    Returns all events.

    Ticket types are prefetched to avoid N+1 queries when calculating
    ticket availability and starting prices.
    """

    def get(self, request):
        events_queryset = (
            Event.objects
            .all()
            .prefetch_related("ticket_types")
            .order_by("start_time")
        )

        serializer = EventItemSerializer(
            events_queryset,
            many=True,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


class EventDetailAPIView(APIView):
    """
    Returns a single event together with its ticket tiers.
    """

    def get(self, request, event_id):
        try:
            event = (
                Event.objects
                .prefetch_related("ticket_types")
                .get(id=event_id)
            )
        except Event.DoesNotExist:
            return Response(
                {
                    "error": "Event not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = EventDetailSerializer(event)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


class EventTicketListAPIView(APIView):
    """
    Returns ticket tiers for a specific event.

    GET /api/v1/events/<event_id>/tickets/
    """

    def get(self, request, event_id):
        try:
            Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return Response(
                {
                    "error": "Event not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        ticket_types = (
            TicketType.objects
            .filter(event_id=event_id)
            .order_by("price")
        )

        serializer = TicketTypeSerializer(
            ticket_types,
            many=True,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )