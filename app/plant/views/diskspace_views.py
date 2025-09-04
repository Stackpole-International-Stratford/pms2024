# pms/views.py
import re
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.core.mail import send_mail
from django.conf import settings
from django.utils.html import escape

THRESHOLD = 90  # Only send if disk_used >= THRESHOLD

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
DISK_USED_FROM_MESSAGE = re.compile(r"(?:DiskUsed:\s*)?(\d{1,3})%")

def _parse_disk_used_int(disk_used_str: str | None) -> int | None:
    """
    Accepts '92%', '92', ' 92 % ' etc. Returns int 0..100 or None.
    """
    if not disk_used_str:
        return None
    m = re.search(r"(\d{1,3})", disk_used_str)
    if not m:
        return None
    val = int(m.group(1))
    # Clamp to 0..100 just to be safe
    return max(0, min(val, 100))

@require_GET
def send_health_disk(request):
    """
    Sends an email *only if* disk_used >= THRESHOLD.
    Prefer ?disk_used=92% ; falls back to parsing from legacy 'message' (DiskUsed: 92%).
    """
    recipient = "tyler.careless@johnsonelectric.com"
    raw_message = (request.GET.get("message") or "").strip()
    disk_used_raw = (request.GET.get("disk_used") or "").strip()

    # Extract IP from legacy 'message' if present
    ip_match = IP_REGEX.search(raw_message)
    ip = ip_match.group(0) if ip_match else None

    # Map host if we know the IP
    host_name = emoji = color_hex = None
    if ip and ip in HOST_MAP:
        host_name, emoji, color_hex = HOST_MAP[ip]

    # Derive disk_used %
    disk_used = disk_used_raw
    if not disk_used:
        m = DISK_USED_FROM_MESSAGE.search(raw_message)
        if m:
            disk_used = m.group(1) + "%"  # e.g. "72%"

    disk_used_pct = _parse_disk_used_int(disk_used)

    if disk_used_pct is None:
        return JsonResponse({
            "ok": False,
            "error": "disk_used_missing_or_invalid",
            "hint": "Pass ?disk_used=NN% or include 'DiskUsed: NN%' in message."
        })

    # If below threshold, do NOT send the email—just report back
    if disk_used_pct < THRESHOLD:
        return JsonResponse({
            "ok": True,
            "email_sent": False,
            "suppressed_due_to_threshold": True,
            "threshold": THRESHOLD,
            "disk_used_percent": disk_used_pct,
            "ip_detected": ip,
            "host_mapped": host_name,
        })

    # Build subject (severity + host color emoji if mapped)
    severity_emoji = "🚨"
    if host_name:
        subject = f"{severity_emoji} {emoji} Disk Space Report [{host_name} | {ip}]"
    elif ip:
        subject = f"{severity_emoji} Disk Space Report [{ip}]"
    else:
        subject = f"{severity_emoji} Disk Space Report"

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")

    # Plain text body (clean)
    text_lines = [
        f"Host: {host_name}" if host_name else "Host: Unknown",
        f"IP: {ip}" if ip else "IP: Not detected",
        "",
        f"Disk Space Used: {disk_used_pct}%",
    ]
    text_body = "\n".join(text_lines)

    # HTML body with a colored host badge (if mapped)
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
        {badge_html}<span>Disk Space Report</span>
      </h2>
      <p style="margin:4px 0;"><strong>Host:</strong> {escape(host_name) if host_name else 'Unknown'}</p>
      <p style="margin:4px 0;"><strong>IP:</strong> {escape(ip) if ip else 'Not detected'}</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:12px 0;" />
      <p style="margin:4px 0;"><strong>Disk Space Used:</strong> {disk_used_pct}%</p>
      <p style="margin:4px 0;color:#b91c1c;"><strong>Alert:</strong> Usage at or above {THRESHOLD}%.</p>
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
            "email_sent": bool(sent),
            "sent_to": recipient,
            "subject": subject,
            "ip_detected": ip,
            "host_mapped": host_name,
            "disk_used_percent": disk_used_pct,
            "threshold": THRESHOLD,
        })
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)})



# ##
# curl "http://10.4.1.232:8082/plant/health/disk/?disk_used=$(df -h / | awk 'NR==2 {print $5}')&message=IP:%20$(hostname -I | awk '{print $1}')"
# ##
