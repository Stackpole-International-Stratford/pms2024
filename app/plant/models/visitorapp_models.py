# plant/models.py
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class VisitorLog(models.Model):
    VISITOR_TYPES = [
        ('contractor', 'Contractor'),
        ('corporate', 'Corporate'),
        ('other', 'Other'),
    ]

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    visitor_type = models.CharField(max_length=20, choices=VISITOR_TYPES)
    hosts = models.ManyToManyField(User, related_name='hosted_visits')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email}) @ {self.created_at:%Y-%m-%d %H:%M}"
