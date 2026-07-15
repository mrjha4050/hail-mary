
from django.db import models


class EmailJob(models.Model):

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"  # permanently failed, moved to dead-letter

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    idempotency_key = models.CharField(max_length=255, unique=True)
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    status = models.CharField(choices=STATUS_CHOICES, default=STATUS_PENDING, max_length=10)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    send_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"EmailJob: {self.idempotency_key}, {self.status}"


class DeadLetterJob(models.Model):

    email_job = models.OneToOneField(EmailJob, on_delete=models.CASCADE, related_name="dead_letter_job")
    reason = models.TextField()
    failed_at = models.DateTimeField(auto_now_add=True)
    replayed = models.BooleanField(default=False)
    last_attempt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"DeadLetterJob: {self.email_job.idempotency_key}"