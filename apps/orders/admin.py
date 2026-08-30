from django.contrib import admin

from .models import Order, OrderItem, TicketHold


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "ticket_type",
        "quantity",
        "price_at_purchase",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_hash",
        "customer_email",
        "payment_reference",
        "status",
        "total_price",
        "email_sent",
        "email_sent_at",
        "created_at",
    )

    list_filter = (
        "status",
        "email_sent",
        "created_at",
    )

    search_fields = (
        "order_hash",
        "customer_email",
        "payment_reference",
    )

    readonly_fields = (
        "order_hash",
        "payment_reference",
        "created_at",
        "updated_at",
        "email_sent_at",
    )

    inlines = [
        OrderItemInline,
    ]

    ordering = (
        "-created_at",
    )


@admin.register(TicketHold)
class TicketHoldAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "ticket_type",
        "email",
        "quantity",
        "expires_at",
        "is_released",
        "created_at",
    )

    list_filter = (
        "is_released",
        "expires_at",
    )

    search_fields = (
        "email",
        "ticket_type__name",
        "ticket_type__event__title",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    list_select_related = (
        "ticket_type",
    )