# pms/views.py
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.core.mail import send_mail
from django.conf import settings

@require_GET
def send_health_disk(request):
    """
    Hitting this URL will send the message in the query string as an email.
    Example:
      curl "http://10.4.1.232:8082/plant/health/disk/?message=Hello+World"
    """
    recipient = "tyler.careless@johnsonelectric.com"
    message = request.GET.get("message", "No message provided")

    subject = "Plant Health – Disk Report"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")

    try:
        sent = send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=False,
        )
        return JsonResponse({"ok": bool(sent), "sent_to": recipient, "message": message})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)})




# curl "http://10.4.1.232:8082/plant/health/disk/?message=IP:%20$(hostname -I | awk '{print $1}')%20DiskUsed:%20$(df -h / | awk 'NR==2 {print $5}')"
