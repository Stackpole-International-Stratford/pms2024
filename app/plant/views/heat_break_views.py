# views.py
from django.shortcuts import render
from plant.models.maintenance_models import *
from plant.models.heat_break_models import *
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone

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

    if request.method == "POST":
        duration = request.POST.get("duration")
        print("POST duration raw value:", duration)

        try:
            duration = int(duration)
        except Exception as e:
            print("❌ Error parsing duration:", e)
            return JsonResponse({"status": "error", "msg": "Invalid duration"}, status=400)

        machine = get_object_or_404(DowntimeMachine, pk=machine_id)
        print("✅ Found machine:", machine)

        hb = HeatBreak.objects.create(
            machine=machine,
            duration_minutes=duration,
            start_time=timezone.now(),
            turned_on_by=request.user,
        )
        print("✅ Created HeatBreak:", hb.id, "at", hb.start_time)

        return JsonResponse({
            "status": "ok",
            "heatbreak_id": hb.id,
            "start_time": hb.start_time.isoformat()
        })

    print("❌ turn_on_heat invalid request method:", request.method)
    return JsonResponse({"status": "error", "msg": "Invalid request"}, status=400)


@login_required
def turn_off_heat(request, heatbreak_id):
    print("➡️ turn_off_heat called by:", request.user, "for heatbreak_id:", heatbreak_id)

    if request.method == "POST":
        hb = get_object_or_404(HeatBreak, pk=heatbreak_id, end_time__isnull=True)
        print("✅ Found active HeatBreak:", hb.id, "machine:", hb.machine)

        end_time_str = request.POST.get("end_time")
        print("POST end_time raw value:", end_time_str)

        try:
            end_time = timezone.datetime.fromisoformat(end_time_str)
            print("Parsed end_time:", end_time)
        except Exception as e:
            print("❌ Failed to parse end_time, using now():", e)
            end_time = timezone.now()

        hb.end_time = end_time
        hb.turned_off_by = request.user
        hb.save()
        print("✅ Updated HeatBreak:", hb.id, "end_time:", hb.end_time)

        return JsonResponse({"status": "ok", "end_time": hb.end_time.isoformat()})

    print("❌ turn_off_heat invalid request method:", request.method)
    return JsonResponse({"status": "error", "msg": "Invalid request"}, status=400)