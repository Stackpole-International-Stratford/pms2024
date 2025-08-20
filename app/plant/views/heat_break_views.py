# views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from plant.models.maintenance_models import *
from plant.models.heat_break_models import *

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

    machines = DowntimeMachine.objects.filter(is_tracked=True).order_by("line", "operation", "machine_number")
    print(f"Found {machines.count()} tracked machines")

    grouped_data = {}
    for machine in machines:
        if machine.line not in grouped_data:
            grouped_data[machine.line] = []
        grouped_data[machine.line].append(machine)

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
        duration_minutes=duration,
        start_time_epoch=start_epoch,
        turned_on_by=request.user,
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

    # Only active heatbreaks (no end_time yet)
    hb = get_object_or_404(HeatBreak, pk=heatbreak_id, end_time_epoch__isnull=True)
    print("✅ Found active HeatBreak:", hb.id, "machine:", hb.machine)

    end_time_raw = request.POST.get("end_time")
    print("POST end_time raw value:", end_time_raw)

    end_epoch = parse_to_epoch(end_time_raw)
    hb.end_time_epoch = end_epoch
    hb.turned_off_by = request.user
    hb.save()
    print("✅ Updated HeatBreak:", hb.id, "end_time_epoch:", hb.end_time_epoch)

    return JsonResponse({
        "status": "ok",
        "end_time_epoch": hb.end_time_epoch,
        "end_time_iso": epoch_to_iso(hb.end_time_epoch),
    })
