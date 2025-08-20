# views.py
from django.shortcuts import render
from plant.models.maintenance_models import *

def heat_toggle_view(request):
    # Query all tracked machines, ordered nicely by line/operation/number
    machines = DowntimeMachine.objects.filter(is_tracked=True).order_by("line", "operation", "machine_number")

    # Group them by line
    grouped_data = {}
    for machine in machines:
        if machine.line not in grouped_data:
            grouped_data[machine.line] = []
        grouped_data[machine.line].append(machine)

    context = {
        "grouped_data": grouped_data
    }
    return render(request, "plant/heat_toggle.html", context)
