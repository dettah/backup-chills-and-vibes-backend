# backend/apps/orders/models.py
from decimal import Decimal
from django.db import models
from apps.core.models import TimeStampedModel
from apps.core.utils import generate_secure_token
from apps.events.models import TicketType


class Order(TimeStampedModel):
    """Tracks transaction records securely using guest email addresses."""

    STATUS_CHOICES = (
        ('PENDING', 'Pending Payment'),
        ('PAID', 'Payment Captured'),
        ('CANCELLED', 'Transaction Cancelled'),
    )

    customer_email = models.EmailField(db_index=True)

    order_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True
    )

    # Paystack's unique transaction reference
    payment_reference = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        db_index=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING'
    )

    email_sent = models.BooleanField(
        default=False,
        help_text="Whether the ticket delivery email has been successfully sent."
    )

    email_sent_at = models.DateTimeField(
        null=True,
        blank=True
    )

    total_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )

    def save(self, *args, **kwargs):
        if not self.order_hash:
            self.order_hash = generate_secure_token("ord")

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.order_hash} ({self.status})"


class OrderItem(TimeStampedModel):
    """ breaks down specific quantities bought per order."""
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items")
    ticket_type = models.ForeignKey(TicketType, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.ticket_type.name} (Order: {self.order.order_hash})"


class TicketHold(TimeStampedModel):
    """holds inventory configurations, temporarily, during the ongoing checkout loop."""
    ticket_type = models.ForeignKey(
        TicketType, on_delete=models.CASCADE, related_name="holds")
    email = models.EmailField()
    quantity = models.PositiveIntegerField()
    expires_at = models.DateTimeField()
    is_released = models.BooleanField(default=False)

    def __str__(self):
        return f"Hold for {self.email} ({self.quantity} tickets)"
