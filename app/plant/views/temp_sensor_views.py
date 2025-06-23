import mysql.connector
import pytz
from datetime import datetime
from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import render
from django.core.mail import EmailMultiAlternatives
from django.utils.html import format_html
from django.contrib.auth.models import Group
import json
from django.http           import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from ..models.tempsensor_models import TempSensorEmailList
import time
from django.db.models import Max






# =========================================================================
# =========================================================================
# ======================= Helper Functions ================================
# =========================================================================
# =========================================================================


# zones located by furnaces need a +1 humidex adjustment
FURNACE_ZONES = [1, 2, 5, 6, 18, 19, 20, 21, 24]  




def humanize_delta(delta):
    total_secs = int(delta.total_seconds())
    mins = total_secs // 60
    hrs = total_secs // 3600
    days = delta.days

    if mins < 60:
        return f"{mins} mins"
    if hrs < 24:
        return f"{hrs} hrs {mins % 60} mins"
    if days < 7:
        return f"{days} days {mins % 60} mins"
    if days < 30:
        weeks = days // 7
        return f"{weeks} weeks"
    return f"{days // 30} months"





def send_alert_email(zones):
    """
    Send a multipart email (plain text + HTML) listing every zone
    whose humidex ≥ 43, with clear heat-break recommendations.
    Throttles to once every 29 minutes by checking and pre-logging email_sent.
    """
    # 1) Collect only zones needing alerts
    alerts = []
    for entry in zones:
        hx = entry["humidex"]
        if hx < 43.0:
            continue

        if hx < 45.0:
            rec = "15-minute heat break"
        elif hx < 47.0:
            rec = "30-minute heat break"
        elif hx < 50.0:
            rec = "45-minute heat break"
        else:
            rec = "<strong style='color:#c00;'>HAZARDOUS to continue physical activity!</strong>"

        alerts.append({
            "zone":    entry["zone"],
            "humidex": f"{hx:.1f}",
            "rec":     rec,
        })

    if not alerts:
        return  # nothing to report

    # 2) Throttle: only once every 29 minutes
    now_ts = int(time.time())
    last_sent = (
        TempSensorEmailList.objects
        .aggregate(latest=Max("email_sent"))["latest"]
        or 0
    )
    if now_ts - last_sent < 29 * 60:
        return

    # 3) Gather recipient list (and bail if empty)
    recipient_qs   = TempSensorEmailList.objects.all()
    recipient_list = list(recipient_qs.values_list("email", flat=True))
    if not recipient_list:
        return

    # 4) Pre-log the send so concurrent calls see the update immediately
    recipient_qs.update(email_sent=now_ts)

    # 5) Build subject + plain-text body
    subject = "🔴 Heat Alert Notification: Humidex Safety Advisory"

    text_lines = [
        "The following zones have recorded a humidex of 43 or higher:",
        ""
    ]
    for a in alerts:
        rec_text = a["rec"].replace("<strong>", "").replace("</strong>", "")
        text_lines.append(f"- Zone {a['zone']}: humidex = {a['humidex']} → {rec_text}")
    text_body = "\n".join(text_lines)

    # 6) Build HTML body
    html_rows = "".join([
        format_html(
            "<tr>"
            "  <td style='padding:8px;border:1px solid #ddd;'>Zone {zone}</td>"
            "  <td style='padding:8px;border:1px solid #ddd;text-align:center;'>{humidex}</td>"
            "  <td style='padding:8px;border:1px solid #ddd;'>{rec}</td>"
            "</tr>",
            zone=a["zone"], humidex=a["humidex"], rec=format_html(a["rec"])
        )
        for a in alerts
    ])
    html_body = format_html(
        """
        <html>
         <body style="font-family:Arial,sans-serif;color:#333;">
          <h2 style="color:#c00;">Heat Alert: Humidex Threshold Exceeded</h2>
          <p>The following zones have recorded a <strong>humidex ≥ 43</strong>. 
             Please observe the recommended heat-breaks below:</p>
          <table style="border-collapse:collapse;width:100%;max-width:600px;">
           <thead>
            <tr style="background:#f5f5f5;">
             <th style="padding:8px;border:1px solid #ddd;text-align:left;">Zone</th>
             <th style="padding:8px;border:1px solid #ddd;text-align:center;">Humidex</th>
             <th style="padding:8px;border:1px solid #ddd;text-align:left;">Recommendation</th>
            </tr>
           </thead>
           <tbody>
             {rows}
           </tbody>
          </table>
          <p style="font-size:0.9em;color:#666;">Stay safe!</p>
         </body>
        </html>
        """,
        rows=format_html(html_rows)
    )

    # 7) Assemble and send the email
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipient_list,
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)




def is_healthsafety_manager(user):
    return (
        user.is_authenticated
        and user.groups.filter(name="healthsafety_managers").exists()
    )



@require_POST
def add_temp_sensor_email(request):
    if not is_healthsafety_manager(request.user):
        return HttpResponseForbidden()
    email = request.POST.get("email", "").strip()
    if not email:
        return JsonResponse({"error": "No email provided."}, status=400)
    obj, created = TempSensorEmailList.objects.get_or_create(email=email)
    if not created:
        return JsonResponse({"error": "That address is already on the list."}, status=400)
    return JsonResponse({"id": obj.id, "email": obj.email})

@require_POST
def delete_temp_sensor_email(request):
    if not is_healthsafety_manager(request.user):
        return HttpResponseForbidden()
    pk = request.POST.get("id")
    if not pk:
        return JsonResponse({"error": "No id provided."}, status=400)
    try:
        obj = TempSensorEmailList.objects.get(pk=pk)
        obj.delete()
        return JsonResponse({"deleted": pk})
    except TempSensorEmailList.DoesNotExist:
        return JsonResponse({"error": "Email not found."}, status=404)
    





# =========================================================================
# =========================================================================
# ======================= Main Functions ==================================
# =========================================================================
# =========================================================================

def temp_display(request):
    raw_rows = []
    try:
        conn = mysql.connector.connect(
            host=settings.DAVE_HOST,
            user=settings.DAVE_USER,
            password=settings.DAVE_PASSWORD,
            database=settings.DAVE_DB,
        )
        cursor = conn.cursor()
        cursor.execute(
            "SELECT temp, humidity, humidex, zone, timestamp FROM temp_monitors"
        )
        raw_rows = cursor.fetchall()
    except mysql.connector.Error as e:
        print("MySQL error:", e)
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn.is_connected():
            conn.close()

    now_utc = datetime.now(pytz.utc)
    processed = []
    for temp_raw, hum_raw, hex_raw, zone, ts_raw in raw_rows:
        temp     = temp_raw   / 10.0
        humidity = hum_raw    / 10.0
        # base humidex
        humidex = hex_raw / 10.0

        # adjust for furnace zones
        if zone in FURNACE_ZONES:
            humidex += 1.0

        if ts_raw is None:
            updated = "n/a"
        else:
            if isinstance(ts_raw, (int, float)):
                ts_aware = datetime.fromtimestamp(ts_raw, tz=pytz.utc)
            else:
                ts_aware = ts_raw if ts_raw.tzinfo else pytz.utc.localize(ts_raw)
            updated = humanize_delta(now_utc - ts_aware)

        processed.append({
            "temp":     temp,
            "humidity": humidity,
            "humidex":  humidex,
            "zone":     zone,
            "updated":  updated,
            "alert":    humidex >= 43.0,
        })

    processed.sort(key=lambda x: x["humidex"], reverse=True)
    send_alert_email(processed)

    half    = (len(processed) + 1) // 2
    columns = [processed[:half], processed[half:]]

    # <-- new bit, works for anonymous or logged-in users
    is_manager = is_healthsafety_manager(request.user)

     # load the current list only for managers
    email_list = TempSensorEmailList.objects.all() if is_manager else []

    return render(request, "plant/temp_display.html", {
        "columns":    columns,
        "is_manager": is_manager,
        "email_list": email_list,
    })




# =========================================================================
# =========================================================================
# ======================= Heat Break ======================================
# =========================================================================
# =========================================================================



def heat_break(request):
    # Renders plant/heatbreak.html
    return render(request, 'plant/heatbreak.html')
