import mysql.connector
import pytz
from datetime import datetime
from django.conf import settings
from django.core.mail import send_mail
from django.core.mail import EmailMultiAlternatives
from django.utils.html import format_html
from django.contrib.auth.models import Group
import json
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from ..models.tempsensor_models import *
import time
from django.db.models import Max
from django.utils import timezone
import pytz
import MySQLdb
from django.shortcuts import render, redirect
from django.urls import reverse




# =========================================================================
# =========================================================================
# ======================= Helper Functions ================================
# =========================================================================
# =========================================================================


def get_db_connection():
    return MySQLdb.connect(
        host=settings.DAVE_HOST,
        user=settings.DAVE_USER,
        passwd=settings.DAVE_PASSWORD,
        db=settings.DAVE_DB
    )

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
    Production-ready:
    - Throttles to once every 29 minutes by inspecting email_sent.
    - Sends to every address in TempSensorEmailList.
    - Logs each alert in SentHeatBreakEntry (with sent_on_break_epoch & supervisor_id left null).
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
    text_lines = ["The following zones have recorded a humidex of 43 or higher:", ""]
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
           <tbody>{rows}</tbody>
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

    # 8) Log each alert in our new table
    entries = [
        SentHeatBreakEntry(
            zone           = int(a["zone"]),
            humidex        = float(a["humidex"]),
            recommendation = a["rec"],
        )
        for a in alerts
    ]
    SentHeatBreakEntry.objects.bulk_create(entries)



def is_healthsafety_manager(user):
    return (
        user.is_authenticated
        and user.groups.filter(name="healthsafety_managers").exists()
    )

def is_supervisor(user):
    """
    Allow access if the user is in either
    the maintenance_supervisors or maintenance_managers group.
    """
    if not user.is_authenticated:
        return False

    return user.groups.filter(
        name__in=["maintenance_supervisors", "maintenance_managers"]
    ).exists()



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
# ================== Heat Break Acknowledgement ===========================
# =========================================================================
# =========================================================================



def heat_break(request):
    # only managers may access
    if not is_supervisor(request.user):
        return HttpResponseForbidden()

    # show only the entries that still need to be marked “sent”
    entries = SentHeatBreakEntry.objects.filter(
        sent_on_break_epoch__isnull=True,
        supervisor_id       =None
    ).order_by('created_at')

    return render(request, 'plant/heatbreak.html', {
        'entries': entries,
    })


@require_POST
def mark_heat_break(request):
    # 0) Check permissions
    if not is_supervisor(request.user):
        print("[mark_heat_break] Forbidden: user not supervisor:", request.user)
        return HttpResponseForbidden()

    # 1) Log incoming POST data
    print("[mark_heat_break] POST data:", dict(request.POST))

    entry_id      = request.POST.get('entry_id')
    sent_on_break = request.POST.get('sent_on_break')   # expected like "2025-06-25T13:45"
    supervisor_id = request.POST.get('supervisor_id')

    print(f"[mark_heat_break] raw values -> entry_id={entry_id}, sent_on_break={sent_on_break}, supervisor_id={supervisor_id}")

    # 2) Parse the datetime-local
    try:
        dt_naive = datetime.strptime(sent_on_break, '%Y-%m-%dT%H:%M')
        print("[mark_heat_break] parsed dt_naive:", dt_naive)
    except Exception as e:
        print("[mark_heat_break] ERROR parsing sent_on_break:", e)
        return redirect(reverse('heat_break'))

    # 3) Make it timezone-aware and to epoch
    try:
        local_tz = timezone.get_current_timezone()
        dt_aware = timezone.make_aware(dt_naive, local_tz)
        epoch    = int(dt_aware.timestamp())
        print("[mark_heat_break] dt_aware:", dt_aware, "epoch:", epoch)
    except Exception as e:
        print("[mark_heat_break] ERROR localizing or epoching:", e)
        return redirect(reverse('heat_break'))

    # 4) Fetch & save the model
    try:
        entry = SentHeatBreakEntry.objects.get(pk=entry_id)
        print("[mark_heat_break] fetched entry before change:", entry, 
              "sent_on_break_epoch=", entry.sent_on_break_epoch,
              "supervisor_id=", entry.supervisor_id)

        entry.sent_on_break_epoch = epoch
        entry.supervisor_id       = int(supervisor_id)
        print("[mark_heat_break] about to save entry with sent_on_break_epoch=", 
              entry.sent_on_break_epoch, "supervisor_id=", entry.supervisor_id)

        entry.save()

        # re-fetch to verify
        saved = SentHeatBreakEntry.objects.get(pk=entry_id)
        print("[mark_heat_break] after save, entry:", saved, 
              "sent_on_break_epoch=", saved.sent_on_break_epoch,
              "supervisor_id=", saved.supervisor_id)
    except SentHeatBreakEntry.DoesNotExist:
        print("[mark_heat_break] ENTRY NOT FOUND for id:", entry_id)
    except ValueError as e:
        print("[mark_heat_break] VALUE ERROR converting supervisor_id:", e)
    except Exception as e:
        print("[mark_heat_break] UNEXPECTED ERROR:", e)

    return redirect(reverse('heat_break'))



# # Test Emailer 
# def send_alert_email(zones):
#     """
#     Test-only:
#     - No throttle: sends every call.
#     - Sends exclusively to tyler.careless@johnsonelectric.com.
#     - Still logs into SentHeatBreakEntry for you to inspect.
#     """
#     # 1) Collect only zones needing alerts
#     alerts = []
#     for entry in zones:
#         hx = entry["humidex"]
#         if hx < 43.0:
#             continue
#         if hx < 45.0:
#             rec = "15-minute heat break"
#         elif hx < 47.0:
#             rec = "30-minute heat break"
#         elif hx < 50.0:
#             rec = "45-minute heat break"
#         else:
#             rec = "<strong style='color:#c00;'>HAZARDOUS to continue physical activity!</strong>"
#         alerts.append({
#             "zone":    entry["zone"],
#             "humidex": f"{hx:.1f}",
#             "rec":     rec,
#         })
#     if not alerts:
#         return

#     # —no throttle here—

#     # 2) Force recipient to yourself only
#     recipient_qs   = TempSensorEmailList.objects.filter(
#         email="tyler.careless@johnsonelectric.com"
#     )
#     recipient_list = list(recipient_qs.values_list("email", flat=True))
#     if not recipient_list:
#         return

#     # (we do NOT update email_sent in test mode)

#     # 3) Build subject + plain-text body
#     subject = "[TEST] 🔴 Heat Alert Notification"
#     text_lines = ["(test) The following zones have humidex ≥ 43:", ""]
#     for a in alerts:
#         rec_text = a["rec"].replace("<strong>", "").replace("</strong>", "")
#         text_lines.append(f"- Zone {a['zone']}: {a['humidex']} → {rec_text}")
#     text_body = "\n".join(text_lines)

#     # 4) Build HTML body (same as prod)
#     html_rows = "".join([
#         format_html(
#             "<tr>"
#             "  <td style='padding:8px;border:1px solid #ddd;'>Zone {zone}</td>"
#             "  <td style='padding:8px;border:1px solid #ddd;text-align:center;'>{humidex}</td>"
#             "  <td style='padding:8px;border:1px solid #ddd;'>{rec}</td>"
#             "</tr>",
#             zone=a["zone"], humidex=a["humidex"], rec=format_html(a["rec"])
#         )
#         for a in alerts
#     ])
#     html_body = format_html(
#         """
#         <html>
#          <body style="font-family:Arial,sans-serif;color:#333;">
#           <h2 style="color:#c00;">[TEST] Heat Alert</h2>
#           <table style="border-collapse:collapse;width:100%;max-width:600px;">
#            <thead>
#             <tr style="background:#f5f5f5;">
#              <th style="padding:8px;border:1px solid #ddd;">Zone</th>
#              <th style="padding:8px;border:1px solid #ddd;text-align:center;">Humidex</th>
#              <th style="padding:8px;border:1px solid #ddd;">Recommendation</th>
#             </tr>
#            </thead>
#            <tbody>{rows}</tbody>
#           </table>
#          </body>
#         </html>
#         """,
#         rows=format_html(html_rows)
#     )

#     # 5) Send
#     msg = EmailMultiAlternatives(
#         subject=subject,
#         body=text_body,
#         from_email=settings.DEFAULT_FROM_EMAIL,
#         to=recipient_list,
#     )
#     msg.attach_alternative(html_body, "text/html")
#     msg.send(fail_silently=False)

#     # 6) Still log entries so you can review them
#     entries = [
#         SentHeatBreakEntry(
#             zone           = int(a["zone"]),
#             humidex        = float(a["humidex"]),
#             recommendation = a["rec"],
#         )
#         for a in alerts
#     ]
#     SentHeatBreakEntry.objects.bulk_create(entries)
