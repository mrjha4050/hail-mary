
from django.db import models
from .context import get_current_tenant

class Tenant(models.Model):
    name = models.CharField(max_length=200)
    subdomain = models.CharField(max_length=200, unique=True)

class TenantManager(models.Manager):
    tenant= models.ForeignKey(Tenant, on_delete=models.CASCADE)
    def get_queryset(self):
        tenant = get_current_tenant()
        if tenant is None:
            raise RuntimeError('No tenant found')

        return super().get_queryset().filter(tenant = tenant)

class Order(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    reference = models.CharField(max_length=200)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    objects = TenantManager()
