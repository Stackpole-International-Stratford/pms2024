from django.shortcuts import render
from ..forms.cycle_crud_forms import AssetCycleTimeForm
from ..models.setupfor_models import AssetCycleTimes, Asset, Part
import time
from datetime import datetime
import pytz  # For timezone conversion if needed
import json
from django.http import JsonResponse

def asset_cycle_times_page(request):
    if request.method == 'POST':
        form = AssetCycleTimeForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            epoch_timestamp = int(data['datetime'].timestamp())  # Convert datetime to epoch

            # Save to AssetCycleTimes model
            AssetCycleTimes.objects.create(
                asset=data['asset'],
                part=data['part'],
                cycle_time=float(data['cycle_time']),
                effective_date=epoch_timestamp
            )
            print("Entry saved successfully!")
    else:
        form = AssetCycleTimeForm()

    # Fetch past entries and convert effective_date from epoch to datetime
    past_entries = AssetCycleTimes.objects.all().order_by('-created_at')[:500]
    for entry in past_entries:
        entry.effective_date_display = datetime.fromtimestamp(entry.effective_date, pytz.utc).strftime("%Y-%m-%d %H:%M")

    # Fetch possible assets and parts
    assets = Asset.objects.all()
    parts = Part.objects.all()

    return render(
        request,
        'asset_cycle_times.html',
        {
            'form': form,
            'past_entries': past_entries,
            'assets': assets,
            'parts': parts,
        }
    )




def update_asset_cycle_times_page(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            entry_id = data.get("entry_id")
            asset_id = data.get("asset")
            part_id = data.get("part")
            cycle_time = data.get("cycle_time")
            effective_date_str = data.get("effective_date")

            # Convert effective date to epoch timestamp
            effective_date_obj = datetime.strptime(effective_date_str, "%Y-%m-%dT%H:%M")
            effective_date_epoch = int(effective_date_obj.timestamp())  # Convert to epoch (seconds)

            # Retrieve the existing record
            try:
                entry = AssetCycleTimes.objects.get(id=entry_id)
                
                # Update the fields
                entry.asset_id = asset_id
                entry.part_id = part_id
                entry.cycle_time = float(cycle_time)
                entry.effective_date = effective_date_epoch
                entry.save()  # Save changes to the database
                
                print(f"Updated Entry ID: {entry_id}")
                return JsonResponse({"message": "Entry updated successfully!", "epoch_timestamp": effective_date_epoch}, status=200)
            except AssetCycleTimes.DoesNotExist:
                return JsonResponse({"error": "Entry not found"}, status=404)

        except Exception as e:
            print(f"Error: {e}")
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "Invalid request method"}, status=405)



