# pms/views.py
from django.conf import settings
from django.core.mail import send_mail
from django.http import JsonResponse
from django.views.decorators.http import require_GET

@require_GET
def send_test_email(request):
    """
    Hitting this URL will send a test email to Tyler.
    """
    recipient = "tyler.careless@johnsonelectric.com"
    subject = "PMS test email"
    message = "Hi Tyler,\n\nThis is a test email triggered by visiting /email/test/.\n\n–PMS"
    sent = send_mail(
        subject=subject,
        message=message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"),
        recipient_list=[recipient],
        fail_silently=False,
    )
    return JsonResponse({"ok": bool(sent), "sent_to": recipient})
