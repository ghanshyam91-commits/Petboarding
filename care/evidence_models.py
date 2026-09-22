from django.conf import settings
from django.db import models


class HealthEvidence(models.Model):
    """Small, private medical evidence stored durably alongside its health record."""
    record = models.OneToOneField('care.HealthRecord', on_delete=models.PROTECT, related_name='evidence')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    content = models.BinaryField()
    content_type = models.CharField(max_length=40)
    extension = models.CharField(max_length=5)
    sha256 = models.CharField(max_length=64)
    reviewer_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
