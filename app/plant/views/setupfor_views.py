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



def index(request):
    return render(request, 'setupfor/index.html')

def natural_sort_key(s):
    """
    Generate a key for natural sorting of strings containing numbers.

    Splits the input string into alternating non-numeric and numeric segments,
    converting any purely digit segments to integers so that comparisons treat
    numbers by their numeric value rather than lexicographically.

    Examples
    --------
    >>> sorted(['item2', 'item10', 'item1'], key=natural_sort_key)
    ['item1', 'item2', 'item10']

    Parameters
    ----------
    s : str
        The string to generate a sort key for.

    Returns
    -------
    list[Union[str, int]]
        A list of segments where numeric substrings are integers and others are strings,
        suitable for use as a sort key in Python’s sorted() or list.sort().
    """
    # Split the string into numeric and non-numeric parts
    parts = re.split(r'(\d+)', s)
    # Convert numeric parts to integers
    return [int(part) if part.isdigit() else part for part in parts]


@login_required(login_url="login")
def display_assets(request):
    """
    Display a paginated list of assets, optionally filtered by a search query.

    GET parameters
    --------------
    q : str, optional
        Case-insensitive substring to filter assets by `asset_number` or `asset_name`.
    show : int, optional
        Number of assets to display per page (defaults to 10).
    page : int, optional
        Page number for pagination.

    Behavior
    --------
    1. Retrieves all Asset instances whose `asset_number` or `asset_name` contains the search query.
    2. Sorts the resulting list using natural sort order on `asset_number`.
    3. Paginates the sorted list according to `show` and `page` parameters.
    4. Renders the 'setupfor/display_assets.html' template with:
       - `page_obj`: the paginated Page of Asset objects.
       - `search_query`: the original query string for echoing in the UI.

    Access Control
    --------------
    - User must be authenticated; otherwise they are redirected to the login page.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP GET request with possible query parameters.

    Returns
    -------
    django.http.HttpResponse
        Renders the asset display template populated with the paginated assets.
    """
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
    """
    Display and process the form to create a new Asset, with optional redirection back to password creation.

    GET:
      - Renders the 'setupfor/asset_form.html' template with:
        • form: an empty AssetForm instance.
        • title: "Add New Asset".
        • from_password_create flag (True if the URL contains ?from_password_create=true).

    POST:
      - Binds submitted data to AssetForm.
      - If valid:
         • Saves the new Asset.
         • If `from_password_create` is True, redirects to the 'password_create' view.
         • Otherwise redirects to 'display_assets'.
      - If invalid and the request is AJAX (X-Requested-With header), returns JSON:
         {
           "success": False,
           "errors": form.errors
         }
      - If invalid and non-AJAX, re-renders the form template with errors.

    Query Parameters
    ----------------
    from_password_create : str ("true" or "false", default "false")
        If "true", indicates the user initiated asset creation from the password creation workflow
        and should be returned there upon success.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request.

    Returns
    -------
    django.http.HttpResponse or django.http.JsonResponse
        - On GET: HTML page with the asset creation form.
        - On successful POST: HTTP redirect to 'password_create' or 'display_assets'.
        - On invalid AJAX POST: JSON with form errors.
        - On invalid non-AJAX POST: HTML page re-rendered with form errors.
    """
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
    """
    Display and process the form to edit an existing Asset.

    GET:
    - Retrieves the Asset by its `id` or returns HTTP 404.
    - Instantiates an AssetForm pre-filled with the asset’s data.
    - Renders 'setupfor/asset_form.html' with context:
        • form: the bound AssetForm
        • title: "Edit Asset"

    POST:
    - Binds submitted data to AssetForm with the existing asset instance.
    - If valid, saves changes and redirects to 'display_assets'.
    - If invalid, re-renders the form template with validation errors.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request (GET to display the form, POST to submit changes).
    id : int
        Primary key of the Asset to edit.

    Returns
    -------
    django.http.HttpResponse
        - On GET or invalid POST: renders the asset form template.
        - On successful POST: redirects to the asset listing view.
    """
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
    """
    Display a confirmation page and handle deletion of an Asset.

    GET:
      - Retrieves the Asset by `id` or returns HTTP 404 if not found.
      - Renders 'setupfor/delete_asset.html' with the asset context for confirmation.

    POST:
      - Deletes the specified Asset.
      - Redirects to 'display_assets' after successful deletion.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, which may be GET (to confirm) or POST (to delete).
    id : int
        Primary key of the Asset to delete.

    Returns
    -------
    django.http.HttpResponse
        - On GET: renders the deletion confirmation template.
        - On POST: redirects to the asset listing view.
    """
    # Get the Asset object by id or return 404 if not found
    asset = get_object_or_404(Asset, id=id)
    if request.method == 'POST':
        asset.delete()
        return redirect('display_assets')
    return render(request, 'setupfor/delete_asset.html', {'asset': asset})


@login_required(login_url="login")
def display_parts(request):
    """
    Display a paginated list of parts, optionally filtered by a search query.

    GET parameters
    --------------
    q : str, optional
        Case-insensitive substring to filter parts by `part_number` or `part_name`.
    show : int, optional
        Number of parts to display per page (defaults to 10).
    page : int, optional
        Page number for pagination.

    Behavior
    --------
    1. Retrieves all Part instances whose `part_number` or `part_name` contains the search query.
    2. Sorts the resulting list using natural sort order on `part_number`.
    3. Paginates the sorted list according to `show` and `page` parameters.
    4. Renders the 'setupfor/display_parts.html' template with:
       - `page_obj`: the paginated Page of Part objects.
       - `search_query`: the original query string for echoing in the UI.

    Access Control
    --------------
    - User must be authenticated; otherwise they are redirected to the login page.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP GET request with possible query parameters.

    Returns
    -------
    django.http.HttpResponse
        Renders the parts display template populated with the paginated parts.
    """
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
    """
    Display and process the form to create a new Part record.

    GET:
      - Instantiates an empty PartForm.
      - Renders 'setupfor/part_form.html' with context:
          • form: the empty PartForm
          • title: "Add New Part"

    POST:
      - Binds submitted data to PartForm.
      - If valid, saves the new Part instance and redirects to 'display_parts'.
      - If invalid, re-renders the form template with validation errors.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, which may be GET (to display the form)
        or POST (to submit the new part data).

    Returns
    -------
    django.http.HttpResponse
        - On GET or invalid POST: renders the part creation form.
        - On valid POST: redirects to the parts listing view.
    """
    if request.method == 'POST':
        form = PartForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('display_parts')
    else:
        form = PartForm()
    return render(request, 'setupfor/part_form.html', {'form': form, 'title': 'Add New Part'})

def edit_part(request, id):
    """
    Display and process the form to edit an existing Part record.

    GET:
      - Retrieves the Part by its `id` or returns HTTP 404 if not found.
      - Instantiates a PartForm pre-filled with the part’s data.
      - Renders 'setupfor/part_form.html' with context:
          • form: the bound PartForm
          • title: "Edit Part"

    POST:
      - Binds submitted data to PartForm with the existing part instance.
      - If valid, saves changes and redirects to 'display_parts'.
      - If invalid, re-renders the form template with validation errors.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request (GET to display the form, POST to submit changes).
    id : int
        Primary key of the Part to edit.

    Returns
    -------
    django.http.HttpResponse
        - On GET or invalid POST: renders the part edit form template.
        - On successful POST: redirects to the part listing view.
    """
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
    """
    Display a confirmation page and handle deletion of a Part record.

    GET:
      - Retrieves the Part by its `id` or returns HTTP 404 if not found.
      - Renders 'setupfor/delete_part.html' with the part in context for confirmation.

    POST:
      - Deletes the specified Part from the database.
      - Redirects to the 'display_parts' view after successful deletion.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, which may be GET (to confirm deletion) or POST (to perform deletion).
    id : int
        Primary key of the Part to delete.

    Returns
    -------
    django.http.HttpResponse
        - On GET: renders the deletion confirmation template.
        - On POST: redirects to the parts listing view.
    """
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
    """
    Retrieve the part number assigned to a given asset at a specific timestamp.

    Expects GET parameters:
      - asset_number (str): Identifier of the asset to query.
      - timestamp (str):    ISO 8601 datetime string ("YYYY-MM-DDTHH:MM:SS") 
                            representing the point in time to check.

    Workflow:
      1. Validates that both `asset_number` and `timestamp` are provided;
         if missing, returns JSON with an `error` key.
      2. Parses the `timestamp` into a datetime object; on format error,
         returns JSON with an appropriate `error`.
      3. Calls `SetupFor.setupfor_manager.get_part_at_time(asset_number, timestamp)`
         to fetch the corresponding Part instance.
      4. Returns a JsonResponse containing:
         - `asset_number`: the original asset identifier.
         - `timestamp`:    the original timestamp string.
         - `part_number`:  the `part_number` of the found Part, or `None`.
         - `error`:        present only if lookup failed or parameters were invalid.

    Returns
    -------
    django.http.JsonResponse
        JSON with keys `asset_number`, `timestamp`, `part_number`, and optionally `error`.
    """
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
    """
    Display a paginated list of setup changeover records with human- and machine-friendly timestamps.

    GET:
      - Retrieves all `SetupFor` records, ordered by descending `since` epoch timestamp.
      - Paginates the records (100 per page, showing the first page by default).
      - Converts each record’s `since` epoch (assumed US/Eastern) into:
          • `since_human`: formatted "YYYY-MM-DD HH:MM"
          • `since_local`: formatted "YYYY-MM-DDTHH:MM" (suitable for `<input type="datetime-local">`)
      - Fetches all `Asset` and `Part` instances (ordered by their number fields) for populating dropdowns.
      - Renders the 'setupfor/display_setups.html' template with context:
          • `setups`: the paginated page of setup records
          • `assets`: list of all assets
          • `parts`:  list of all parts

    Access Control
    --------------
    - User must be authenticated; otherwise they are redirected to the login page.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP GET request.

    Returns
    -------
    django.http.HttpResponse
        Renders the setups display template populated with paginated records and reference data.
    """
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
    """
    AJAX endpoint to load additional setup changeover records, paginated.

    Expects a GET request with:
      - page (int, optional): The 1-based page number to retrieve (defaults to 2).

    Workflow:
      1. Parse and sanitize the `page` parameter, defaulting to 2 on missing or invalid input.
      2. Query all `SetupFor` records ordered by descending `since` timestamp.
      3. Paginate at 100 records per page.
      4. If the requested page is beyond the last page, return `{'records': []}`.
      5. Otherwise, for each record on that page, compute:
         - `since_human`: formatted "YYYY-MM-DD HH:MM" in US/Eastern.
         - `since_local`: formatted "YYYY-MM-DDTHH:MM" in US/Eastern.
      6. Return a JSON response `{'records': [...]}` where each entry includes:
         - id, asset (asset_number), asset_id
         - part (part_number), part_id
         - since_human, since_local

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP GET request, with optional `page` query parameter.

    Returns
    -------
    django.http.JsonResponse
        JSON object with key `records` containing a list of dictionaries for each setup entry.
    """
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
    """
    AJAX endpoint to update an existing setup changeover record.

    Expects form-encoded POST parameters:
      - record_id (int):   Primary key of the SetupFor record to update.
      - asset_id (int):    Primary key of the new Asset to assign.
      - part_id (int):     Primary key of the new Part to assign.
      - since (str):       New timestamp in ISO format "YYYY-MM-DDTHH:MM", Eastern Time.

    Workflow:
      1. Retrieve the SetupFor instance by `record_id`; return HTTP 404 if not found.
      2. Retrieve the Asset and Part by their IDs; return HTTP 400 if either is missing.
      3. Parse and localize the `since` string as US/Eastern time; convert to a Unix timestamp.
         Return HTTP 400 on format errors.
      4. Update the record’s `asset`, `part`, and `since` fields and save.
      5. Respond with JSON containing:
         - record_id, asset (asset_number), asset_id
         - part (part_number), part_id
         - since_human: formatted "YYYY-MM-DD HH:MM"
         - since_local: formatted "YYYY-MM-DDTHH:MM"

    Returns
    -------
    django.http.JsonResponse
        On success: JSON object with the updated record details.
        On error:   JSON object `{'error': <message>}` with appropriate HTTP status code.
    """
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
    """
    AJAX endpoint to create a new setup changeover record.

    Expects form-encoded POST parameters:
      - asset_id (str):  Primary key of the Asset to assign.
      - part_id (str):   Primary key of the Part to assign.
      - since (str):     Timestamp in ISO format "YYYY-MM-DDTHH:MM" (US/Eastern time).

    Workflow:
      1. Validate that `asset_id`, `part_id`, and `since` are all provided; return HTTP 400 if any are missing.
      2. Retrieve the Asset and Part instances; return HTTP 400 if either does not exist.
      3. Parse `since` into a naive datetime, localize to US/Eastern, and convert to Unix timestamp; return HTTP 400 on format errors.
      4. Create a new `SetupFor` record with the given `asset`, `part`, and `since` timestamp.
      5. Respond with JSON containing:
         - record_id (int)
         - asset (str): asset_number
         - asset_id (int)
         - part (str): part_number
         - part_id (int)
         - since_human (str): formatted "YYYY-MM-DD HH:MM"
         - since_local (str): formatted "YYYY-MM-DDTHH:MM"

    Returns
    -------
    django.http.JsonResponse
        On success: JSON with the newly created record’s details.
        On error:   JSON `{'error': message}` with an appropriate HTTP 400 status.
    """
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
    """
    AJAX endpoint to determine which part was installed on an asset at a given time.

    Expects form-encoded POST parameters:
      - asset_id (str):      Primary key of the Asset to query.
      - datetime (str):      ISO-formatted datetime string (e.g. from an `<input type="datetime-local">`).

    Workflow:
      1. Validate that both `asset_id` and `datetime` are provided; return JSON error otherwise.
      2. Parse `datetime` using `parse_datetime`; return JSON error if parsing fails.
      3. Convert the resulting `datetime` to a Unix epoch integer (seconds since the epoch).
      4. Query `SetupFor` for the most recent record for that asset whose `since` timestamp
         is less than or equal to the provided epoch.
      5. If found, return `{'part_number': <str>}`; otherwise return `{'error': ...}`.

    Returns
    -------
    django.http.JsonResponse
        - Success: `{'part_number': <part_number>}`
        - Failure: `{'error': <message>}`
    """
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
