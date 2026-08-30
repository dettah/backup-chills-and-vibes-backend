# backend/apps/orders/management/commands/release_holds.py
from django.core.management.base import BaseCommand
from apps.orders.services import release_expired_holds_atomic

class Command(BaseCommand):
    help = "Finds expired ticket reservations and restores them safely back to available stock."

    def handle(self, *args, **options):
        count = release_expired_holds_atomic()
        if count > 0:
            self.stdout.write(self.style.SUCCESS(f"Successfully released {count} expired ticket hold(s)."))
