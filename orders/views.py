
from django.db.models import Sum
from .models import Order
from django.http import JsonResponse, HttpResponseNotFound


def order_summary(request):
    orders = Order.objects.all()

    customer = request.GET.get('customer')
    if customer:
        orders = orders.filter(customer_name__icontains=customer)

    status = request.GET.get('status')
    if status:
        orders = orders.filter(status=status)

    start_date = request.GET.get('start_date')
    if start_date:
        orders = orders.filter(created_at__date__gte=start_date)

    end_date = request.GET.get('end_date')
    if end_date:
        orders = orders.filter(created_at__date__lte=end_date)

    total = orders.aggregate(total=Sum('total_amount'))['total'] or 0

    return JsonResponse({
        'count': orders.count(),
        'total_amount': total,
        'filters': {
            'customer': customer,
            'status': status,
            'start_date': start_date,
            'end_date': end_date,
        },
    })


def customer_orders_summary(request, customer_id):
    """Per-order breakdown for one customer's dashboard: status, item count, item total.

    ?fixed=1 selects the select_related/prefetch_related version for A/B profiling
    against the N+1 path below (see incident log, Section 1).
    """
    if request.GET.get('fixed') == '1':
        orders = Order.objects.filter(customer_id=customer_id) \
            .select_related('customer') \
            .prefetch_related('items')
    else:
        orders = Order.objects.filter(customer_id=customer_id)

    orders = list(orders)
    if not orders:
        return HttpResponseNotFound('no orders for that customer')

    rows = []
    for order in orders:
        items = order.items.all()
        rows.append({
            'order_id': order.id,
            'customer_name': order.customer.name, 
            'status': order.status,
            'item_count': len(items),
            'items_total': sum(i.quantity * i.unit_price for i in items),
        })

    return JsonResponse({'customer_id': customer_id, 'orders': rows})
