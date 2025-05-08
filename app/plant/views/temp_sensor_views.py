import mysql.connector
import pytz
from datetime import datetime
from django.conf import settings
from django.shortcuts import render

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

def alert_zones(zones):
    """
    Print out any zones with humidex >= 43,
    along with the recommended heat-break duration.
    """
    for entry in zones:
        hx = entry["humidex"]
        zone = entry["zone"]

        if hx < 43.0:
            continue

        # Determine recommendation
        if hx < 45.0:
            recommendation = "15 minute heat break"
        elif hx < 47.0:
            recommendation = "30 minute heat break"
        elif hx < 50.0:
            recommendation = "45 minute heat break"
        else:
            # 50 or above is hazardous
            print(f"🚨 Zone {zone}: humidex = {hx:.1f} → HAZARDOUS to continue physical activity!")
            continue

        print(f"⚠️ Zone {zone}: humidex = {hx:.1f} → {recommendation}")

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

        # Format the timestamp
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

    # Sort by humidex in descending order
    processed.sort(key=lambda x: x["humidex"], reverse=True)

    # Call the alert function to print any zones in the danger range
    alert_zones(processed)

    # Split into two balanced columns for the template
    half = (len(processed) + 1) // 2
    columns = [processed[:half], processed[half:]]

    return render(request, "plant/temp_display.html", {
        "columns": columns,
    })
