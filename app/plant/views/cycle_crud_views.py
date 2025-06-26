from django.shortcuts import render
from ..forms.cycle_crud_forms import AssetCycleTimeForm
from ..models.setupfor_models import AssetCycleTimes, Asset, Part
import time
from datetime import datetime
import pytz  # For timezone conversion if needed
import json
from django.http import JsonResponse

def asset_cycle_times_page(request):
    """
    Handle display and submission of asset cycle time entries.

    This view supports both GET and POST requests:
    - GET: Render the asset cycle times page with an empty form,
      a list of existing entries (up to 500 most recent), and
      available assets and parts for selection.
    - POST: Validate submitted data via AssetCycleTimeForm. If valid,
      convert the provided datetime to an epoch timestamp, save a new
      AssetCycleTimes record (with asset, part, cycle_time, and
      effective_date), and then re-render the page including the new entry.

    For display purposes, each retrieved entry’s `effective_date`
    (stored as an integer epoch) is converted back into a human-readable
    UTC-based datetime string (`YYYY-MM-DD HH:MM`).

    Parameters
    ----------
    request : django.http.HttpRequest
        The HTTP request object. On POST it should contain form data
        for asset, part, cycle_time, and datetime fields; on GET it
        simply indicates a page load.

    Returns
    -------
    django.http.HttpResponse
        The rendered 'asset_cycle_times.html' template populated with:
        - form: An instance of AssetCycleTimeForm (empty or bound with POST data)
        - past_entries: A list of the 500 most recent AssetCycleTimes
                        records, each with `effective_date_display` added
        - assets: All Asset instances for selection
        - parts: All Part instances for selection
    """
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
    """
    Handle AJAX updates to existing asset cycle time records.

    This view only accepts POST requests containing a JSON payload with:
      - entry_id (int):   The primary key of the AssetCycleTimes record to update.
      - asset (int):      The ID of the Asset to associate.
      - part (int):       The ID of the Part to associate.
      - cycle_time (str|float): The new cycle time value.
      - effective_date (str):   The new effective datetime as ISO string "YYYY-MM-DDTHH:MM".

    On successful update, the record’s `effective_date` (sent as ISO string) is parsed,
    converted to an epoch timestamp (seconds since Unix epoch), and stored. The view
    returns a JSON response with a success message and the computed epoch timestamp.

    Error handling:
      - If the record does not exist, returns HTTP 404 with `{"error": "Entry not found"}`.
      - If the request payload is malformed or any other error occurs, returns HTTP 400
        with `{"error": <error message>}`.
      - If invoked with any method other than POST, returns HTTP 405
        with `{"error": "Invalid request method"}`.

    Parameters
    ----------
    request : django.http.HttpRequest
        The HTTP request object, expected to carry a JSON body on POST.

    Returns
    -------
    django.http.JsonResponse
        A JSON response indicating success (HTTP 200) or an error (HTTP 4xx).
    """
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



