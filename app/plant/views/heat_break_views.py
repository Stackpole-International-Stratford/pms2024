# views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings
import MySQLdb
from plant.models.maintenance_models import *
from plant.models.heat_break_models import *


DAVE_HOST = settings.NEW_HOST
DAVE_USER = settings.DAVE_USER
DAVE_PASSWORD = settings.DAVE_PASSWORD
DAVE_DB = settings.DAVE_DB
# ---------- helpers ----------

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

    machines = DowntimeMachine.objects.filter(is_tracked=True)\
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

    # 👇 Call custom logging function
    log_heatbreak_info(hb.id)

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


def log_heatbreak_info(heatbreak_id):
    try:
        hb = HeatBreak.objects.get(pk=heatbreak_id)

        print("📋 HeatBreak info lookup:")
        print("   ID:", hb.id)
        print("   Machine number:", hb.machine_number)   # ✅ use denormalized field
        print("   Started:", epoch_to_iso(hb.start_time_epoch))
        print("   Ended:", epoch_to_iso(hb.end_time_epoch) if hb.end_time_epoch else "Still active")
        print("   Turned on by:", hb.turned_on_by_username)
        print("   Turned off by:", hb.turned_off_by_username)

    except HeatBreak.DoesNotExist:
        print("❌ HeatBreak not found for id:", heatbreak_id)


