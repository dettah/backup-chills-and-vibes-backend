# backend/apps/tickets/services.py
import urllib.parse
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from apps.orders.models import Order
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.tickets.models import Ticket
from django.db import transaction
from io import BytesIO
import qrcode


def generate_qr_code_url(ticket_hash: str) -> str:
    """
    Generates a QR image URL for a ticket.

    The QR contains the ticket verification URL.
    """

    verification_payload = (
        f"https://chillandvibes.com/tickets/verify/{ticket_hash}"
    )

    encoded_data = urllib.parse.quote(
        verification_payload,
        safe=""
    )

    return (
        "https://api.qrserver.com/v1/create-qr-code/"
        f"?size=500x500&data={encoded_data}"
    )


def generate_qr_code_image(ticket_hash: str) -> BytesIO:
    """
    Generates an in-memory PNG QR code for a ticket.
    """

    verification_payload = (
        f"https://chillandvibes.com/tickets/verify/{ticket_hash}"
    )

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )

    qr.add_data(verification_payload)
    qr.make(fit=True)

    image = qr.make_image()

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer


def dispatch_ticket_delivery_email(order_hash: str) -> int:
    """
    Sends a completed order receipt containing individual QR ticket images.
    """

    order = (
        Order.objects
        .prefetch_related(
            "items__tickets",
            "items__ticket_type"
        )
        .get(order_hash=order_hash)
    )
    
    if order.status != "PAID":
        return 0
    if order.email_sent:
        return 0

    subject = "Your Chill & Vibes Tickets Are Ready! 🎟️"

    ticket_counter = 1

    text_body = (
        "Hello,\n\n"
        "Thank you for choosing Chill & Vibes.\n"
        "Your payment was received successfully.\n\n"
        f"Order Reference: {order.order_hash}\n"
        f"Total Paid: ₦{order.total_price:,.2f}\n\n"
        "Your tickets are attached to this email as QR codes.\n\n"
    )

    html_body = f"""
    <html>
        <body>
            <h2>Your Chill & Vibes Tickets Are Ready! 🎟️</h2>

            <p>
                Thank you for choosing Chill & Vibes.
                Your payment was received successfully.
            </p>

            <p>
                <strong>Order Reference:</strong>
                {order.order_hash}
            </p>

            <p>
                <strong>Total Paid:</strong>
                ₦{order.total_price:,.2f}
            </p>

            <hr>

            <h3>Your Tickets</h3>
    """

    attachments = []

    for item in order.items.all():
        for ticket in item.tickets.all():

            qr_buffer = generate_qr_code_image(
                ticket.ticket_hash
            )

            filename = (
                f"chill-vibes-ticket-{ticket_counter}.png"
            )

            attachments.append(
                (
                    filename,
                    qr_buffer.getvalue(),
                    "image/png"
                )
            )

            text_body += (
                f"Ticket #{ticket_counter}\n"
                f"Type: {item.ticket_type.name}\n"
                f"Ticket ID: {ticket.ticket_hash}\n\n"
            )

            html_body += f"""
                <div>
                    <h4>Ticket #{ticket_counter}</h4>
                    <p>
                        <strong>Type:</strong>
                        {item.ticket_type.name}
                    </p>
                    <p>
                        Ticket ID:
                        {ticket.ticket_hash}
                    </p>
                    <p>
                        Your QR code is attached to this email.
                    </p>
                </div>

                <hr>
            """

            ticket_counter += 1

    html_body += f"""
            <p>
                <strong>Order Reference:</strong>
                {order.order_hash}
            </p>

            <p>
                Enjoy the show!<br>
                The Chill & Vibes Team
            </p>
        </body>
    </html>
    """

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(
            settings,
            "DEFAULT_FROM_EMAIL",
            "tickets@chillandvibes.com"
        ),
        to=[order.customer_email],
    )

    email.attach_alternative(
        html_body,
        "text/html"
    )

    for filename, content, mimetype in attachments:
        email.attach(
            filename,
            content,
            mimetype
        )
        
     # Actually send the email.
    sent_count = email.send()

    # Only mark as sent if Django's email backend reports success.
    if sent_count > 0:
        order.email_sent = True
        order.email_sent_at = timezone.now()

        order.save(
            update_fields=[
                "email_sent",
                "email_sent_at"
            ]
        )

    return sent_count


def validate_and_redeem_ticket_gate(ticket_hash: str) -> Ticket:
    """
    Validates a ticket's status at the entrance gate using an atomic row lock.
    If valid, it permanently marks it as SCANNED and stamps the arrival time.
    Throws a ValidationError if the ticket is already used or cancelled.
    """
    with transaction.atomic():
        try:
            # Lock the row immediately to prevent rapid double-scanning fraud attacks
            ticket = Ticket.objects.select_for_update().get(ticket_hash=ticket_hash)
        except Ticket.DoesNotExist:
            raise ValidationError(
                "Access Denied: Ticket code does not exist in our registry.")

        # Check if the ticket has already been checked in
        if ticket.status == 'SCANNED':
            raise ValidationError(
                f"Access Denied: Ticket was already scanned on {ticket.scanned_at.strftime('%Y-%m-%d %H:%M:%S')} UTC."
            )

        # Check if the ticket was voided or cancelled due to refunds
        if ticket.status == 'CANCELLED':
            raise ValidationError(
                "Access Denied: This ticket has been voided or cancelled.")

        # Ticket is perfectly valid! Redeem it immediately
        ticket.status = 'SCANNED'
        ticket.scanned_at = timezone.now()
        ticket.save()

        return ticket
