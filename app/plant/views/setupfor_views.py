# setupfor/views.py
import json
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from ..models.setupfor_models import SetupFor, Asset, Part
from ..forms.setupfor_forms import AssetForm, PartForm
from django.utils import timezone
import re
from django.core.paginator import Paginator, EmptyPage
from django.db import models
from django.urls import reverse
from datetime import timedelta
from datetime import datetime
import pytz
from django.views.decorators.http import require_POST
from django.utils.dateparse import parse_datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render




def index(request):
    context = {
        "can_view_temp": (
            request.user.is_authenticated
            and request.user.groups.filter(
                name__in=["maintenance_supervisors", "maintenance_managers"]
            ).exists()
        )
    }
    return render(request, 'setupfor/index.html', context)

def natural_sort_key(s):
    # Split the string into numeric and non-numeric parts
    parts = re.split(r'(\d+)', s)
    # Convert numeric parts to integers
    return [int(part) if part.isdigit() else part for part in parts]


@login_required(login_url="login")
def display_assets(request):
    # Get the search query
    search_query = request.GET.get('q', '')

    # Filter assets based on the search query, allowing search by asset_number or asset_name
    assets = Asset.objects.filter(
        models.Q(asset_number__icontains=search_query) | models.Q(asset_name__icontains=search_query)
    )
    assets = list(assets)
    assets.sort(key=lambda a: natural_sort_key(a.asset_number))

    # Handle pagination
    items_per_page = request.GET.get('show', '10')  # Default to 10 items per page
    try:
        items_per_page = int(items_per_page)
    except ValueError:
        items_per_page = 10  # Fallback to 10 if conversion fails

    paginator = Paginator(assets, items_per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'setupfor/display_assets.html', {'page_obj': page_obj, 'search_query': search_query})

def create_asset(request):
    # Check if the user is coming from the password_create page
    from_password_create = request.GET.get('from_password_create', 'false') == 'true'

    if request.method == 'POST':
        form = AssetForm(request.POST)
        if form.is_valid():
            asset = form.save()
            if from_password_create:
                # Redirect back to the password_create page if coming from there
                return redirect(reverse('password_create'))
            return redirect('display_assets')
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors,
                })
    else:
        form = AssetForm()

    return render(request, 'setupfor/asset_form.html', {'form': form, 'title': 'Add New Asset'})


def edit_asset(request, id):
    # Get the Asset object by id or return 404 if not found
    asset = get_object_or_404(Asset, id=id)
    if request.method == 'POST':
        form = AssetForm(request.POST, instance=asset)
        if form.is_valid():
            form.save()
            return redirect('display_assets')
    else:
        form = AssetForm(instance=asset)
    return render(request, 'setupfor/asset_form.html', {'form': form, 'title': 'Edit Asset'})

def delete_asset(request, id):
    # Get the Asset object by id or return 404 if not found
    asset = get_object_or_404(Asset, id=id)
    if request.method == 'POST':
        asset.delete()
        return redirect('display_assets')
    return render(request, 'setupfor/delete_asset.html', {'asset': asset})


@login_required(login_url="login")
def display_parts(request):
    # Get the search query
    search_query = request.GET.get('q', '')

    # Filter parts based on the search query, allowing search by part_number or part_name
    parts = Part.objects.filter(
        models.Q(part_number__icontains=search_query) | models.Q(part_name__icontains=search_query)
    )
    parts = list(parts)
    parts.sort(key=lambda p: natural_sort_key(p.part_number))

    # Handle pagination
    items_per_page = request.GET.get('show', '10')  # Default to 10 items per page
    try:
        items_per_page = int(items_per_page)
    except ValueError:
        items_per_page = 10  # Fallback to 10 if conversion fails

    paginator = Paginator(parts, items_per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'setupfor/display_parts.html', {'page_obj': page_obj, 'search_query': search_query})

def create_part(request):
    if request.method == 'POST':
        form = PartForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('display_parts')
    else:
        form = PartForm()
    return render(request, 'setupfor/part_form.html', {'form': form, 'title': 'Add New Part'})

def edit_part(request, id):
    # Get the Part object by id or return 404 if not found
    part = get_object_or_404(Part, id=id)
    if request.method == 'POST':
        form = PartForm(request.POST, instance=part)
        if form.is_valid():
            form.save()
            return redirect('display_parts')
    else:
        form = PartForm(instance=part)
    return render(request, 'setupfor/part_form.html', {'form': form, 'title': 'Edit Part'})

def delete_part(request, id):
    # Get the Part object by id or return 404 if not found
    part = get_object_or_404(Part, id=id)
    if request.method == 'POST':
        part.delete()
        return redirect('display_parts')
    return render(request, 'setupfor/delete_part.html', {'part': part})





# =========================================================================
# =========================================================================
# ======================== JSON API Endpoint View =========================
# =========================================================================
# =========================================================================

def fetch_part_for_asset(request):
    # Get asset number and timestamp from GET parameters
    asset_number = request.GET.get('asset_number')
    timestamp_str = request.GET.get('timestamp')

    # Initialize the response data
    response_data = {
        'asset_number': asset_number,
        'timestamp': timestamp_str,
        'part_number': None
    }

    if asset_number and timestamp_str:
        try:
            # Convert timestamp string to datetime object
            timestamp = timezone.datetime.fromisoformat(timestamp_str)
            # Get the part at the given time for the asset
            part = SetupFor.setupfor_manager.get_part_at_time(asset_number, timestamp)
            # Update response data with the part number
            if part:
                response_data['part_number'] = part.part_number
            else:
                response_data['error'] = 'No part found for the given asset at the specified time.'
        except ValueError:
            # Handle invalid timestamp format
            response_data['error'] = 'Invalid timestamp format. Please use ISO format (YYYY-MM-DDTHH:MM:SS).'
    else:
        response_data['error'] = 'Missing asset_number or timestamp parameter.'

    return JsonResponse(response_data)


# =======================================================================================
# Example usages of the fetch_part_for_asset API endpoint
# =======================================================================================
# To query the API endpoint, you need to make a GET request with 'asset_number' and 'timestamp' parameters.
# Below are some example usage using curl. The timestamp parameter should be a string representing the date and time in ISO 8601 format.: YYYY-MM-DDTHH:MM

# YYYY: Four-digit year (e.g., 2024)
# MM: Two-digit month (01 for January, 12 for December)
# DD: Two-digit day of the month (01 to 31)
# T: Separator between date and time (literally the letter 'T')
# HH: Two-digit hour in 24-hour format (00 to 23)
# MM: Two-digit minutes (00 to 59)

# Using curl:
# ---------------------------------------------------------------------------------------
# curl -X GET "http://10.4.1.232:8081/api/fetch_part_for_asset/?asset_number=Asset123&timestamp=2024-07-25T14:30:00"

# =======================================================================================









# =============================================================================================
# =============================================================================================
# =============================== Input API Endpoint ==========================================
# =============================================================================================
# =============================================================================================


from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from ..models.setupfor_models import SetupFor, Asset, Part
import json

@csrf_exempt
def update_part_for_asset(request):
    """
    API endpoint to update or add a new SetupFor record based on asset and part numbers.

    This endpoint allows users to submit an asset number, part number, and timestamp to log a changeover.
    If the part number is the same as the most recent part running on that asset, no new entry is created.
    Otherwise, a new changeover entry is added with the provided timestamp.

    Request method:
        POST (Only POST requests are allowed)

    JSON Payload:
        {
            "asset_number": "<string>",  # Asset number as a string
            "part_number": "<string>",   # Part number as a string
            "timestamp": "<ISO8601>"     # Timestamp in ISO 8601 format, e.g., "2024-11-10T18:30:00"
        }

    Usage example (with curl):
        # To add or check a changeover for asset "728" with part "50-1713" at a specific timestamp
        curl -X POST -H "Content-Type: application/json" -d '{
            "asset_number": "728",
            "part_number": "50-1713",
            "timestamp": "2024-11-10T18:30:00"
        }' http://10.4.1.232:8082/plant/api/update_part_for_asset/

    """

    # Ensure the request is a POST; otherwise, return a 405 Method Not Allowed response.
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests are allowed'}, status=405)

    try:
        # Parse the JSON payload from the request body
        data = json.loads(request.body)
        asset_number = data.get('asset_number')  # Asset number provided in the request
        part_number = data.get('part_number')    # Part number provided in the request
        timestamp_str = data.get('timestamp')    # Timestamp string in ISO 8601 format

        # Check for required fields in the payload
        if not (asset_number and part_number and timestamp_str):
            return JsonResponse({'error': 'Missing asset_number, part_number, or timestamp'}, status=400)

        # Attempt to convert the timestamp string to a datetime object
        try:
            timestamp = timezone.datetime.fromisoformat(timestamp_str)
        except ValueError:
            # Return an error if the timestamp format is invalid
            return JsonResponse({'error': 'Invalid timestamp format. Use ISO 8601 (YYYY-MM-DDTHH:MM:SS)'}, status=400)

        # Retrieve the Asset and Part instances using the provided asset and part numbers
        asset = Asset.objects.filter(asset_number=asset_number).first()
        part = Part.objects.filter(part_number=part_number).first()

        # If either the asset or part does not exist, return a 404 Not Found response
        if not asset or not part:
            return JsonResponse({'error': 'Asset or part not found'}, status=404)

        # Find the most recent SetupFor record for the asset
        recent_setup = SetupFor.objects.filter(asset=asset).order_by('-since').first()

        # Check if the recent setup is the same as the current part
        if recent_setup and recent_setup.part == part:
            # If the most recent part matches the current part, no new changeover is needed
            return JsonResponse({
                'message': 'No new changeover needed; the asset is already running this part',
                'asset_number': asset_number,
                'part_number': part_number,
                'since': recent_setup.since
            })

        # If the part is different, create a new SetupFor record with the provided timestamp
        new_setup = SetupFor.objects.create(asset=asset, part=part, since=timestamp)
        return JsonResponse({
            'message': 'New changeover created',
            'asset_number': asset_number,
            'part_number': part_number,
            'since': new_setup.since
        })

    # Handle JSON decoding errors (invalid JSON format in request body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)

    # Handle any other unexpected errors and return a 500 Internal Server Error response
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)




# =======================================================
# =======================================================
# ========== Refreshed setupFor views and page ==========
# =======================================================
# =======================================================


@login_required(login_url="login")
def display_setups(request):
    # Retrieve all SetupFor records ordered by descending changeover datetime (since)
    setups = SetupFor.objects.all().order_by('-since')
    paginator = Paginator(setups, 100)
    page_obj = paginator.page(1)
    eastern = pytz.timezone('US/Eastern')
    
    # Add both a human-readable and a datetime-local formatted value for each record
    for setup in page_obj:
        setup.since_human = datetime.fromtimestamp(setup.since, eastern).strftime("%Y-%m-%d %H:%M")
        setup.since_local = datetime.fromtimestamp(setup.since, eastern).strftime("%Y-%m-%dT%H:%M")
    
    # Retrieve lists of assets and parts for the dropdown menus
    assets = Asset.objects.all().order_by('asset_number')
    parts = Part.objects.all().order_by('part_number')
    
    return render(request, 'setupfor/display_setups.html', {
        'setups': page_obj,
        'assets': assets,
        'parts': parts,
    })

def load_more_setups(request):
    # Get the requested page number from GET parameters, default to 2
    page_number = request.GET.get('page', 2)
    try:
        page_number = int(page_number)
    except ValueError:
        page_number = 2

    setups = SetupFor.objects.all().order_by('-since')
    paginator = Paginator(setups, 100)
    
    try:
        page_obj = paginator.page(page_number)
    except EmptyPage:
        return JsonResponse({'records': []})
    
    eastern = pytz.timezone('US/Eastern')
    records = []
    for setup in page_obj:
        since_human = datetime.fromtimestamp(setup.since, eastern).strftime("%Y-%m-%d %H:%M")
        since_local = datetime.fromtimestamp(setup.since, eastern).strftime("%Y-%m-%dT%H:%M")
        records.append({
            'id': setup.id,
            'asset': setup.asset.asset_number,
            'asset_id': setup.asset.id,
            'part': setup.part.part_number,
            'part_id': setup.part.id,
            'since_human': since_human,
            'since_local': since_local,
        })
    
    return JsonResponse({'records': records})

@require_POST
def update_setup(request):
    record_id = request.POST.get('record_id')
    asset_id = request.POST.get('asset_id')
    part_id = request.POST.get('part_id')
    since_value = request.POST.get('since')  # Expecting format "YYYY-MM-DDTHH:MM"
    
    try:
        setup = SetupFor.objects.get(id=record_id)
    except SetupFor.DoesNotExist:
        return JsonResponse({'error': 'Record not found'}, status=404)
    
    try:
        asset = Asset.objects.get(id=asset_id)
        part = Part.objects.get(id=part_id)
    except (Asset.DoesNotExist, Part.DoesNotExist):
        return JsonResponse({'error': 'Asset or Part not found'}, status=400)
    
    try:
        eastern = pytz.timezone('US/Eastern')
        dt = datetime.strptime(since_value, "%Y-%m-%dT%H:%M")
        # Localize the datetime to Eastern Time
        dt = eastern.localize(dt)
        timestamp = dt.timestamp()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    # Update record fields
    setup.asset = asset
    setup.part = part
    setup.since = timestamp
    setup.save()
    
    # Format values to send back to the client
    since_human = dt.strftime("%Y-%m-%d %H:%M")
    since_local = dt.strftime("%Y-%m-%dT%H:%M")
    
    return JsonResponse({
        'record_id': setup.id,
        'asset': setup.asset.asset_number,
        'asset_id': setup.asset.id,
        'part': setup.part.part_number,
        'part_id': setup.part.id,
        'since_human': since_human,
        'since_local': since_local,
    })


@require_POST
def add_setup(request):
    asset_id = request.POST.get('asset_id', '').strip()
    part_id = request.POST.get('part_id', '').strip()
    since_value = request.POST.get('since', '').strip()  # Expected format "YYYY-MM-DDTHH:MM"
    
    # Check if required fields are provided
    if not asset_id or not part_id or not since_value:
        return JsonResponse({'error': 'Please select an asset, part, and date/time.'}, status=400)
    
    try:
        asset = Asset.objects.get(id=asset_id)
        part = Part.objects.get(id=part_id)
    except (Asset.DoesNotExist, Part.DoesNotExist):
        return JsonResponse({'error': 'Asset or Part not found'}, status=400)
    
    try:
        eastern = pytz.timezone('US/Eastern')
        dt = datetime.strptime(since_value, "%Y-%m-%dT%H:%M")
        # Localize datetime to Eastern Time
        dt = eastern.localize(dt)
        timestamp = dt.timestamp()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    # Create a new SetupFor record
    setup = SetupFor.objects.create(asset=asset, part=part, since=timestamp)
    
    # Format the date for display
    since_human = dt.strftime("%Y-%m-%d %H:%M")
    since_local = dt.strftime("%Y-%m-%dT%H:%M")
    
    return JsonResponse({
        'record_id': setup.id,
        'asset': setup.asset.asset_number,
        'asset_id': setup.asset.id,
        'part': setup.part.part_number,
        'part_id': setup.part.id,
        'since_human': since_human,
        'since_local': since_local,
    })


@csrf_exempt
@require_POST
def check_part(request):
    asset_id = request.POST.get('asset_id')
    datetime_str = request.POST.get('datetime')

    if not asset_id or not datetime_str:
        return JsonResponse({'error': 'Asset and datetime are required.'})

    # Parse the datetime string from the input. The datetime-local input typically returns an ISO format.
    dt = parse_datetime(datetime_str)
    if dt is None:
        return JsonResponse({'error': 'Invalid datetime format.'})

    # Convert the datetime to epoch integer.
    # If your datetime is timezone naive, dt.timestamp() treats it as local time.
    epoch_time = int(dt.timestamp())

    # Query for the latest SetupFor record for the given asset that occurred on or before the provided datetime.
    record = SetupFor.objects.filter(asset_id=asset_id, since__lte=epoch_time).order_by('-since').first()

    if record:
        return JsonResponse({'part_number': record.part.part_number})
    else:
        return JsonResponse({'error': 'No record found for the given asset and time.'})
