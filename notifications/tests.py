# notifications/tests.py
from unittest.mock import patch

from django.test import TestCase, override_settings

from .models import EmailJob, DeadLetterJob
from .services import submit_email_job
from . import tasks as tasks_module


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=False)
class RateLimitedQueueTests(TestCase):
    """
    CELERY_TASK_ALWAYS_EAGER runs tasks synchronously in-process instead of
    needing a real worker — standard way to test Celery logic without
    standing up broker + worker infrastructure in CI.
    """

    def setUp(self):
        # Reset the rate limiter's Redis key between tests so runs don't
        # bleed into each other.
        tasks_module._limiter._client.delete(tasks_module._limiter.key)

    def test_500_jobs_none_lost_and_rate_limit_respected(self):
        submitted_keys = []
        for i in range(500):
            key = submit_email_job(
                recipient=f"user{i}@example.com",
                subject="Order Confirmation",
            )
            submitted_keys.append(key)

        # --- Assertion 1: no job lost ---
        # Every submitted job should have a corresponding EmailJob row,
        # regardless of whether it ended up sent or dead-lettered.
        found = EmailJob.objects.filter(idempotency_key__in=submitted_keys).count()
        self.assertEqual(found, 500, "Some jobs have no EmailJob row — a job was lost.")

        # --- Assertion 2: rate limit never exceeded ---
        # Replay the Redis sorted set's timestamps and check no 60s window
        # ever contained more than 200 entries.
        raw_entries = tasks_module._limiter._client.zrange(
            tasks_module._limiter.key, 0, -1, withscores=True
        )
        timestamps = sorted(score for _member, score in raw_entries)
        self.assertTrue(self._no_window_exceeds_limit(timestamps, window=60, limit=200))

    def _no_window_exceeds_limit(self, timestamps, window, limit):
        # Sliding check: for every timestamp, count how many timestamps
        # fall within [t, t+window). None of those counts should exceed limit.
        for i, t in enumerate(timestamps):
            count_in_window = sum(1 for other in timestamps if t <= other < t + window)
            if count_in_window > limit:
                return False
        return True

    def test_transient_failure_is_retried_and_eventually_succeeds(self):
        call_count = {"n": 0}
        original_send = tasks_module.send_via_provider

        def flaky_send(recipient, subject):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ConnectionError("Simulated transient provider failure")
            return original_send(recipient, subject)

        with patch.object(tasks_module, "send_via_provider", side_effect=flaky_send):
            key = submit_email_job(recipient="retry-test@example.com", subject="OTP")

        job = EmailJob.objects.get(idempotency_key=key)
        self.assertEqual(job.status, EmailJob.STATUS_SENT)
        self.assertGreaterEqual(job.attempts, 2, "Job should have been attempted more than once.")
        self.assertGreaterEqual(call_count["n"], 2, "Provider send should have been retried.")

    def test_permanent_failure_lands_in_dead_letter(self):
        with patch.object(
            tasks_module, "send_via_provider", side_effect=Exception("permanent failure")
        ):
            key = submit_email_job(recipient="dead-letter-test@example.com", subject="Alert")

        job = EmailJob.objects.get(idempotency_key=key)
        self.assertEqual(job.status, EmailJob.STATUS_FAILED)
        self.assertTrue(DeadLetterJob.objects.filter(email_job=job).exists())