from django.db import models
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.core.models import TimeStampedModel


class Event(TimeStampedModel):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    location = models.CharField(max_length=255)
    capacity = models.PositiveIntegerField()
    category = models.CharField(
        max_length=100,
        default="Parties",
    )

    flyer = models.ImageField(
        upload_to="event_flyers/",
        blank=True,
        null=True,
        help_text="Upload the event flyer/poster."
    )

    is_featured = models.BooleanField(
        default=False,
        help_text="Display this event as the featured event."
    )
    
    class Meta:
        ordering = ["start_time"]
        indexes = [
            models.Index(fields=["start_time"]),
            models.Index(fields=["category"]),
        ]

    def clean(self):
        if (
            self.start_time
            and self.end_time
            and self.start_time >= self.end_time
        ):
            raise ValidationError(
                "Event end time must occur strictly after the start time."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class TicketType(TimeStampedModel):
    """Pricing tier belonging to a specific event."""

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="ticket_types",
    )

    name = models.CharField(max_length=100,  help_text="Example: Regular, VIP, VVIP")
    
    description = models.TextField(
        blank=True,
        help_text="Short description displayed to customers."
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    quantity_available = models.PositiveIntegerField()
    
    highlight = models.BooleanField(
        default=False,
        help_text="Mark this ticket as Most Popular."
    )
    
    perks = models.JSONField(
        default=list,
        blank=True,
        help_text='Enter perks as a JSON list, e.g. ["VIP access", "Free drink"]'
    )

    def __str__(self):
        return f"{self.event.title} - {self.name} (₦{self.price})"
