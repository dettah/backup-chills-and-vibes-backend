from django.contrib import admin

from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "ticket_hash",
        "get_customer_email",
        "get_ticket_type",
        "get_event",
        "status",
        "scanned_at",
        "created_at",
    )

    list_filter = (
        "status",
        "scanned_at",
        "created_at",
    )

    search_fields = (
        "ticket_hash",
        "order_item__order__customer_email",
        "order_item__order__order_hash",
        "order_item__ticket_type__name",
        "order_item__ticket_type__event__title",
    )

    readonly_fields = (
        "ticket_hash",
        "order_item",
        "scanned_at",
        "created_at",
        "updated_at",
    )

    list_select_related = (
        "order_item",
        "order_item__order",
        "order_item__ticket_type",
        "order_item__ticket_type__event",
    )

    @admin.display(description="Customer")
    def get_customer_email(self, obj):
        return obj.order_item.order.customer_email

    @admin.display(description="Ticket Type")
    def get_ticket_type(self, obj):
        return obj.order_item.ticket_type.name

    @admin.display(description="Event")
    def get_event(self, obj):
        return obj.order_item.ticket_type.event.title
