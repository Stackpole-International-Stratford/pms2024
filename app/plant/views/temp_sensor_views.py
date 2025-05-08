import mysql.connector
import pytz
from datetime import datetime
from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import render
from django.core.mail import EmailMultiAlternatives
from django.utils.html import format_html

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
    whose humidex ≥ 43, with a clean table and clear recommendations.
    """
    # Build a list of alert entries
    alerts = []
    for entry in zones:
        hx = entry["humidex"]
        if hx < 43.0:
            continue

        zone = entry["zone"]
        if hx < 45.0:
            rec = "15-minute heat break"
        elif hx < 47.0:
            rec = "30-minute heat break"
        elif hx < 50.0:
            rec = "45-minute heat break"
        else:
            rec = "<strong style='color:#c00;'>HAZARDOUS to continue physical activity!</strong>"

        alerts.append({
            "zone": zone,
            "humidex": f"{hx:.1f}",
            "rec": rec,
        })

    if not alerts:
        return  # nothing to report

    subject = "🔴 Heat Alert Notification: Humidex Safety Advisory"

    # Plain-text fallback
    text_lines = [
        "The following zones have recorded a humidex of 43 or higher:",
        ""
    ]
    for a in alerts:
        # strip HTML tags from rec for text version
        rec_text = a["rec"].replace("<strong>", "").replace("</strong>", "")
        text_lines.append(f"- Zone {a['zone']}: humidex = {a['humidex']} → {rec_text}")
    text_body = "\n".join(text_lines)

    # HTML body with inline styles
    html_rows = "".join([
        format_html(
            "<tr>"
            "  <td style='padding:8px; border:1px solid #ddd;'>Zone {zone}</td>"
            "  <td style='padding:8px; border:1px solid #ddd; text-align:center;'>{humidex}</td>"
            "  <td style='padding:8px; border:1px solid #ddd;'>{rec}</td>"
            "</tr>",
            zone=a["zone"], humidex=a["humidex"], rec=format_html(a["rec"])
        )
        for a in alerts
    ])
    html_body = format_html(
        """
        <html>
         <body style="font-family:Arial,sans-serif; color:#333;">
          <h2 style="color:#c00;">Heat Alert: Humidex Threshold Exceeded</h2>
          <p>The following zones have recorded a <strong>humidex ≥ 43</strong>. 
             Please observe the recommended heat‐breaks below:</p>
          <table style="border-collapse:collapse; width:100%; max-width:600px;">
           <thead>
            <tr style="background:#f5f5f5;">
             <th style="padding:8px; border:1px solid #ddd; text-align:left;">Zone</th>
             <th style="padding:8px; border:1px solid #ddd; text-align:center;">Humidex</th>
             <th style="padding:8px; border:1px solid #ddd; text-align:left;">Recommendation</th>
            </tr>
           </thead>
           <tbody>
             {rows}
           </tbody>
          </table>
          <p style="font-size:0.9em; color:#666;">Sent by Johnson Electric ‐ Stay safe!</p>
         </body>
        </html>
        """,
        rows=format_html(html_rows)
    )

    # Assemble and send
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=["tyler.careless@johnsonelectric.com"],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)

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
        temp = temp_raw / 10.0
        humidity = hum_raw / 10.0
        humidex = hex_raw / 10.0

        if ts_raw is None:
            updated = "n/a"
        else:
            if isinstance(ts_raw, (int, float)):
                ts_aware = datetime.fromtimestamp(ts_raw, tz=pytz.utc)
            else:
                ts_aware = ts_raw if ts_raw.tzinfo else pytz.utc.localize(ts_raw)
            updated = humanize_delta(now_utc - ts_aware)

        processed.append({
            "temp": temp,
            "humidity": humidity,
            "humidex": humidex,
            "zone": zone,
            "updated": updated,
            "alert": humidex >= 43.0,
        })

    # Sort by humidex descending
    processed.sort(key=lambda x: x["humidex"], reverse=True)

    # Send your email alert if any zones ≥ 43
    send_alert_email(processed)

    # Then split into two columns for display
    half = (len(processed) + 1) // 2
    columns = [processed[:half], processed[half:]]

    return render(request, "plant/temp_display.html", {
        "columns": columns,
    })
