from django.contrib import admin
from .models import Event, TicketType


class TicketTypeInline(admin.TabularInline):
    model = TicketType
    extra = 1
    fields = (
        "name",
        "description",
        "price",
        "quantity_available",
        "highlight",
        "perks",
    )


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "start_time",
        "location",
        "capacity",
        "is_featured",
    )

    list_filter = (
        "category",
        "is_featured",
        "start_time",
    )

    search_fields = (
        "title",
        "location",
        "description",
    )

    list_editable = (
        "is_featured",
    )

    inlines = [
        TicketTypeInline,
    ]


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "event",
        "price",
        "quantity_available",
        "highlight",
    )

    list_filter = (
        "event",
        "highlight",
    )

    search_fields = (
        "name",
        "event__title",
    )