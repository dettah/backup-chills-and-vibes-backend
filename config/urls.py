from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from apps.events.views import (
    EventListAPIView,
    EventDetailAPIView,
    EventTicketListAPIView,
)

from apps.orders.views import (
    GuestOrderTicketsAPIView,
    ReserveTicketAPIView,
    CheckoutInitializeAPIView,
    GuestOrderLookupAPIView,
    VerifyPaystackTransactionAPIView,
)

from apps.orders.webhooks import (
    PaymentGatewayWebhookAPIView,
)

from apps.tickets.views import (
    GateTicketScanAPIView,
)


urlpatterns = [
    path(
        "admin/",
        admin.site.urls,
    ),

    # ============================================================
    # EVENTS
    # ============================================================

    path(
        "api/v1/events/",
        EventListAPIView.as_view(),
        name="api-events-list",
    ),

    path(
        "api/v1/events/<int:event_id>/",
        EventDetailAPIView.as_view(),
        name="api-event-detail",
    ),

    path(
        "api/v1/events/<int:event_id>/tickets/",
        EventTicketListAPIView.as_view(),
        name="api-event-ticket-list",
    ),

    # ============================================================
    # ORDERS
    # ============================================================

    path(
        "api/v1/orders/reserve/",
        ReserveTicketAPIView.as_view(),
        name="api-reserve-tickets",
    ),

    path(
        "api/v1/orders/checkout/",
        CheckoutInitializeAPIView.as_view(),
        name="api-checkout-initialize",
    ),

    path(
        'api/v1/orders/verify-payment/',
        VerifyPaystackTransactionAPIView.as_view(),
        name='api-verify-paystack-payment'
    ),

    path(
        "api/v1/orders/lookup/",
        GuestOrderLookupAPIView.as_view(),
        name="api-guest-lookup",
    ),

    path(
        "api/v1/orders/tickets/",
        GuestOrderTicketsAPIView.as_view(),
        name="api-guest-tickets",
    ),

    # ============================================================
    # PAYMENT WEBHOOK
    # ============================================================

    path(
        "api/v1/webhooks/payment/",
        PaymentGatewayWebhookAPIView.as_view(),
        name="api-webhook-payment",
    ),

    # ============================================================
    # TICKET GATE SCANNER
    # ============================================================

    path(
        "api/v1/tickets/gate-scan/",
        GateTicketScanAPIView.as_view(),
        name="api-gate-scan",
    ),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
