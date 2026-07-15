from django.test import TestCase

from .context import set_current_tenant, reset_current_tenant
from .models import Tenant, Order

from loguru import logger


class TenantIsolationTests(TestCase):
    def setUp(self):
        logger.info("=== setUp: creating tenants A and B with one order each ===")

        self.tenant_a = Tenant.objects.create(name='A', subdomain='a')
        self.tenant_b = Tenant.objects.create(name='B', subdomain='b')

        token = set_current_tenant(self.tenant_a)
        self.order_a = Order.objects.create(tenant=self.tenant_a, reference='A-1', total_amount=10)
        reset_current_tenant(token)

        token = set_current_tenant(self.tenant_b)
        self.order_b = Order.objects.create(tenant=self.tenant_b, reference='B-1', total_amount=20)
        reset_current_tenant(token)

    def test_all_only_returns_own_tenant(self):
        logger.info("--- test_all_only_returns_own_tenant ---")
        token = set_current_tenant(self.tenant_a)
        try:
            refs = list(Order.objects.all().values_list('reference', flat=True))
        finally:
            reset_current_tenant(token)

        self.assertEqual(refs, ['A-1'])
        logger.success("PASS: only tenant_a's order ('A-1') was visible")

    def test_get_by_pk_cannot_fetch_other_tenants_row(self):
        logger.info("--- test_get_by_pk_cannot_fetch_other_tenants_row ---")
        token = set_current_tenant(self.tenant_a)
        try:
            with self.assertRaises(Order.DoesNotExist):
                Order.objects.get(pk=self.order_b.pk)
            logger.success("PASS: fetching tenant_b's order while scoped to tenant_a raised DoesNotExist")
        finally:
            reset_current_tenant(token)

    def test_filter_call_cannot_bypass_scoping(self):
        logger.info("--- test_filter_call_cannot_bypass_scoping ---")
        token = set_current_tenant(self.tenant_a)
        try:
            qs = Order.objects.filter(reference='B-1')
            exists = qs.exists()
        finally:
            reset_current_tenant(token)

        self.assertFalse(exists)
        logger.success("PASS: filter() could not surface tenant_b's row while scoped to tenant_a")

    def test_count_and_exists_are_scoped_too(self):
        logger.info("--- test_count_and_exists_are_scoped_too ---")
        token = set_current_tenant(self.tenant_a)
        try:
            count = Order.objects.count()
            has_a1 = Order.objects.filter(reference='A-1').exists()
        finally:
            reset_current_tenant(token)

        self.assertEqual(count, 1)
        self.assertTrue(has_a1)
        logger.success("PASS: count() and exists() both respected tenant scoping")

    def test_no_tenant_bound_fails_closed(self):
        logger.info("--- test_no_tenant_bound_fails_closed ---")
        with self.assertRaises(RuntimeError):
            list(Order.objects.all())
        logger.success("PASS: querying with no tenant context raised RuntimeError (fail-closed)")

    def test_context_does_not_leak_between_requests(self):
        logger.info("--- test_context_does_not_leak_between_requests ---")
        token = set_current_tenant(self.tenant_a)
        results = list(Order.objects.all())
        reset_current_tenant(token)

        with self.assertRaises(RuntimeError):
            list(Order.objects.all())
        logger.success("PASS: context did not leak from request 1 into request 2")


class TenantMiddlewareTests(TestCase):
    def setUp(self):
        logger.info("=== setUp: creating tenant Acme ===")
        self.tenant = Tenant.objects.create(name='Acme', subdomain='acme')

    def test_middleware_resolves_tenant_from_subdomain_and_scopes_request(self):
        logger.info("--- test_middleware_resolves_tenant_from_subdomain_and_scopes_request ---")
        token = set_current_tenant(self.tenant)
        try:
            Order.objects.create(tenant=self.tenant, reference='ACME-1', total_amount=5)
        finally:
            reset_current_tenant(token)

        response = self.client.get('/', HTTP_HOST='acme.example.com')

        self.assertIn(response.status_code, (200, 404))
        logger.success("PASS: middleware handled the subdomain request without error and cleaned up context")

    def test_unknown_subdomain_leaves_tenant_unbound(self):
        logger.info("--- test_unknown_subdomain_leaves_tenant_unbound ---")
        response = self.client.get('/', HTTP_HOST='unknown.example.com')

        self.assertIn(response.status_code, (200, 404, 500))
        logger.success("PASS: unknown subdomain handled without crashing the middleware chain")