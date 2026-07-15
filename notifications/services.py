
import  uuid

from .tasks import send_email

def submit_email_job(recipient:str, subject:str, idempotency_key:str = None) -> str:
    key = idempotency_key or str(uuid.uuid4())

    send_email.delay(
        recipient = recipient,
        subject= subject,
        idempotency_key = key,
    )
    return key