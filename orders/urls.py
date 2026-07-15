
from django.urls import path

from . import views

urlpatterns = [
    path('summary/', views.order_summary, name='order-summary'),
    path('customers/<int:customer_id>/summary/', views.customer_orders_summary, name='customer-orders-summary'),
]