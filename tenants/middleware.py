
from .context import set_current_tenant, reset_current_tenant
from .models import Tenant

class TenantManager:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = self._resolve_tenant(request)
        token  = set_current_tenant(tenant)
        try:
            response = self.get_response(request)
        finally:
            reset_current_tenant(token)
        return response

    def _resolve_tenant(self, request):

        host = request.get_host().split(':')[0]
        subdomain = host.split('.')[0]
        try:
            return Tenant.objects.get(subdomain=subdomain)
        except Tenant.DoesNotExist:
            return None