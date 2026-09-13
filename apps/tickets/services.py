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
from PIL import Image, ImageDraw, ImageFont


def build_ticket_verification_url(
    ticket_hash: str
) -> str:
    """
    Builds the canonical public verification URL embedded
    inside every Chill & Vibes ticket QR code.
    """

    return (
        f"https://chillandvibes.com"
        f"/tickets/verify/{ticket_hash}"
    )


def generate_qr_code_url(ticket_hash: str) -> str:
    """
    Generates a QR image URL for a ticket.

    The QR contains the ticket verification URL.
    """

    verification_payload = (
        build_ticket_verification_url(
            ticket_hash
        )
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
        build_ticket_verification_url(
            ticket_hash
        )
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


def generate_ticket_image(
    ticket_hash: str,
    ticket_number: int,
    event_title: str,
    event_date: str,
    event_time: str,
    event_location: str,
    customer_name: str,
    customer_email: str,
    ticket_type: str,
    order_reference: str,
    total_paid: str,
) -> BytesIO:
    """
    Generates a complete branded Chill & Vibes ticket as PNG.

    The ticket uses the Chill & Vibes dark/gold visual language.
    The QR itself deliberately remains black on white with a
    generous quiet zone for reliable scanning.
    """

    width = 1400
    height = 1900

    # ============================================================
    # BRAND COLORS
    # ============================================================

    BACKGROUND = "#07070A"
    GOLD = "#D4AF37"
    GOLD_LIGHT = "#F4D675"
    WHITE = "#FFFFFF"
    MUTED = "#B7B7B7"
    PANEL = "#111217"
    BORDER = "#2A2A30"

    image = Image.new(
        "RGB",
        (width, height),
        BACKGROUND,
    )

    draw = ImageDraw.Draw(image)

    # ============================================================
    # FONTS
    # ============================================================

    def load_font(size: int, bold: bool = False):
        candidates = []

        if bold:
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            ]
        else:
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            ]

        for path in candidates:
            try:
                return ImageFont.truetype(
                    path,
                    size,
                )
            except OSError:
                continue

        return ImageFont.load_default()

    font_brand = load_font(48, True)
    font_event = load_font(58, True)
    font_detail = load_font(30)
    font_label = load_font(24, True)
    font_value = load_font(34, True)
    font_small = load_font(22)
    font_ticket_id = load_font(21)
    font_instruction = load_font(28, True)

    # ============================================================
    # OUTER BORDER
    # ============================================================

    draw.rounded_rectangle(
        (25, 25, width - 25, height - 25),
        radius=36,
        fill=BACKGROUND,
        outline=GOLD,
        width=5,
    )

    # ============================================================
    # TOP BRAND BAR
    # ============================================================

    draw.rounded_rectangle(
        (55, 55, width - 55, 185),
        radius=28,
        fill=PANEL,
    )

    draw.text(
        (width // 2, 95),
        "CHILLS & VIBES",
        fill=GOLD,
        font=font_brand,
        anchor="ma",
    )

    draw.text(
        (width // 2, 150),
        "EVENT TICKET",
        fill=MUTED,
        font=font_small,
        anchor="ma",
    )

    # ============================================================
    # EVENT
    # ============================================================

    draw.text(
        (width // 2, 245),
        event_title,
        fill=WHITE,
        font=font_event,
        anchor="ma",
    )

    draw.text(
        (width // 2, 330),
        f"{event_date} • {event_time}",
        fill=GOLD_LIGHT,
        font=font_detail,
        anchor="ma",
    )

    draw.text(
        (width // 2, 380),
        event_location,
        fill=MUTED,
        font=font_detail,
        anchor="ma",
    )

    # ============================================================
    # DIVIDER
    # ============================================================

    draw.line(
        (120, 445, width - 120, 445),
        fill=BORDER,
        width=3,
    )

    # ============================================================
    # TICKET INFORMATION PANEL
    # ============================================================

    panel_top = 490
    panel_bottom = 920

    draw.rounded_rectangle(
        (
            80,
            panel_top,
            width - 80,
            panel_bottom,
        ),
        radius=28,
        fill=PANEL,
        outline=BORDER,
        width=2,
    )

    left_x = 125
    value_x = 400

    rows = [
        (
            "GUEST",
            customer_name or "Guest",
        ),
        (
            "EMAIL",
            customer_email,
        ),
        (
            "TICKET TYPE",
            ticket_type,
        ),
        (
            "TICKET",
            f"#{ticket_number}",
        ),
        (
            "ORDER",
            order_reference,
        ),
    ]

    y = 545

    for label, value in rows:

        draw.text(
            (left_x, y),
            label,
            fill=GOLD,
            font=font_label,
        )

        draw.text(
            (value_x, y),
            value,
            fill=WHITE,
            font=font_value,
        )

        y += 72

    # ============================================================
    # QR CONTAINER
    # ============================================================

    qr_size = 620

    qr_x = (width - qr_size) // 2
    qr_y = 1000

    # White quiet-zone container.
    #
    # This must remain white so the scanner can reliably identify
    # the QR finder patterns against the ticket's dark background.
    qr_padding = 45

    draw.rounded_rectangle(
        (
            qr_x - qr_padding,
            qr_y - qr_padding,
            qr_x + qr_size + qr_padding,
            qr_y + qr_size + qr_padding,
        ),
        radius=20,
        fill=WHITE,
    )

    # ============================================================
    # QR GENERATION
    # ============================================================

    verification_payload = (
        build_ticket_verification_url(
            ticket_hash
        )
    )

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )

    qr.add_data(
        verification_payload
    )

    qr.make(
        fit=True
    )

    qr_image = qr.make_image(
        fill_color="#07070A",
        back_color="#FFFFFF",
    )

    qr_image = qr_image.convert(
        "RGB"
    )

    qr_image = qr_image.resize(
        (qr_size, qr_size),
        Image.Resampling.NEAREST,
    )

    image.paste(
        qr_image,
        (
            qr_x,
            qr_y,
        ),
    )

    # ============================================================
    # QR INSTRUCTION
    # ============================================================

    draw.text(
        (width // 2, 1680),
        "PRESENT THIS QR CODE AT THE ENTRANCE",
        fill=GOLD_LIGHT,
        font=font_instruction,
        anchor="ma",
    )

    draw.text(
        (width // 2, 1735),
        ticket_hash,
        fill=MUTED,
        font=font_ticket_id,
        anchor="ma",
    )

    draw.text(
        (width // 2, 1790),
        f"Total Paid: ₦{total_paid}",
        fill=WHITE,
        font=font_detail,
        anchor="ma",
    )

    # ============================================================
    # SAVE PNG IN MEMORY
    # ============================================================

    buffer = BytesIO()

    image.save(
        buffer,
        format="PNG",
        optimize=True,
    )

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
        "Your tickets are attached to this email as PNG ticket images.\n"
        "Each ticket contains its own unique QR code.\n\n"
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

            event = item.ticket_type.event

            ticket_buffer = generate_ticket_image(
                ticket_hash=ticket.ticket_hash,
                ticket_number=ticket_counter,
                event_title=event.title,
                event_date=event.start_time.strftime(
                    "%B %d, %Y"
                ),
                event_time=event.start_time.strftime(
                    "%I:%M %p"
                ),
                event_location=event.location,
                customer_name=order.customer_name,
                customer_email=order.customer_email,
                ticket_type=item.ticket_type.name,
                order_reference=order.order_hash,
                total_paid=f"{order.total_price:,.2f}",
            )

            filename = (
                f"chill-vibes-ticket-{ticket_counter}.png"
            )

            attachments.append(
                (
                    filename,
                    ticket_buffer.getvalue(),
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
