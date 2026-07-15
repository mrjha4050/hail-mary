from django.contrib import admin

from .models import Order, Customer, OrderItem

admin.site.register(Order)
admin.site.register(Customer)
admin.site.register(OrderItem)

# Register your models here.
