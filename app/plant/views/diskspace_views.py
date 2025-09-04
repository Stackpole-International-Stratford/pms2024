# pms/views.py
import re
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.core.mail import send_mail
from django.conf import settings
from django.utils.html import escape

# IP -> (host_name, color_emoji, hex_color)
HOST_MAP = {
    "10.4.1.232": ("pmdsdata9",  "🟦", "#1E90FF"),
    "10.4.1.224": ("pmdsdata3",  "🟥", "#DC143C"),
    "10.4.1.245": ("pmdsdata6",  "🟩", "#2E8B57"),
    "10.4.1.231": ("pmdsdata8",  "🟨", "#DAA520"),
    "10.4.1.234": ("pmdsdata12", "🟪", "#800080"),
}

IP_REGEX = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# Accept "72%" or "DiskUsed: 72%" from legacy message payloads
DISK_USED_FROM_MESSAGE = re.compile(r"(?:DiskUsed:\s*)?(\d{1,3}%)")

@require_GET
def send_health_disk(request):
    """
    Sends an email with host + IP derived from the message, and a clean line:
    'Disk Space Used: <value>'.
    Prefer ?disk_used=72% ; falls back to parsing from legacy 'message'.
    """
    recipient = "tyler.careless@johnsonelectric.com"
    raw_message = (request.GET.get("message") or "").strip()
    disk_used = (request.GET.get("disk_used") or "").strip()

    # Try to extract IP from either disk_used param (unlikely) or legacy message
    ip_match = IP_REGEX.search(raw_message)
    ip = ip_match.group(0) if ip_match else None

    # Map host if we know the IP
    host_name = emoji = color_hex = None
    if ip and ip in HOST_MAP:
        host_name, emoji, color_hex = HOST_MAP[ip]

    # Extract disk_used if not explicitly provided
    if not disk_used:
        m = DISK_USED_FROM_MESSAGE.search(raw_message)
        if m:
            disk_used = m.group(1)  # e.g. "72%"

    # Build subject
    if host_name:
        subject = f"{emoji} Health Disk Report [{host_name} | {ip}]"
    elif ip:
        subject = f"Health Disk Report [{ip}]"
    else:
        subject = "Health Disk Report"

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")

    # Plain text body (clean)
    text_lines = [
        f"Host: {host_name}" if host_name else "Host: Unknown",
        f"IP: {ip}" if ip else "IP: Not detected",
        "",
        f"Disk Space Used: {disk_used or 'Unknown'}",
    ]
    text_body = "\n".join(text_lines)

    # HTML body (with colored badge for mapped hosts)
    badge_html = ""
    if host_name and color_hex:
        badge_html = (
            f'<span style="display:inline-block;'
            f'padding:4px 8px;margin-right:8px;border-radius:6px;'
            f'background:{color_hex};color:#ffffff;font-weight:600;">{escape(host_name)}</span>'
        )

    html_body = f"""
    <div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;line-height:1.5;">
      <h2 style="margin:0 0 8px 0;">
        {badge_html}<span>Plant Health – Disk Report</span>
      </h2>
      <p style="margin:4px 0;"><strong>Host:</strong> {escape(host_name) if host_name else 'Unknown'}</p>
      <p style="margin:4px 0;"><strong>IP:</strong> {escape(ip) if ip else 'Not detected'}</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:12px 0;" />
      <p style="margin:4px 0;"><strong>Disk Space Used:</strong> {escape(disk_used or 'Unknown')}</p>
    </div>
    """.strip()

    try:
        sent = send_mail(
            subject=subject,
            message=text_body,
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=False,
            html_message=html_body,
        )
        return JsonResponse({
            "ok": bool(sent),
            "sent_to": recipient,
            "subject": subject,
            "ip_detected": ip,
            "host_mapped": host_name,
            "disk_used": disk_used or None,
        })
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)})



# ##
# curl "http://10.4.1.232:8082/plant/health/disk/?disk_used=$(df -h / | awk 'NR==2 {print $5}')&message=IP:%20$(hostname -I | awk '{print $1}')"
# ##
