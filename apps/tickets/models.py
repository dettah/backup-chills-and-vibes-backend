from django.db import models
from apps.core.models import TimeStampedModel
from apps.core.utils import generate_secure_token
from apps.orders.models import OrderItem

class Ticket(TimeStampedModel):
    """Generated physical inventory items representing a single unique door QR payload scan."""
    STATUS_CHOICES = (
        ('VALID', 'Active / Eligible for Entry'),
        ('SCANNED', 'Redeemed at Gate'),
        ('CANCELLED', 'Voided / Cancelled'),
    )

    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="tickets")
    ticket_hash = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='VALID')
    scanned_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.ticket_hash:
            self.ticket_hash = generate_secure_token("tkt")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Ticket {self.ticket_hash} - {self.status}"

