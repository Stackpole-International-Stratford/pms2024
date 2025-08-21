# views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings
import MySQLdb
from plant.models.maintenance_models import *
from plant.models.heat_break_models import *
import datetime


DAVE_HOST = settings.NEW_HOST
DAVE_USER = settings.DAVE_USER
DAVE_PASSWORD = settings.DAVE_PASSWORD
DAVE_DB = settings.DAVE_DB
# ---------- helpers ----------

def floor_to_hour_epoch(epoch: int) -> int:
    """
    Floor an epoch timestamp to the top of the hour in the current Django timezone,
    then convert back to epoch.
    """
    tz = timezone.get_current_timezone()
    dt = timezone.datetime.fromtimestamp(epoch, tz=tz)
    dt_hour = dt.replace(minute=0, second=0, microsecond=0)
    return int(dt_hour.timestamp())

def hour_range(start_floor_epoch: int, end_epoch: int):
    """
    Yield hour-start epochs [start_floor_epoch, ..., <= end_epoch] stepping by 1 hour.
    """
    cur = start_floor_epoch
    one_hour = 60 * 60
    while cur <= end_epoch:
        yield cur
        cur += one_hour

def now_epoch() -> int:
    return int(timezone.now().timestamp())

def epoch_to_iso(epoch: int | None) -> str | None:
    if epoch is None:
        return None
    # Render in the current Django timezone
    return timezone.datetime.fromtimestamp(epoch, tz=timezone.get_current_timezone()).isoformat()

def parse_to_epoch(value: str | None) -> int:
    """
    Accepts either:
      - epoch (e.g. '1724162400' or '1724162400.123')
      - ISO 8601 (e.g. '2025-08-20T10:21:00' or '2025-08-20 10:21:00+00:00')
    Falls back to now() if it can't parse.
    """
    if not value:
        return now_epoch()

    # 1) try epoch directly
    try:
        return int(float(value))
    except Exception:
        pass

    # 2) try ISO 8601
    try:
        dt = timezone.datetime.fromisoformat(value)
        if dt.tzinfo is None:
            # assume current TZ for naive times
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return int(dt.timestamp())
    except Exception:
        # 3) fallback
        return now_epoch()

# ---------- views ----------

@login_required
def heat_toggle_view(request):
    print("➡️ heat_toggle_view called by:", request.user)

    machines = DowntimeMachine.objects\
        .order_by("line", "operation", "machine_number")
    print(f"Found {machines.count()} tracked machines")

    # Map active heatbreaks by machine_id
    active_qs = HeatBreak.objects.filter(machine__in=machines, end_time_epoch__isnull=True)
    active_by_machine = {
        hb.machine_id: {
            "id": hb.id,
            "duration": hb.duration_minutes,
            "start_time_iso": epoch_to_iso(hb.start_time_epoch),
        }
        for hb in active_qs
    }

    # Group machines by line and attach active hb metadata to each machine
    grouped_data = {}
    for m in machines:
        # attach for easy access in template
        m.active_hb = active_by_machine.get(m.id)  # either dict or None
        grouped_data.setdefault(m.line, []).append(m)

    for line, mlist in grouped_data.items():
        print(f"Line {line}: {len(mlist)} machines")

    context = {
        "grouped_data": grouped_data,
        "durations": [15, 30, 45],
    }
    print("✅ Context prepared for template")
    return render(request, "plant/heat_toggle.html", context)


@login_required
def turn_on_heat(request, machine_id):
    print("➡️ turn_on_heat called by:", request.user, "for machine_id:", machine_id)

    if request.method != "POST":
        print("❌ turn_on_heat invalid request method:", request.method)
        return JsonResponse({"status": "error", "msg": "Invalid request"}, status=400)

    duration_raw = request.POST.get("duration")
    print("POST duration raw value:", duration_raw)
    try:
        duration = int(duration_raw)
    except Exception as e:
        print("❌ Error parsing duration:", e)
        return JsonResponse({"status": "error", "msg": "Invalid duration"}, status=400)

    machine = get_object_or_404(DowntimeMachine, pk=machine_id)
    print("✅ Found machine:", machine)

    start_epoch = now_epoch()
    hb = HeatBreak.objects.create(
        machine=machine,
        machine_number=machine.machine_number,           # ✅ snapshot the machine number
        duration_minutes=duration,
        start_time_epoch=start_epoch,
        turned_on_by_username=request.user.get_username(),  # ✅ username, not FK
    )
    print("✅ Created HeatBreak:", hb.id, "at epoch", hb.start_time_epoch)

    return JsonResponse({
        "status": "ok",
        "heatbreak_id": hb.id,
        "start_time_epoch": hb.start_time_epoch,
        "start_time_iso": epoch_to_iso(hb.start_time_epoch),
    })



@login_required
def turn_off_heat(request, heatbreak_id):
    print("➡️ turn_off_heat called by:", request.user, "for heatbreak_id:", heatbreak_id)

    if request.method != "POST":
        print("❌ turn_off_heat invalid request method:", request.method)
        return JsonResponse({"status": "error", "msg": "Invalid request"}, status=400)

    hb = get_object_or_404(HeatBreak, pk=heatbreak_id, end_time_epoch__isnull=True)
    print("✅ Found active HeatBreak:", hb.id, "machine:", hb.machine)

    end_time_raw = request.POST.get("end_time")
    print("POST end_time raw value:", end_time_raw)

    end_epoch = parse_to_epoch(end_time_raw)
    hb.end_time_epoch = end_epoch
    hb.turned_off_by_username = request.user.get_username()  # ✅ username
    hb.updated_at_epoch = now_epoch()                        # ✅ keep updated_at in sync (unless model auto-updates)
    hb.save()
    print("✅ Updated HeatBreak:", hb.id, "end_time_epoch:", hb.end_time_epoch)

    # 👇 Print the downtime entries we would insert (one per hour slot)
    print_heatbreak_downtime_rows(hb.id)

    return JsonResponse({
        "status": "ok",
        "end_time_epoch": hb.end_time_epoch,
        "end_time_iso": epoch_to_iso(hb.end_time_epoch),
    })









# ======================================================================
# ======================================================================
# ==================== Hook now into downtime app ======================
# ======================================================================
# ======================================================================


def print_heatbreak_downtime_rows(heatbreak_id: int):
    """
    Build and PRINT the MachineDowntimeEvent rows that would be created
    for a given HeatBreak, one row per hour anchored to the top of the hour.

    Example:
      start=16:16, end=19:33, duration=30min
      -> rows at 16:00-16:30, 17:00-17:30, 18:00-18:30, 19:00-19:30
    """
    try:
        hb = HeatBreak.objects.select_related("machine").get(pk=heatbreak_id)
    except HeatBreak.DoesNotExist:
        print("❌ HeatBreak not found for id:", heatbreak_id)
        return

    if hb.end_time_epoch is None:
        print("ℹ️ HeatBreak is still active; cannot build final downtime rows yet.")
        return

    # Pull machine facts
    # Assumes DowntimeMachine has .line and .machine_number (your code uses these elsewhere)
    machine_line = getattr(hb.machine, "line", None)
    machine_number = hb.machine_number  # snapshot saved at creation time

    if machine_line is None:
        # Fallback: if line wasn't available for some reason
        machine_line = "UNKNOWN"

    duration_sec = int(hb.duration_minutes) * 60
    start_floor = floor_to_hour_epoch(hb.start_time_epoch)
    end_epoch = hb.end_time_epoch

    # For readability in logs
    tz = timezone.get_current_timezone()
    start_dt = timezone.datetime.fromtimestamp(hb.start_time_epoch, tz=tz)
    end_dt = timezone.datetime.fromtimestamp(end_epoch, tz=tz)
    start_floor_dt = timezone.datetime.fromtimestamp(start_floor, tz=tz)

    print("📋 HeatBreak summary:")
    print(f"   id={hb.id}  line={machine_line}  machine={machine_number}")
    print(f"   start={start_dt.isoformat()}  (floored to hour {start_floor_dt.isoformat()})")
    print(f"   end={end_dt.isoformat()}")
    print(f"   duration={hb.duration_minutes} minutes")
    print(f"   on_by={hb.turned_on_by_username}  off_by={hb.turned_off_by_username}")

    # Build and print synthetic downtime rows (no DB writes yet)
    print("🧮 Downtime rows to insert (PRINT ONLY):")
    for hour_start in hour_range(start_floor, end_epoch):
        row_start = hour_start
        row_end = hour_start + duration_sec  # per spec: always hour_start + duration

        # Compose required fields
        row = {
            "line": machine_line,
            "machine": str(machine_number),
            "category": "Unplanned",
            "subcategory": "Heat Break",
            "code": "Heat Break",
            "start_epoch": row_start,
            "closeout_epoch": row_end,
            "comment": (
                f"Heat break turned on by {hb.turned_on_by_username} "
                f"and turned off by {hb.turned_off_by_username}"
            ),
            "labour_types": ["NA"],  # model uses a JSON list
            "employee_id": hb.turned_on_by_username,
            # not part of the model fields we print, but useful context:
            "_start_local": timezone.datetime.fromtimestamp(row_start, tz=tz).isoformat(),
            "_end_local": timezone.datetime.fromtimestamp(row_end, tz=tz).isoformat(),
        }

        # Pretty print a compact line first…
        print(
            f"   • {row['_start_local']} → {row['_end_local']}  "
            f"[line={row['line']} machine={row['machine']} category={row['category']} "
            f"sub={row['subcategory']} code={row['code']} employee_id={row['employee_id']}]"
        )
        # …then print a dict (exact values you’d insert)
        print("     ROW:", {
            k: v for k, v in row.items()
            if not k.startswith("_")  # exclude the human-time helpers
        })

