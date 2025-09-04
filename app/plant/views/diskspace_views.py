# pms/views.py
from django.http import JsonResponse
from django.views.decorators.http import require_GET

@require_GET
def send_health_disk(request):
    """
    Hitting this URL will print whatever message is passed in the query string.
    Example:
      curl "http://10.4.1.232:8082/plant/email/test/?message=Hello+World"
    """
    recipient = "tyler.careless@johnsonelectric.com"
    message = request.GET.get("message", "No message provided")

    # Print to console
    print("=== Simulated Email ===")
    print(f"To: {recipient}")
    print(message)
    print("=======================")

    return JsonResponse({"ok": True, "printed_to_console": True, "message": message})



# curl "http://10.4.1.232:8082/plant/health/disk/?message=IP:%20$(hostname -I | awk '{print $1}')%20DiskUsed:%20$(df -h / | awk 'NR==2 {print $5}')"

