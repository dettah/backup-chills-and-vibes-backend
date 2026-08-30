from django.utils.text import slugify
from rest_framework import serializers

from apps.events.models import Event, TicketType


class TicketTypeSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)

    tier = serializers.CharField(
        source="name",
        read_only=True,
    )

    description = serializers.SerializerMethodField()
    perks = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()

    class Meta:
        model = TicketType
        fields = [
            "id",
            "tier",
            "description",
            "price",
            "perks",
        ]

    def get_description(self, obj):
        return f"{obj.name} ticket"

    def get_perks(self, obj):
        return [
            "Event entry",
            f"{obj.quantity_available} tickets remaining",
        ]

    def get_price(self, obj):
        return float(obj.price)

class EventItemSerializer(serializers.ModelSerializer):
    """
    Converts the Django Event model into the frontend EventItem shape.
    """

    slug = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    isoDate = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()

    shortDescription = serializers.CharField(
        source="description",
        read_only=True,
    )

    priceFrom = serializers.SerializerMethodField()
    ticketsAvailable = serializers.SerializerMethodField()
    flyer = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "slug",
            "title",
            "category",
            "date",
            "isoDate",
            "time",
            "location",
            "shortDescription",
            "description",
            "flyer",
            "priceFrom",
            "ticketsAvailable",
        ]

    def get_slug(self, obj):
        return f"{slugify(obj.title)}-{obj.id}"

    def get_date(self, obj):
        return obj.start_time.strftime("%B %d")

    def get_isoDate(self, obj):
        return obj.start_time.strftime("%Y-%m-%d")

    def get_time(self, obj):
        return obj.start_time.strftime("%I:%M %p")

    def get_priceFrom(self, obj):
        lowest_tier = obj.ticket_types.order_by("price").first()

        if lowest_tier:
            return f"₦{int(lowest_tier.price):,}"

        return "₦0"

    def get_ticketsAvailable(self, obj):
        return obj.ticket_types.filter(
            quantity_available__gt=0
        ).exists()

    def get_flyer(self, obj):
        """
        Temporary flyer until Event has an actual image field.
        """
        return "https://images.unsplash.com/photo-1492684223066-81342ee5ff30"


class EventDetailSerializer(EventItemSerializer):
    """
    Detailed event response, including ticket tiers.
    """

    ticketTypes = TicketTypeSerializer(
        source="ticket_types",
        many=True,
        read_only=True,
    )

    class Meta(EventItemSerializer.Meta):
        fields = EventItemSerializer.Meta.fields + [
            "ticketTypes",
        ]