from django.utils import timezone
from loguru import logger
from celery import shared_task , Task

from notifications.exception import RateLimitExceeded
from notifications.models import EmailJob, DeadLetterJob
from notifications.rate_limiter import SlidingWindowRateLimiter

EMAIL_RATE_LIMIT = 200
EMAIL_RATE_WINDOW = 60

_limiter = SlidingWindowRateLimiter(
    key="ratelimit:email",
    limit=EMAIL_RATE_LIMIT,
    window_seconds=EMAIL_RATE_WINDOW,
)

def send_via_provider(recipient, subject):
    logger.info(f"Sending via: {recipient} - subject: {subject}")


class DeadLetterTask(Task):

    def on_failure(self, exc, task_id, args, kwargs, einfo):

        idempotency_key = kwargs.get("idempotency_key") or (args[0] if args else None)
        if not idempotency_key:
            logger.error(f"Task {task_id} failed with no idempotency_key: {exc}")
            return

        try:
            job = EmailJob.objects.get(idempotency_key=idempotency_key)
            job.status = EmailJob.STATUS_FAILED
            job.save(update_fields=["status"])

            DeadLetterJob.objects.update_or_create(
                email_job=job,
                defaults={"reason": str(exc)},
            )
            logger.error(f"Job {idempotency_key} moved to dead-letter after max retries: {exc}")
        except EmailJob.DoesNotExist:
            logger.error(f"Job {idempotency_key} failed but not EmailJob Found: {exc}")

        super().on_failure(exc, task_id, args, kwargs, einfo)

@shared_task(
    bind=True,
    base=DeadLetterTask,
    autoretry_for=(RateLimitExceeded, Exception),
    retry_backoff=True,
    retry_backoff_max= 60,
    max_retries=5,
    retry_jitter=True,
)
def send_email(self, idempotency_key:str , recipient:str , subject:str):
    job, _created = EmailJob.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={"recipient": recipient, "subject": subject},
    )

    if job.status == EmailJob.STATUS_SENT:
        logger.info(f"Skipping the idempotency key: {idempotency_key} -- email already sent")
        return

    job.attempts += 1
    job.save(update_fields=["attempts"])

    if not _limiter.allow():
        raise RateLimitExceeded(f"Rate limit hit for {idempotency_key}")

    send_via_provider(recipient, subject)

    job.status = EmailJob.STATUS_SENT
    job.send_at = timezone.now()
    job.save(update_fields=["status", "send_at"])

