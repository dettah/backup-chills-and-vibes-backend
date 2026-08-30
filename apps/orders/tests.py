from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.core.utils import generate_secure_token
from apps.events.models import Event, TicketType
from apps.orders.models import Order, OrderItem
from apps.tickets.models import Ticket

class CoreInfrastructureTestCase(TestCase):
    
    def setUp(self):
        """Set up testing context records."""
        self.event = Event.objects.create(
            title="Afrobeats Fest 2026",
            start_time=timezone.now() + timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=6),
            location="Eko Atlantic, Lagos",
            capacity=5000
        )
        self.regular_tier = TicketType.objects.create(
            event=self.event,
            name="Regular",
            price=Decimal("50.00"),
            quantity_available=200
        )

    def test_secure_token_formatting(self):
        """Tokens should output unique values and match custom domain type labels."""
        order_token = generate_secure_token("ord")
        ticket_token = generate_secure_token("tkt")
        
        self.assertTrue(order_token.startswith("ord_"))
        self.assertTrue(ticket_token.startswith("tkt_"))
        self.assertNotEqual(order_token, ticket_token)

    def test_order_hash_hooks_lifecycle(self):
        """Saving an Order records secure random hashes and sets status flags automatically."""
        order = Order.objects.create(
            customer_email="checkout_user@example.com",
            total_price=Decimal("100.00")
        )
        self.assertIsNotNone(order.order_hash)
        self.assertTrue(order.order_hash.startswith("ord_"))
        self.assertEqual(order.status, 'PENDING')

    def test_event_time_integrity_validation(self):
        """Database validation constraints should block impossible chronological end configurations."""
        invalid_event = Event(
            title="Broken Time Concert",
            start_time=timezone.now() + timezone.timedelta(days=3),
            end_time=timezone.now() + timezone.timedelta(days=2),
            location="Stadium Hall",
            capacity=50
        )
        with self.assertRaises(ValidationError):
            invalid_event.save()

    def test_multi_ticket_generation_allocation(self):
        """An order item buying multiple tickets must map separate unique tracking IDs cleanly."""
        order = Order.objects.create(
            customer_email="guest_checkout@example.com",
            status='PAID',
            total_price=Decimal("100.00")
        )
        item = OrderItem.objects.create(
            order=order,
            ticket_type=self.regular_tier,
            quantity=2,
            price_at_purchase=self.regular_tier.price
        )
        
        tkt1 = Ticket.objects.create(order_item=item)
        tkt2 = Ticket.objects.create(order_item=item)

        self.assertEqual(item.tickets.count(), 2)
        self.assertNotEqual(tkt1.ticket_hash, tkt2.ticket_hash)
        self.assertTrue(tkt1.ticket_hash.startswith("tkt_"))
        
        
        # Append these methods cleanly inside your CoreInfrastructureTestCase class in backend/apps/orders/tests.py

    def test_successful_ticket_hold_reservation(self):
        """Verify that booking requests correctly hold stock levels and return secure trackers."""
        from apps.orders.services import reserve_tickets_atomic
        from apps.orders.models import TicketHold

        initial_stock = self.regular_tier.quantity_available # 200
        
        # Attempt to buy 4 regular tickets
        hold = reserve_tickets_atomic(
            email="rush_buyer@example.com",
            ticket_type_id=self.regular_tier.id,
            quantity=4
        )
        
        # Refresh configuration record from memory
        self.regular_tier.refresh_from_db()
        
        self.assertEqual(self.regular_tier.quantity_available, initial_stock - 4)
        self.assertEqual(hold.quantity, 4)
        self.assertEqual(hold.is_released, False)

    def test_insufficient_stock_raises_validation_error(self):
        """A reservation purchase requesting more than the available inventory must be instantly rejected."""
        from apps.orders.services import reserve_tickets_atomic
        
        # regular_tier only has 200 tickets in setUp. Let's ask for 201.
        with self.assertRaises(ValidationError):
            reserve_tickets_atomic(
                email="greedy_buyer@example.com",
                ticket_type_id=self.regular_tier.id,
                quantity=201
            )

    def test_expired_hold_reversion_lifecycle(self):
        """ Lapsed checkout reservation locks must return their quantities back to the core stock pool."""
        from apps.orders.services import reserve_tickets_atomic, release_expired_holds_atomic
        from django.utils import timezone
        
        initial_stock = self.regular_tier.quantity_available # 200
        
        # Create a hold that we explicitly force to look expired
        hold = reserve_tickets_atomic(
            email="forgetful_buyer@example.com",
            ticket_type_id=self.regular_tier.id,
            quantity=10
        )
        
        self.regular_tier.refresh_from_db()
        self.assertEqual(self.regular_tier.quantity_available, initial_stock - 10) # 190
        
        # Force expiration timestamp into the past for sandbox emulation
        hold.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        hold.save()
        
        # Fire background tracking engine cleanup sweep
        processed_holds = release_expired_holds_atomic()
        
        self.regular_tier.refresh_from_db()
        hold.refresh_from_db()
        
        self.assertEqual(processed_holds, 1)
        self.assertEqual(hold.is_released, True)
        self.assertEqual(self.regular_tier.quantity_available, initial_stock) # Restored back to 200!
    
        # Append these methods cleanly inside your CoreInfrastructureTestCase class in backend/apps/orders/tests.py

    def test_ghost_profile_resolver_normalization(self):
        """Verify that the identity selector normalizes emails to prevent duplicate routing states."""
        from apps.orders.selectors import resolve_ghost_profile

        raw_email = "  ThEtA_bUyEr@ExAmPlE.cOm  "
        processed_email = resolve_ghost_profile(raw_email)

        # Trims white spaces and forces lowercase format matching
        self.assertEqual(processed_email, "theta_buyer@example.com")

    def test_secure_guest_route_guard_success(self):
        """A user should access order records when providing both a matching hash and their email."""
        from apps.orders.selectors import get_order_by_guest_hash
        from apps.orders.models import Order
        from decimal import Decimal

        order = Order.objects.create(
            customer_email="verified_guest@example.com",
            total_price=Decimal("75.00")
        )

        # Guard should authorize access and return the order model instantiation object
        fetched_order = get_order_by_guest_hash(
            order_hash=order.order_hash, 
            customer_email="verified_guest@example.com"
        )
        self.assertEqual(fetched_order.id, order.id)

    def test_secure_guest_route_guard_denial_on_mismatched_email(self):
        """The route guard must block requests if a valid hash is paired with an incorrect email."""
        from apps.orders.selectors import get_order_by_guest_hash
        from apps.orders.models import Order
        from django.core.exceptions import PermissionDenied
        from decimal import Decimal

        order = Order.objects.create(
            customer_email="real_owner@example.com",
            total_price=Decimal("75.00")
        )

        # An attacker trying to view the order using a guessed hash must be instantly blocked
        with self.assertRaises(PermissionDenied):
            get_order_by_guest_hash(
                order_hash=order.order_hash, 
                customer_email="attacker_email@example.com"
            )

    def test_secure_guest_route_guard_denial_on_invalid_hash(self):
        """The route guard must throw a PermissionDenied exception if the lookup hash does not exist."""
        from apps.orders.selectors import get_order_by_guest_hash
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            get_order_by_guest_hash(
                order_hash="ord_fakehash1234567890", 
                customer_email="anyone@example.com"
            )

    def test_checkout_initialization_success_and_math_aggregation(self):
        """Verify checkout correctly aggregates multi-item ticket holds and computes exact balances."""
        from apps.orders.services import reserve_tickets_atomic, initialize_checkout_order
        
        # Instantiate an alternate tier to test a multi-product checkout basket
        vip_tier = TicketType.objects.create(
            event=self.event,
            name="VIP Experience",
            price=Decimal("500.00"),
            quantity_available=20
        )
        
        # Create separate inventory reservation hooks under a uniform email key
        buyer = "checkout_champion@example.com"
        hold1 = reserve_tickets_atomic(buyer, self.regular_tier.id, quantity=3)  # 3 x $50 = $150
        hold2 = reserve_tickets_atomic(buyer, vip_tier.id, quantity=2)          # 2 x $500 = $1000
        
        # Fire initialization engine
        order = initialize_checkout_order(email=buyer, hold_ids=[hold1.id, hold2.id])
        
        self.assertEqual(order.status, 'PENDING')
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(order.total_price, Decimal('1150.00'))  # Assert precise financial summation

    def test_checkout_fails_on_expired_reservation_holds(self):
        """The checkout engine must reject configuration pathways containing expired or invalid holds."""
        from apps.orders.services import reserve_tickets_atomic, initialize_checkout_order
        from django.utils import timezone
        
        buyer = "late_buyer@example.com"
        hold = reserve_tickets_atomic(buyer, self.regular_tier.id, quantity=1)
        
        # Artificially expire the hold record state
        hold.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        hold.save()
        
        with self.assertRaises(ValidationError):
            initialize_checkout_order(email=buyer, hold_ids=[hold.id])

    def test_payment_gateway_payload_formatting(self):
        """Payload arrays passed out to external processing vendors must present structural integrity parameters."""
        from apps.orders.services import initialize_checkout_order, prepare_payment_gateway_payload
        from apps.orders.services import reserve_tickets_atomic
        
        buyer = "gateway_tester@example.com"
        hold = reserve_tickets_atomic(buyer, self.regular_tier.id, quantity=2)  # 2 x $50 = $100
        order = initialize_checkout_order(buyer, [hold.id])
        
        payload = prepare_payment_gateway_payload(order, redirect_url="https://chillandvibes.com")
        
        self.assertEqual(payload["email"], buyer)
        self.assertEqual(payload["amount"], 10000)  # Verify $100 correctly transforms into 10000 cents/kobo units
        self.assertEqual(payload["reference"], order.order_hash)
        self.assertTrue(payload["reference"].startswith("ord_"))


    # Append these methods inside your CoreInfrastructureTestCase class in backend/apps/orders/tests.py

    def test_webhook_signature_verification_success(self):
        """Webhooks with matching payload signatures must pass validation filters securely."""
        from apps.orders.services import verify_webhook_signature
        import hmac
        import hashlib

        raw_payload = b'{"event": "charge.success", "data": {"reference": "ord_123"}}'
        secret_key = "test_gateway_secret"
        
        # Pre-compute valid expected hash
        valid_sig = hmac.new(
            secret_key.encode('utf-8'),
            raw_payload,
            hashlib.sha256
        ).hexdigest()

        is_valid = verify_webhook_signature(raw_payload, valid_sig, secret_key=secret_key)
        self.assertTrue(is_valid)

    def test_webhook_signature_verification_rejection(self):
        """Webhooks containing mutated or fake signatures must be flatly rejected."""
        from apps.orders.services import verify_webhook_signature

        raw_payload = b'{"event": "charge.success"}'
        is_valid = verify_webhook_signature(raw_payload, "fake_signature_hash", secret_key="secret")
        self.assertFalse(is_valid)

    def test_order_fulfillment_ticket_factory_generation(self):
        """Fulfilling an order successfully should set statuses to PAID and spin up individual QR tickets."""
        from apps.orders.services import reserve_tickets_atomic, initialize_checkout_order, fulfill_successful_order
        from apps.tickets.models import Ticket

        buyer = "webhook_recipient@example.com"
        # Reserve a multi-ticket block of 3 items
        hold = reserve_tickets_atomic(buyer, self.regular_tier.id, quantity=3)
        order = initialize_checkout_order(buyer, [hold.id])

        self.assertEqual(order.status, 'PENDING')
        
        # Fire async execution hook simulator
        paid_order = fulfill_successful_order(order.order_hash)
        
        # Refresh instance conditions
        paid_order.refresh_from_db()
        self.assertEqual(paid_order.status, 'PAID')
        
        # Extract individual tickets across the target line breakdown item
        line_item = paid_order.items.first()
        ticket_count = Ticket.objects.filter(order_item=line_item).count()
        
        # Verify that exactly 3 distinct row instances are generated in the DB
        self.assertEqual(ticket_count, 3)
        
        # Pull generated tickets and assert each unique hash starts with tkt_
        sample_ticket = Ticket.objects.filter(order_item=line_item).first()
        self.assertTrue(sample_ticket.ticket_hash.startswith("tkt_"))
        self.assertEqual(sample_ticket.status, 'VALID')

    # Append these methods cleanly inside your CoreInfrastructureTestCase class in backend/apps/orders/tests.py

    def test_qr_code_url_generation_formatting(self):
        """The QR utility should correctly format and URL-encode ticket verification hashes into image charts."""
        from apps.tickets.services import generate_qr_code_url
        
        sample_hash = "tkt_alpha12345"
        qr_url = generate_qr_code_url(sample_hash)
        
        self.assertIn("tkt_alpha12345", qr_url)
        self.assertTrue(qr_url.startswith("https://qrserver.com"))

    def test_ticket_email_dispatch_lifecycle(self):
        """Sending a ticket email for a paid order should generate a message and route it to the user's inbox."""
        from django.core import mail
        from apps.orders.services import reserve_tickets_atomic, initialize_checkout_order, fulfill_successful_order
        from apps.tickets.services import dispatch_ticket_delivery_email

        buyer_email = "concert_fanatic@example.com"
        
        # Build complete baseline transaction loop up to PAID state
        hold = reserve_tickets_atomic(buyer_email, self.regular_tier.id, quantity=2)
        order = initialize_checkout_order(buyer_email, [hold.id])
        fulfill_successful_order(order.order_hash)
        
        # Wipe any existing mock outboxes to ensure absolute counts
        mail.outbox = []
        
        # Fire dispatch system
        emails_sent = dispatch_ticket_delivery_email(order.order_hash)
        
        # Verify Django standard mail utilities records the actions perfectly
        self.assertEqual(emails_sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        
        # Validate metadata components match expected string fields
        dispatched_message = mail.outbox[0]
        self.assertEqual(dispatched_message.to, [buyer_email])
        self.assertIn(order.order_hash, dispatched_message.body)
        self.assertIn("https://qrserver.com", dispatched_message.body)

    # Append these methods cleanly inside your CoreInfrastructureTestCase class in backend/apps/orders/tests.py

    def test_gate_control_successful_redemption(self):
        """A valid ticket hash must be authorized at the gate and marked as scanned with a timestamp."""
        from apps.orders.services import reserve_tickets_atomic, initialize_checkout_order, fulfill_successful_order
        from apps.tickets.services import validate_and_redeem_ticket_gate
        from apps.tickets.models import Ticket

        # Step 1: Create a valid paid ticket
        buyer = "concert_goer@example.com"
        hold = reserve_tickets_atomic(buyer, self.regular_tier.id, quantity=1)
        order = initialize_checkout_order(buyer, [hold.id])
        fulfill_successful_order(order.order_hash)

        # Step 2: Grab the manufactured ticket
        ticket = Ticket.objects.filter(order_item__order=order).first()
        self.assertEqual(ticket.status, 'VALID')
        self.assertIsNone(ticket.scanned_at)

        # Step 3: Scan it at the gate
        redeemed_ticket = validate_and_redeem_ticket_gate(ticket.ticket_hash)

        self.assertEqual(redeemed_ticket.status, 'SCANNED')
        self.assertIsNotNone(redeemed_ticket.scanned_at)

    def test_gate_control_blocks_double_scan_fraud(self):
        """The gate validator must block a ticket from being reused if it has already been scanned."""
        from apps.orders.services import reserve_tickets_atomic, initialize_checkout_order, fulfill_successful_order
        from apps.tickets.services import validate_and_redeem_ticket_gate
        from apps.tickets.models import Ticket

        buyer = "scammer_target@example.com"
        hold = reserve_tickets_atomic(buyer, self.regular_tier.id, quantity=1)
        order = initialize_checkout_order(buyer, [hold.id])
        fulfill_successful_order(order.order_hash)

        ticket = Ticket.objects.filter(order_item__order=order).first()

        # First scan: Allowed
        validate_and_redeem_ticket_gate(ticket.ticket_hash)

        # Second scan (e.g. trying to pass a screenshot to a friend): Must be flatly rejected
        with self.assertRaises(ValidationError):
            validate_and_redeem_ticket_gate(ticket.ticket_hash)

    def test_gate_control_rejects_nonexistent_hash(self):
        """The gate system must throw an exception if the scanned payload code is entirely invalid or guessed."""
        from apps.tickets.services import validate_and_redeem_ticket_gate

        with self.assertRaises(ValidationError):
            validate_and_redeem_ticket_gate("tkt_fake_random_hash_code_999")




