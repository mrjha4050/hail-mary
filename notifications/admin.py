from django.contrib import admin

from .models import EmailJob, DeadLetterJob


@admin.register(EmailJob)
class EmailJobAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'subject', 'status', 'idempotency_key', 'attempts')
    list_filter = ('status',)
    search_fields = ('recipient', 'idempotency_key')

@admin.register(DeadLetterJob)
class DeadLetterJobAdmin(admin.ModelAdmin):
    list_display = ('email_job', 'reason')
    search_fields = ('reason',)

# Register your models here.
