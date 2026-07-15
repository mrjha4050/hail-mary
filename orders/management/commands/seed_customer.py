import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Customer ,Order, OrderItem

CUSTOMERS = [
    ('Alice', 'alice@example.com'),
    ('Bob', 'bob@example.com'),
    ('Charlie', 'charlie@example.com'),
    ('Diana', 'diana@example.com'),
    ('Ethan', 'ethan@example.com'),
    ('Fiona', 'fiona@example.com'),
    ('George', 'george@example.com'),
    ('Hannah', 'hannah@example.com'),
    ('Ivan', 'ivan@example.com'),
    ('Julia', 'julia@example.com'),
]
PRODUCTS = ['Widget', 'Gadget', 'Gizmo', 'Doohickey', 'Thingamajig']
STATUSES = [s for s, _ in Order.STATUS_CHOICES]


class Command(BaseCommand):
    help = 'Seed 10 customers, each with 50-200 orders (2-4 items each), for the /api/orders/summary/ scenario'

    def handle(self, *args, **options):
        OrderItem.objects.all().delete()
        Order.objects.filter(customer__isnull=False).delete()
        Customer.objects.all().delete()

        now = timezone.now()
        total_orders = 0
        total_items = 0

        for name, email in CUSTOMERS:
            customer = Customer.objects.create(name=name, email=email)
            order_count = random.randint(50, 200)
            for _ in range(order_count):
                order = Order.objects.create(
                    customer=customer,
                    customer_name=name,
                    status=random.choice(STATUSES),
                    total_amount=0,
                    created_at=now - timedelta(days=random.randint(0, 180)),
                )
                items = [
                    OrderItem(
                        order=order,
                        product_name=random.choice(PRODUCTS),
                        quantity=random.randint(1, 5),
                        unit_price=round(random.uniform(5, 100), 2),
                    )
                    for _ in range(random.randint(2, 4))
                ]
                OrderItem.objects.bulk_create(items)
                order.total_amount = sum(i.quantity * i.unit_price for i in items)
                order.save(update_fields=['total_amount'])
                total_orders += 1
                total_items += len(items)

        self.stdout.write(self.style.SUCCESS(
            f'Created {len(CUSTOMERS)} customers, {total_orders} orders, {total_items} order items'
        ))
