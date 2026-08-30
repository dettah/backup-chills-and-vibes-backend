from django.db import models

class TimeStampedModel(models.Model):
    """
    An abstract base class model that provides automated tracking fields
    for creation and update timestamps across all database tables.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
