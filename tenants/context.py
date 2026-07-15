
import contextvars
from email.policy import default

_current_tenant = contextvars.ContextVar('current_tenant', default=None)

def get_current_tenant():
    return _current_tenant.get()

def set_current_tenant(new_tenant):
    return _current_tenant.set(new_tenant)

def reset_current_tenant(token):
    return _current_tenant.reset(token)