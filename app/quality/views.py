# quality/views.py
from django.shortcuts import render, get_object_or_404, redirect
from .models import Feat
from .forms import FeatForm
from plant.models.setupfor_models import Part
from django.db import transaction  
from django.db.models import F
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import ScrapForm, FeatEntry, SupervisorAuthorization
import json
from .models import Feat
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
import os
import importlib.util
import inspect
import re




def index(request):
    is_quality_manager = False
    if request.user.is_authenticated:
        is_quality_manager = request.user.groups.filter(name="quality_manager").exists()
    context = {
        'is_quality_manager': is_quality_manager,
        # ... any other context variables ...
    }
    return render(request, 'quality/index.html', context)


def final_inspection(request, part_number):
    """
    Render the final inspection scrap form for a specific part.

    Retrieves the Part identified by `part_number` (returning 404 if not found),
    then fetches all associated Feat records. Renders the
    'quality/scrap_form.html' template with:
      - `part`: the Part instance under inspection
      - `feats`: a QuerySet of Feat objects linked to that Part

    Parameters
    ----------
    request : django.http.HttpRequest
        The HTTP request object.
    part_number : str
        The unique identifier for the Part to inspect.

    Returns
    -------
    django.http.HttpResponse
        The rendered scrap form page populated with the part and its feats.
    """
    # Get the Part object based on the part_number
    part = get_object_or_404(Part, part_number=part_number)
    
    # Get all feats associated with this part
    feats = part.feat_set.all()

    # Pass the feats and part to the template
    return render(request, 'quality/scrap_form.html', {'part': part, 'feats': feats})





def scrap_form_management(request):
    """
    Display scrap form management page listing all parts and their features.

    Retrieves all Part instances (including those without associated Feat records),
    prefetches related `feat_set` for efficiency, and renders the
    'quality/scrap_form_management.html' template with:
      - `parts`: a QuerySet of all Part objects, each with its `feat_set`.

    Parameters
    ----------
    request : django.http.HttpRequest
        The HTTP request object.

    Returns
    -------
    django.http.HttpResponse
        The rendered management page showing parts and their features.
    """
    # Get all parts, whether or not they have feats
    parts = Part.objects.all().prefetch_related('feat_set')
    return render(request, 'quality/scrap_form_management.html', {'parts': parts})



def feat_create(request):
    """
    Create a new Feat entry, optionally pre-associating it with a Part.

    - GET:
        • If `part_id` is provided as a query parameter, fetch the corresponding Part
          (404 if not found), compute the next `order` as (existing count + 1),
          and instantiate FeatForm with initial `part` and `order`.
        • Otherwise, instantiate an empty FeatForm.
        • Render 'quality/feat_form.html' with the form.

    - POST:
        • Bind FeatForm with request.POST.
        • If valid, save the new Feat within an atomic transaction
          (ensuring referential integrity).
        • Redirect to the 'scrap_form_management' view on success.
        • If invalid, re-render the form with errors.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, may include:
          - GET parameter `part_id` (int) for pre-association.
          - POST data matching the FeatForm fields.

    Returns
    -------
    django.http.HttpResponse or django.http.HttpResponseRedirect
        - On GET or invalid POST: renders 'quality/feat_form.html' with `form` context.
        - On successful POST: redirects to 'scrap_form_management'.
    """
    part_id = request.GET.get('part_id')  # Retrieve the part ID from the query parameters
    if request.method == 'POST':
        form = FeatForm(request.POST)
        if form.is_valid():
            with transaction.atomic():  # Ensure atomic transaction
                # Save the new feat without adjusting orders
                form.save()
            return redirect('scrap_form_management')
    else:
        if part_id:
            part = get_object_or_404(Part, id=part_id)
            # Calculate the next order number
            next_order = part.feat_set.count() + 1
            form = FeatForm(initial={'part': part, 'order': next_order})  # Pre-fill part and order
        else:
            form = FeatForm()
    
    return render(request, 'quality/feat_form.html', {'form': form})


def feat_update(request, pk):
    """
    Edit an existing Feat entry.

    - GET:
        • Retrieve the Feat by primary key (404 if not found).
        • Instantiate FeatForm with the existing instance.
        • Render 'quality/feat_form.html' with the form for editing.

    - POST:
        • Bind FeatForm to request.POST and the existing `feat` instance.
        • If valid, save updates (without reordering other feats).
        • Redirect to the 'scrap_form_management' view on success.
        • If invalid, re-render the form with validation errors.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request.
    pk : int
        The primary key of the Feat to update.

    Returns
    -------
    django.http.HttpResponse or django.http.HttpResponseRedirect
        - On GET or invalid POST: renders 'quality/feat_form.html' with `form` context.
        - On successful POST: redirects to 'scrap_form_management'.
    """
    feat = get_object_or_404(Feat, pk=pk)
    if request.method == 'POST':
        form = FeatForm(request.POST, instance=feat)
        if form.is_valid():
            # Save the updated feat without adjusting orders
            form.save()
            return redirect('scrap_form_management')
    else:
        form = FeatForm(instance=feat)
    return render(request, 'quality/feat_form.html', {'form': form})

def feat_delete(request, pk):
    """
    Delete an existing Feat entry without reordering remaining feats.

    - GET:
        • Retrieve the Feat by primary key (404 if not found).
        • Render 'quality/feat_confirm_delete.html' to confirm deletion.

    - POST:
        • Delete the Feat instance.
        • Redirect to the 'scrap_form_management' view.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request.
    pk : int
        The primary key of the Feat to delete.

    Returns
    -------
    django.http.HttpResponse or django.http.HttpResponseRedirect
        - On GET: renders 'quality/feat_confirm_delete.html' with `feat` context.
        - On POST: redirects to 'scrap_form_management' after deletion.
    """
    feat = get_object_or_404(Feat, pk=pk)

    if request.method == 'POST':
        # Simply delete the feat without adjusting the orders of remaining feats
        feat.delete()
        return redirect('scrap_form_management')
    
    return render(request, 'quality/feat_confirm_delete.html', {'feat': feat})


def feat_move_up(request, pk):
    """
    Shift a Feat’s display order up by one position within its Part.

    Retrieves the Feat identified by `pk`. If its `order` is greater than 1,
    performs an atomic swap:
      1. Increments the `order` of the sibling Feat immediately above
         (current order − 1).
      2. Decrements this Feat’s `order` by 1 and saves it.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request (typically AJAX).
    pk : int
        The primary key of the Feat to move upward.

    Returns
    -------
    django.http.JsonResponse
        A JSON response indicating success: `{'success': True}`.
    """
    feat = get_object_or_404(Feat, pk=pk)
    if feat.order > 1:
        with transaction.atomic():
            # Decrement the order of the feat just above
            Feat.objects.filter(part=feat.part, order=feat.order - 1).update(order=F('order') + 1)
            # Move this feat up
            feat.order -= 1
            feat.save()
    return JsonResponse({'success': True})


def feat_move_down(request, pk):
    """
    Shift a Feat’s display order down by one position within its Part.

    Retrieves the Feat identified by `pk`. If its `order` is less than the
    count of feats for that Part, performs an atomic swap:
      1. Decrements the `order` of the sibling Feat immediately below
         (current order + 1).
      2. Increments this Feat’s `order` by 1 and saves it.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request (typically AJAX).
    pk : int
        The primary key of the Feat to move downward.

    Returns
    -------
    django.http.JsonResponse
        A JSON response indicating success: `{'success': True}`.
    """
    feat = get_object_or_404(Feat, pk=pk)
    max_order = feat.part.feat_set.count()
    if feat.order < max_order:
        with transaction.atomic():
            # Increment the order of the feat just below
            Feat.objects.filter(part=feat.part, order=feat.order + 1).update(order=F('order') - 1)
            # Move this feat down
            feat.order += 1
            feat.save()
    return JsonResponse({'success': True})



# =========================================================
# ================= Proper View ===========================
# =========================================================

@csrf_exempt
def submit_scrap_form(request):
    """
    Accept and process a JSON-based scrap form submission, then create related records.

    Only POST requests are supported. Expects a JSON payload containing at least:
      - partNumber (str)
      - date (str or date; will be passed directly to the ScrapForm.date field)
      - operator (str)
      - shift (int or str)
      - qtyPacked (int)
      - totalDefects (int)
      - totalInspected (int)
      - comments (str)
      - detailOther (str)
      - tpcNumber (str)
      - feats (list of dicts), each with:
          • featName (str)
          • defects (int)

    Workflow:
      1. Parse the JSON body.
      2. Create a new `ScrapForm` instance, storing the entire payload in its `payload` field.
      3. For each entry in `feats`, create a `FeatEntry` linked to the new ScrapForm.
      4. Respond with a JSON object:
         `{ "status": "success", "redirect_url": "/quality/pdf/part_clock/?part_number=<partNumber>" }`

    Error Handling:
      - Non-POST requests yield HTTP 400 with `{ "status": "error", "message": "Invalid request method." }`.
      - Malformed JSON or missing required keys will raise a Python exception (uncaught),
        resulting in a 500 error.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, expected to be a POST with a JSON payload.

    Returns
    -------
    django.http.JsonResponse
        On success: `{"status": "success", "redirect_url": <url>}` (HTTP 200).
        On invalid method: `{"status": "error", "message": "Invalid request method."}` (HTTP 400).
    """
    if request.method == 'POST':
        # Load the JSON payload from the request body
        payload = json.loads(request.body)

        # Save the main ScrapForm data
        scrap_form = ScrapForm.objects.create(
            partNumber=payload.get('partNumber', ''),
            date=payload.get('date', None),
            operator=payload.get('operator', ''),
            shift=payload.get('shift', None),
            qtyPacked=payload.get('qtyPacked', None),
            totalDefects=payload.get('totalDefects', None),
            totalInspected=payload.get('totalInspected', None),
            comments=payload.get('comments', ''),
            detailOther=payload.get('detailOther', ''),
            tpc_number=payload.get('tpcNumber', ''),
            payload=payload
        )

        # Save each feat as a FeatEntry
        part_number = payload.get('partNumber', '')
        for feat in payload.get('feats', []):
            FeatEntry.objects.create(
                scrap_form=scrap_form,
                featName=feat.get('featName', ''),
                defects=int(feat.get('defects', 0)),
                partNumber=part_number
            )

        # Redirect to pdf_part_clock_form with part number in context
        return JsonResponse({'status': 'success', 'redirect_url': f'/quality/pdf/part_clock/?part_number={part_number}'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)









# ====================================================
# ==============      Dummy View       ===============
# ==============   Simulated Tables    ===============
# ====================================================


# @csrf_exempt
# def submit_scrap_form(request):
#     if request.method == 'POST':
#         # Load the JSON payload from the request body
#         payload = json.loads(request.body)

#         # Simulate creating a ScrapForm entry
#         scrap_form_simulated = {
#             'partNumber': payload.get('partNumber', ''),
#             'date': payload.get('date', None),
#             'operator': payload.get('operator', ''),
#             'shift': payload.get('shift', None),
#             'qtyInspected': payload.get('qtyInspected', None),
#             'totalDefects': payload.get('totalDefects', None),
#             'totalAccepted': payload.get('totalAccepted', None),
#             'comments': payload.get('comments', ''),
#             'detailOther': payload.get('detailOther', ''),
#             'payload': json.dumps(payload),  # Store the entire payload as JSON string
#             'created_at': 'Simulated Timestamp'  # Replace with the current timestamp in a real scenario
#         }

#         # Simulate creating FeatEntry entries
#         feat_entries_simulated = []
#         for feat in payload.get('feats', []):
#             feat_entry_simulated = {
#                 'scrap_form_id': 'Simulated ScrapForm ID',
#                 'featName': feat.get('featName', ''),
#                 'defects': int(feat.get('defects', 0))
#             }
#             feat_entries_simulated.append(feat_entry_simulated)

#         # Print out the simulated ScrapForm table entry
#         print("Simulated ScrapForm Table Entry:")
#         for key, value in scrap_form_simulated.items():
#             print(f"{key}: {value}")

#         # Print out the simulated FeatEntry table entries
#         print("\nSimulated FeatEntry Table Entries:")
#         for entry in feat_entries_simulated:
#             for key, value in entry.items():
#                 print(f"{key}: {value}")
#             print("-----")

#         # Respond with a success message
#         return JsonResponse({'status': 'success', 'message': 'Form submitted successfully!'})

#     return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)



@csrf_exempt
def store_supervisor_auth(request):
    """
    Store a supervisor’s authorization for a specific part and feature.

    Accepts only POST requests with a JSON body containing:
      - supervisor_id (int):   The primary key of the Supervisor.
      - part_number (str):     The identifier of the Part being authorized.
      - feat_name (str):       The name of the Feat requiring authorization.

    Workflow:
      1. Parse and validate the JSON payload.
      2. Create a new SupervisorAuthorization record with the provided data.
      3. Return a JSON response indicating success.

    Error Handling:
      - On malformed JSON or database errors, returns HTTP 500 with
        `{"status": "error", "message": <error message>}`.
      - For non-POST requests, returns HTTP 400 with
        `{"status": "error", "message": "Invalid request method."}`.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, expected to be a POST with a JSON body.

    Returns
    -------
    django.http.JsonResponse
        - On success: `{"status": "success", "message": "Authorization stored successfully!"}` (HTTP 200).
        - On error:   `{"status": "error", "message": <error details>}` with appropriate HTTP status.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            SupervisorAuthorization.objects.create(
                supervisor_id=data.get('supervisor_id'),
                part_number=data.get('part_number'),
                feat_name=data.get('feat_name')
            )
            return JsonResponse({'status': 'success', 'message': 'Authorization stored successfully!'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)




def forms_page(request):
    """
    Display a part selection page or redirect to the final inspection form.

    - GET:
        • Fetch all Part instances.
        • Render 'quality/forms_page.html' with context:
            - `parts`: QuerySet of available Part objects.
    - POST:
        • Read `selected_part` from submitted form data.
        • If provided, redirect to the `final_inspection` view for that part_number.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, which may be GET or POST with form data.

    Returns
    -------
    django.http.HttpResponse or django.http.HttpResponseRedirect
        - On GET or missing selection: renders the part-selection template.
        - On valid POST with `selected_part`: redirects to `final_inspection`.
    """
    if request.method == 'POST':
        selected_part = request.POST.get('selected_part')
        if selected_part:
            # Redirect to the scrap_form view with the selected part number
            return redirect('final_inspection', part_number=selected_part)
    
    # If it's a GET request, just render the form selection page
    parts = Part.objects.all()
    return render(request, 'quality/forms_page.html', {'parts': parts})


from .models import PartMessage


@login_required(login_url="login")
def new_manager(request, part_number=None):
    """
    Display and allow editing of a custom message for a given part, restricted to logged-in users.

    - Access Control:
        • Requires authentication; unauthenticated users are redirected to "login".
    - Parameter Handling:
        • If `part_number` is None, immediately redirect to the 'forms_page' view.
    - Data Retrieval:
        • Fetch the Part identified by `part_number` (404 if not found).
        • Retrieve all associated Feat records.
        • Get or create a PartMessage record for this Part, providing `message` and `font_size` fields.
    - GET:
        • Render the 'quality/new_manager.html' template with context:
            - `part`: the Part instance
            - `feats`: its Feat queryset
            - `current_message`: the existing PartMessage.message
            - `current_font_size`: the existing PartMessage.font_size
            - `font_size_choices`: available font size options
    - POST:
        • Read `custom_message` and `font_size` from form data.
        • Update and save the PartMessage record.
        • Reflect changes in context for re-rendering.
    - Debug:
        • Prints initial and updated message/font_size to the console for troubleshooting.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, may be GET or POST.
    part_number : str or None
        The identifier for the Part to manage; if None, redirects to forms selection.

    Returns
    -------
    django.http.HttpResponse or django.http.HttpResponseRedirect
        - On missing `part_number`: redirect to 'forms_page'.
        - Otherwise: renders the management template with the PartMessage context.
    """
    if part_number is None:
        return redirect('forms_page')
    
    part = get_object_or_404(Part, part_number=part_number)
    feats = part.feat_set.all()

    # Get or create the PartMessage for this part
    part_message, created = PartMessage.objects.get_or_create(part=part)
    current_message = part_message.message
    current_font_size = part_message.font_size

    # Debug output: Initial state
    print(f"Initial PartMessage: message='{current_message}', font_size='{current_font_size}'")

    if request.method == 'POST':
        # Handle the message and font size update submission
        new_message = request.POST.get('custom_message', '').strip()
        new_font_size = request.POST.get('font_size', 'medium')
        print(f"Received from form: new_message='{new_message}', new_font_size='{new_font_size}'")

        # Save the updated message and font size
        part_message.message = new_message
        part_message.font_size = new_font_size
        part_message.save()

        # Update the debug state
        current_message = new_message
        current_font_size = new_font_size
        print(f"Updated PartMessage: message='{current_message}', font_size='{current_font_size}'")

    return render(request, 'quality/new_manager.html', {
        'part': part,
        'feats': feats,
        'current_message': current_message,
        'current_font_size': current_font_size,
        'font_size_choices': PartMessage.FONT_SIZE_CHOICES,
    })





@csrf_exempt
def update_feat_order(request):
    """
    Bulk-update the display order of Feat records via a JSON payload.

    Expects a POST request with a JSON array in the body, where each element
    is an object containing:
      - id (int):    The primary key of the Feat to update.
      - order (int): The new order value for that Feat.

    Workflow:
      1. Parse the JSON body into `order_data`.
      2. Open an atomic transaction.
      3. For each item in the array, update the corresponding Feat’s `order`.
      4. If all updates succeed, return `{"status": "success"}`.
      5. If any error occurs during updates, roll back and return
         `{"status": "error", "message": <error>}`.

    Error Handling:
      - Non-POST requests return HTTP 400 with
        `{"status": "error", "message": "Invalid request method."}`.
      - JSON parsing or database errors result in a JSON error response
        with the exception message.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, expected to be POST with a JSON body.

    Returns
    -------
    django.http.JsonResponse
        A JSON response indicating success or error.
    """
    if request.method == 'POST':
        order_data = json.loads(request.body)

        try:
            with transaction.atomic():
                for item in order_data:
                    feat_id = item['id']
                    new_order = item['order']
                    Feat.objects.filter(id=feat_id).update(order=new_order)
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)

@csrf_exempt
def update_feat(request):
    """
    Update fields of an existing Feat via JSON payload.

    Expects a POST request with a JSON body containing:
      - id (int):         The primary key of the Feat to update.
      - name (str):       The new name for the Feat.
      - alarm (any):      The new alarm value for the Feat.
      - critical (bool):  Whether the Feat is critical (defaults to False if omitted).

    Workflow:
      1. Parse the JSON payload.
      2. Retrieve the Feat instance by `id` (return error if not found).
      3. Update `name`, `alarm`, and `critical` fields.
      4. Save the Feat and return `{"status": "success"}`.
      5. On errors, return a JSON response with `status: "error"` and an error message.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, expected to be POST with JSON body.

    Returns
    -------
    django.http.JsonResponse
        - On success: `{"status": "success"}` (HTTP 200).
        - On missing Feat: `{"status": "error", "message": "Feat not found."}` (HTTP 200).
        - On other errors: `{"status": "error", "message": <error>}` (HTTP 200).
        - On invalid method: `{"status": "error", "message": "Invalid request method."}` (HTTP 400).
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        feat_id = data.get('id')
        new_name = data.get('name')
        new_alarm = data.get('alarm')
        new_critical = data.get('critical', False)  # Get the critical field, defaulting to False

        try:
            feat = Feat.objects.get(id=feat_id)
            feat.name = new_name
            feat.alarm = new_alarm
            feat.critical = new_critical  # Update the critical field
            feat.save()

            return JsonResponse({'status': 'success'})
        except Feat.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Feat not found.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)


@csrf_exempt
def delete_feat(request):
    """
    Delete a Feat record based on JSON input.

    Expects a POST request with a JSON body containing:
      - id (int): The primary key of the Feat to delete.

    Workflow:
      1. Parse the JSON payload and extract `id`.
      2. Retrieve the Feat instance by primary key.
      3. Delete the Feat.
      4. Return a JSON response indicating success.

    Error Handling:
      - If the Feat does not exist, returns `{"status": "error", "message": "Feat not found."}`.
      - On other exceptions, returns `{"status": "error", "message": <error message>}`.
      - Non-POST requests return HTTP 400 with `{"status": "error", "message": "Invalid request method."}`.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, expected to be POST with a JSON body.

    Returns
    -------
    django.http.JsonResponse
        - On success: `{"status": "success"}` (HTTP 200).
        - On error:   `{"status": "error", "message": <details>}`.
    """
    if request.method == 'POST':
        data = json.loads(request.body)
        feat_id = data.get('id')

        try:
            feat = Feat.objects.get(id=feat_id)
            feat.delete()

            return JsonResponse({'status': 'success'})
        except Feat.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Feat not found.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)




@csrf_exempt
def add_feat(request):
    """
    Add a new Feat entry for a specified Part via JSON payload.

    Expects a POST request with a JSON body containing:
      - part_number (str):   The Part’s identifier (HTML-encoded ampersands allowed).
      - name (str):          The name of the new Feat.
      - alarm (any):         The alarm threshold or descriptor for the Feat.
      - critical (bool):     Optional; whether the Feat is critical (defaults to False).

    Workflow:
      1. Parse the JSON payload.
      2. Validate that `part_number` and `name` are provided; return HTTP 400 if missing.
      3. Lookup the Part by `part_number`; return HTTP 404 if not found.
      4. Compute the next display order as (existing feat count + 1).
      5. Create the new Feat with the given fields and computed order.
      6. Return JSON `{"status": "success", "feat_id": <new id>, "new_order": <order>}`.

    Error Handling:
      - JSON decoding errors: HTTP 400 with `{"status":"error","message":"Invalid JSON data."}`.
      - Missing required fields: HTTP 400 with `{"status":"error","message":"Missing required fields."}`.
      - Part not found: HTTP 404 with `{"status":"error","message":"Part not found."}`.
      - Other exceptions: HTTP 500 with `{"status":"error","message":<error>}`.
      - Non-POST requests: HTTP 400 with `{"status":"error","message":"Invalid request method."}`.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, expected to be POST with a JSON body.

    Returns
    -------
    django.http.JsonResponse
        A JSON response indicating success or error with appropriate HTTP status.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            part_number = data.get('part_number', '').replace("&amp;", "&")
            name = data.get('name')
            alarm = data.get('alarm')
            critical = data.get('critical', False)

            if not part_number or not name:
                print(f"ERROR: Missing required fields - part_number: '{part_number}', name: '{name}'")
                return JsonResponse({'status': 'error', 'message': 'Missing required fields.'}, status=400)

            # Retrieve part from the database
            try:
                part = Part.objects.get(part_number=part_number)
            except Part.DoesNotExist:
                print(f"ERROR: Part with part_number '{part_number}' not found.")
                return JsonResponse({'status': 'error', 'message': 'Part not found.'}, status=404)

            # Create the new Feat entry
            new_order = part.feat_set.count() + 1
            feat = Feat.objects.create(
                part=part,
                name=name,
                order=new_order,
                alarm=alarm,
                critical=critical
            )

            return JsonResponse({'status': 'success', 'feat_id': feat.id, 'new_order': new_order})

        except json.JSONDecodeError as e:
            print(f"ERROR: JSON decoding failed - {e}")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)

        except Exception as e:
            print(f"ERROR: Unexpected exception - {e}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)







# =====================================================
# ===================== QA V2 =========================
# =====================================================

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseRedirect
from .models import QualityPDFDocument, ViewingRecord
from .forms import PDFUploadForm
from django.urls import reverse
from plant.models.setupfor_models import Part

def pdf_upload(request):
    """
    Display and process a PDF upload form.

    - GET:
        • Instantiate an empty PDFUploadForm.
        • Render the 'quality/pdf_upload.html' template with `form` context.

    - POST:
        • Bind PDFUploadForm with `request.POST` and `request.FILES`.
        • If valid, save the uploaded PDF (including its `category` field).
        • Redirect to the 'pdf_list' view on success.
        • If invalid, fall through to re-render the form with errors.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, which may carry form data and file uploads.

    Returns
    -------
    django.http.HttpResponse or django.http.HttpResponseRedirect
        - On GET or invalid POST: renders 'quality/pdf_upload.html' with `form`.
        - On successful POST: redirects to the 'pdf_list' page.
    """
    if request.method == 'POST':
        form = PDFUploadForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()  # This will save the PDF document including the 'category' field
            return redirect('pdf_list')
    else:
        form = PDFUploadForm()
    return render(request, 'quality/pdf_upload.html', {'form': form})


@login_required(login_url="login")
def pdf_list(request):
    pdfs = QualityPDFDocument.objects.all()
    return render(request, 'quality/pdf_list.html', {'pdfs': pdfs})


def pdf_edit(request, pdf_id):
    """
    Display and process the PDF edit form for an existing document.

    - GET:
        • Retrieve the QualityPDFDocument by `pdf_id` (404 if not found).
        • Instantiate PDFUploadForm with the existing instance.
        • Render 'quality/pdf_edit.html' with context:
            - `form`: the bound form for editing.
            - `pdf_document`: the document being edited.

    - POST:
        • Bind PDFUploadForm with `request.POST`, `request.FILES`, and the existing instance.
        • If valid, save changes to the document (including file and category).
        • Redirect to the 'pdf_list' view on success.
        • If invalid, re-render the form with validation errors.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, which may be GET or POST with form data and file uploads.
    pdf_id : int
        The primary key of the QualityPDFDocument to edit.

    Returns
    -------
    django.http.HttpResponse or django.http.HttpResponseRedirect
        - On GET or invalid POST: renders 'quality/pdf_edit.html' with `form` and `pdf_document`.
        - On successful POST: redirects to the 'pdf_list' page.
    """
    pdf_document = get_object_or_404(QualityPDFDocument, id=pdf_id)
    
    if request.method == 'POST':
        form = PDFUploadForm(request.POST, request.FILES, instance=pdf_document)
        if form.is_valid():
            form.save()
            return redirect('pdf_list')
    else:
        form = PDFUploadForm(instance=pdf_document)
    
    return render(request, 'quality/pdf_edit.html', {'form': form, 'pdf_document': pdf_document})


def pdf_delete(request, pdf_id):
    """
    Confirm and delete a PDF document from the quality library.

    - GET:
        • Retrieve the QualityPDFDocument by `pdf_id` (404 if not found).
        • Render 'quality/pdf_confirm_delete.html' with context:
            - `pdf_document`: the document pending deletion.

    - POST:
        • Delete the retrieved QualityPDFDocument.
        • Redirect to the 'pdf_list' view on success.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, which may be GET or POST.
    pdf_id : int
        The primary key of the QualityPDFDocument to delete.

    Returns
    -------
    django.http.HttpResponse or django.http.HttpResponseRedirect
        - On GET: renders 'quality/pdf_confirm_delete.html' with `pdf_document`.
        - On POST: redirects to 'pdf_list' after deletion.
    """
    pdf_document = get_object_or_404(QualityPDFDocument, id=pdf_id)
    if request.method == 'POST':
        pdf_document.delete()
        return redirect('pdf_list')
    return render(request, 'quality/pdf_confirm_delete.html', {'pdf_document': pdf_document})


# =========================================
# ======== Clock number pdf check =========
# =========================================

from django.utils.html import linebreaks

def pdf_part_clock_form(request):
    """
    Display and process the part-clock PDF selection form.

    - GET:
        • Retrieve all Part instances.
        • If `part_number` is provided as a query parameter:
            - Fetch the corresponding Part (404 if not found).
            - Load its custom message and font size from PartMessage,
              converting newlines to HTML line breaks.
            - If no PartMessage exists, provide a default notice.
        • Render 'quality/pdf_part_clock_form.html' with context:
            - `parts`: QuerySet of all Part objects.
            - `selected_part`: the part_number string (or None).
            - `part_message`: HTML-safe message for display.
            - `font_size`: the chosen font size for the message.

    - POST:
        • Read `selected_part` and the list `clock_numbers[]` from form data.
        • If both are present and non-empty, redirect to the `pdfs_to_view`
          view, passing `part_number` and a comma-separated `clock_numbers`.

    Debug:
      • Prints selected part and submitted clock numbers for troubleshooting.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, which may be GET or POST.
        - GET may include `part_number` in query parameters.
        - POST includes `selected_part` and `clock_numbers[]`.

    Returns
    -------
    django.http.HttpResponse or django.http.HttpResponseRedirect
        - On GET or incomplete POST: renders the form template with context.
        - On valid POST: redirects to 'pdfs_to_view' with appropriate args.
    """
    # Get the part_number from query parameters
    part_number = request.GET.get('part_number', None)
    parts = Part.objects.all()
    part_message = None
    font_size = 'medium'  # Default font size

    if part_number:
        # Retrieve the selected part
        selected_part = get_object_or_404(Part, part_number=part_number)
        
        # Debug output: Selected part
        print(f"Selected part: {selected_part.part_number}")

        # Retrieve the custom message for the selected part
        try:
            part_message = selected_part.custom_message.message
            font_size = selected_part.custom_message.font_size
            # Convert newlines to HTML line breaks
            part_message = linebreaks(part_message)

            # Debug output: Message and font size
            print(f"Retrieved PartMessage: message='{part_message}', font_size='{font_size}'")
        except PartMessage.DoesNotExist:
            part_message = "No message available for this part."
            print("No PartMessage found for the selected part.")
    else:
        selected_part = None

    # Pass the part and its message to the context
    context = {
        'parts': parts,
        'selected_part': part_number,
        'part_message': part_message,
        'font_size': font_size,
    }

    if request.method == 'POST':
        selected_part = request.POST.get('selected_part')
        clock_numbers = request.POST.getlist('clock_numbers[]')  # Get all clock numbers as a list

        if selected_part and clock_numbers:
            # Redirect to the pdfs_to_view view with the clock numbers
            clock_numbers_list = [num.strip() for num in clock_numbers if num.strip()]
            print(f"Submitted clock_numbers: {clock_numbers_list}")
            return redirect('pdfs_to_view', part_number=selected_part, clock_numbers=','.join(clock_numbers_list))

    return render(request, 'quality/pdf_part_clock_form.html', context)





def pdfs_to_view(request, part_number, clock_numbers):
    """
    Display PDFs for a given part that have not yet been viewed by specified operators.

    - Retrieves the Part identified by `part_number` (404 if not found).
    - Parses `clock_numbers`, a comma-separated string of operator clock numbers, into a list.
    - For each clock number:
        • Fetches all PDF documents linked to the Part (`part.pdf_documents.all()`).
        • Retrieves ViewingRecord entries for that operator_number.
        • Excludes already-viewed PDFs to build a queryset of unviewed PDFs.
    - Constructs `clock_pdf_status`, a dict mapping each clock number to its unviewed PDFs.
    - Renders 'quality/pdfs_to_view.html' with context:
        - `part`: the Part instance.
        - `clock_pdf_status`: dict of clock_number → QuerySet of unviewed PDFs.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request.
    part_number : str
        The identifier of the Part whose PDFs are to be displayed.
    clock_numbers : str
        A comma-separated string of operator clock numbers (e.g., "123,456,789").

    Returns
    -------
    django.http.HttpResponse
        The rendered template showing, for each clock number, the PDFs not yet viewed.
    """
    part = get_object_or_404(Part, part_number=part_number)
    
    # Split the clock_numbers string into a list
    clock_numbers_list = [num.strip() for num in clock_numbers.split(',') if num.strip()]
    
    # Initialize a dictionary to store not viewed PDFs for each clock number
    clock_pdf_status = {}

    for clock_number in clock_numbers_list:
        # Get all PDFs associated with this part
        associated_pdfs = part.pdf_documents.all()

        # Get the viewing records for this user (by clock number)
        viewed_pdfs = ViewingRecord.objects.filter(operator_number=clock_number).values_list('pdf_document_id', flat=True)

        # Filter PDFs that the user has not viewed yet
        not_viewed_pdfs = associated_pdfs.exclude(id__in=viewed_pdfs)

        # Add the not viewed PDFs to the dictionary with the clock number as the key
        clock_pdf_status[clock_number] = not_viewed_pdfs

    return render(request, 'quality/pdfs_to_view.html', {
        'part': part,
        'clock_pdf_status': clock_pdf_status,  # Pass the dictionary of clock numbers and their unviewed PDFs
    })




def mark_pdf_as_viewed(request, pdf_id, clock_number):
    """
    Record that a user (identified by clock_number) has viewed a PDF and redirect back to the review list.

    Expects:
      - `pdf_id` (int):       The primary key of the QualityPDFDocument to mark as viewed.
      - `clock_number` (str): The operator’s clock number performing the view action.
      - Optional GET parameters:
          • `part_number` (str): Comma-separated Part identifier to maintain context.
          • `clock_numbers` (str): Comma-separated list of all clock numbers in the session.

    Workflow:
      1. Retrieve the QualityPDFDocument by `pdf_id` or return 404.
      2. Create a new ViewingRecord linking `operator_number` and the PDF.
      3. Determine `part_number` from GET or fall back to the document’s first associated part.
      4. Determine the full `clock_numbers` list from GET or default to the current `clock_number`.
      5. Redirect to `pdfs_to_view` with `part_number` and `clock_numbers` to continue the review process.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request.
    pdf_id : int
        ID of the PDF document being marked viewed.
    clock_number : str
        Operator’s clock number.

    Returns
    -------
    django.http.HttpResponseRedirect
        Redirects to the `pdfs_to_view` view with the appropriate query parameters.
    """
    pdf_document = get_object_or_404(QualityPDFDocument, id=pdf_id)

    # Create a new ViewingRecord for the user (clock_number)
    ViewingRecord.objects.create(
        operator_number=clock_number,
        pdf_document=pdf_document
    )

    # Fetch the part number from the GET parameter
    part_number = request.GET.get('part_number')

    if not part_number:
        # Fall back to the first associated part if not provided
        part_number = pdf_document.associated_parts.first().part_number

    # Retrieve the full list of clock numbers from the GET parameter, falling back to the current clock number if necessary
    clock_numbers = request.GET.get('clock_numbers', clock_number)  # Comma-separated list of all clock numbers

    # Redirect back to the PDFs to view page with all clock numbers included in the URL
    return redirect('pdfs_to_view', part_number=part_number, clock_numbers=clock_numbers)



def change_part(request):
    """
    Render a part‐selection page or redirect to the part‐clock PDF form.

    - GET:
        • Retrieve all Part instances.
        • Render 'quality/change_part.html' with context:
            - `parts`: QuerySet of all Part objects.

    - POST:
        • Read `selected_part` from form data.
        • If a part is selected, redirect to the `pdf_part_clock_form` view
          (URL: '/quality/pdf/part_clock/?part_number=<selected_part>').
        • If no part is selected, log a warning and re-render the selection page.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, which may be GET or POST with form data.

    Returns
    -------
    django.http.HttpResponse or django.http.HttpResponseRedirect
        - On GET or invalid POST: renders 'quality/change_part.html' with `parts`.
        - On valid POST with `selected_part`: redirects to the part‐clock form.
    """
    if request.method == 'POST':

        # Capture the selected part from the form
        selected_part = request.POST.get('selected_part')



        if selected_part:
            return redirect(f'/quality/pdf/part_clock/?part_number={selected_part}')
        else:
            print("No part was selected.")
    else:

        # If it's a GET request, just render the part selection page
        parts = Part.objects.all()
    return render(request, 'quality/change_part.html', {'parts': parts})




# =====================================================
# ================ View Live PDFs Page ================
# =====================================================

from django.shortcuts import render, get_object_or_404
from .models import QualityPDFDocument

def pdfs_by_part_number(request, part_number):
    """
    Display all PDF documents for a specific part, grouped by category.

    Retrieves the Part identified by `part_number` (404 if not found),
    fetches all related QualityPDFDocument instances, and organizes them
    into a list of tuples where each tuple contains:
      - category display name (str)
      - QuerySet of PDFs in that category

    Renders 'quality/pdfs_by_part_number.html' with context:
      - `part`: the Part instance
      - `pdfs_by_category`: list of (category_display, pdfs_in_category)

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request.
    part_number : str
        The identifier of the Part whose PDFs are to be displayed.

    Returns
    -------
    django.http.HttpResponse
        The rendered HTML page showing PDFs grouped by category.
    """
    part = get_object_or_404(Part, part_number=part_number)
    pdfs = part.pdf_documents.all()

    # Build a list of tuples: (category_display_name, pdfs_in_category)
    pdfs_by_category = []
    for code, display in QualityPDFDocument.CATEGORY_CHOICES:
        pdfs_in_category = pdfs.filter(category=code)
        pdfs_by_category.append((display, pdfs_in_category))

    return render(request, 'quality/pdfs_by_part_number.html', {
        'part': part,
        'pdfs_by_category': pdfs_by_category,
    })




# =====================================================
# =====================================================
# ================= Red Rabbits =======================
# =====================================================
# =====================================================

from django.shortcuts import render, get_object_or_404, redirect
from .models import Part, RedRabbitsEntry, RedRabbitType
from django.utils.timezone import now

def red_rabbits_form(request, part_number):
    """
    Display and process the Red Rabbits inspection form for a specific part.

    - GET:
        • Retrieve the Part by `part_number` (404 if not found).
        • Fetch all RedRabbitType instances linked to that Part.
        • Provide today’s date (YYYY-MM-DD) as `today` for default form values.
        • Render 'quality/red_rabbits_form.html' with context:
            - `part`: the Part instance
            - `red_rabbit_types`: QuerySet of relevant RedRabbitType objects
            - `today`: string of today's date

    - POST:
        • Read shared fields: `date`, `clock_number`, and `shift`; return errors if any are missing.
        • For each RedRabbitType:
            – Read `verification_okay_<id>` (yes/no), `supervisor_comments_<id>`, and `supervisor_id_<id>`.
            – If verification is “No”, require both comments and supervisor ID; collect errors otherwise.
            – Build a RedRabbitsEntry instance for each type when valid.
        • If any validation errors occur, re-render form with combined `error_message`.
        • On successful validation, bulk-create all RedRabbitsEntry objects and redirect to `final_inspection` for this part.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request; GET to display, POST to submit form data.
    part_number : str
        The identifier of the Part under inspection.

    Returns
    -------
    django.http.HttpResponse or django.http.HttpResponseRedirect
        - On GET or validation failure: renders 'quality/red_rabbits_form.html' with context.
        - On successful POST: redirects to the `final_inspection` view for the same part.
    """
    # Fetch the specific part using part_number
    part = get_object_or_404(Part, part_number=part_number)
    # Get only the Red Rabbit Types associated with this part
    red_rabbit_types = RedRabbitType.objects.filter(part=part)
    # Today's date
    today = now().strftime('%Y-%m-%d')

    if request.method == 'POST':
        # Shared fields
        date = request.POST.get('date')
        clock_number = request.POST.get('clock_number')
        shift = request.POST.get('shift')

        # Validate shared fields
        if not date or not clock_number or not shift:
            return render(request, 'quality/red_rabbits_form.html', {
                'part': part,
                'red_rabbit_types': red_rabbit_types,
                'today': today,
                'error_message': 'Date, Clock Number, and Shift are required.',
            })

        entries = []
        errors = []

        # Process entries for each Red Rabbit Type
        for rabbit_type in red_rabbit_types:
            verification_okay = request.POST.get(f'verification_okay_{rabbit_type.id}') == 'yes'
            supervisor_comments = request.POST.get(f'supervisor_comments_{rabbit_type.id}')
            supervisor_id = request.POST.get(f'supervisor_id_{rabbit_type.id}')

            # Validate fields for each Red Rabbit Type
            if not verification_okay and (not supervisor_comments or not supervisor_id):
                errors.append(f'Supervisor Comments and ID are required for {rabbit_type.name} if Verification is "No".')

            # If no errors, prepare the entry
            if not errors:
                entries.append(RedRabbitsEntry(
                    part=part,
                    red_rabbit_type=rabbit_type,
                    date=date,
                    clock_number=clock_number,
                    shift=int(shift),
                    verification_okay=verification_okay,
                    supervisor_comments=supervisor_comments if not verification_okay else None,
                    supervisor_id=supervisor_id if not verification_okay else None
                ))

        # If there are validation errors, show them
        if errors:
            return render(request, 'quality/red_rabbits_form.html', {
                'part': part,
                'red_rabbit_types': red_rabbit_types,
                'today': today,
                'error_message': ' '.join(errors),
            })

        # Save all entries in bulk if no errors
        RedRabbitsEntry.objects.bulk_create(entries)

        return redirect('final_inspection', part_number=part_number)

    return render(request, 'quality/red_rabbits_form.html', {
        'part': part,
        'red_rabbit_types': red_rabbit_types,
        'today': today,
    })



from django.shortcuts import render, get_object_or_404, redirect
from .models import RedRabbitType
from .forms import RedRabbitTypeForm
from plant.models.setupfor_models import Part

@login_required(login_url="login")
def manage_red_rabbit_types(request):
    """
    List, add, edit, and delete RedRabbitType entries for HR managers.

    Access Control
    --------------
    Requires authentication; unauthenticated users are redirected to the "login" page.

    Behavior
    --------
    - GET:
        • Fetch all Part instances for the part-selection dropdown.
        • Retrieve all RedRabbitType records (with related Part) to display.
        • Instantiate an empty `add_form` (RedRabbitTypeForm).
        • No `edit_form` unless triggered by POST.

    - POST with `action == 'add'`:
        • Bind `add_form` to submitted data.
        • If valid, save a new RedRabbitType and redirect back to this view.
        • Otherwise, fall through to re-render with validation errors.

    - POST with `action == 'edit'`:
        • Retrieve the target RedRabbitType via `edit_id`; 404 if not found.
        • Bind `edit_form` to submitted data and instance.
        • If valid, save updates and redirect back to this view.
        • Otherwise, re-render with both `add_form` and the invalid `edit_form`.

    - POST with `action == 'delete'`:
        • Retrieve the RedRabbitType via `delete_id`; 404 if not found.
        • Delete the record and redirect back to this view.

    Context
    -------
    Renders 'quality/manage_red_rabbit_types.html' with:
      - `rabbit_types`: QuerySet of all RedRabbitType objects (with Part).
      - `parts`: QuerySet of all Part objects for dropdowns.
      - `add_form`: instance of RedRabbitTypeForm for creating new entries.
      - `edit_form`: instance of RedRabbitTypeForm for editing (or None).

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, supporting GET and POST with form actions.

    Returns
    -------
    django.http.HttpResponse or django.http.HttpResponseRedirect
        - On GET or form validation failure: renders the management template.
        - On successful add/edit/delete: redirects to the same management view.
    """
    # Fetch all parts to populate the dropdown
    parts = Part.objects.all()

    # Handle adding a new Red Rabbit Type
    if request.method == 'POST' and request.POST.get('action') == 'add':
        add_form = RedRabbitTypeForm(request.POST)
        if add_form.is_valid():
            add_form.save()
            return redirect('manage_red_rabbit_types')
    else:
        add_form = RedRabbitTypeForm()

    # Handle editing an existing Red Rabbit Type
    if request.method == 'POST' and request.POST.get('action') == 'edit':
        edit_id = request.POST.get('edit_id')
        rabbit_type = get_object_or_404(RedRabbitType, pk=edit_id)
        edit_form = RedRabbitTypeForm(request.POST, instance=rabbit_type)
        if edit_form.is_valid():
            edit_form.save()
            return redirect('manage_red_rabbit_types')
    else:
        edit_form = None

    # Handle deleting a Red Rabbit Type
    if request.method == 'POST' and request.POST.get('action') == 'delete':
        delete_id = request.POST.get('delete_id')
        rabbit_type = get_object_or_404(RedRabbitType, pk=delete_id)
        rabbit_type.delete()
        return redirect('manage_red_rabbit_types')

    # Retrieve all Red Rabbit Types
    rabbit_types = RedRabbitType.objects.select_related('part').all()

    return render(request, 'quality/manage_red_rabbit_types.html', {
        'rabbit_types': rabbit_types,
        'parts': parts,  # Include parts in the context
        'add_form': add_form,
        'edit_form': edit_form,
    })


# =============================================================================
# =============================================================================
# ========================== EPV Interface ====================================
# =============================================================================
# =============================================================================


import mysql.connector
from mysql.connector import Error
from django.shortcuts import render
from django.http import JsonResponse


def get_creds():
    """
    Load DAVE_* database credentials from the Django settings module and return a MySQL connection.

    This function locates the `settings.py` file in the sibling `pms` package directory,
    dynamically imports it, and reads the attributes `DAVE_HOST`, `DAVE_USER`,
    `DAVE_PASSWORD`, and `DAVE_DB`. If all credentials are found, it attempts to
    establish and return a `mysql.connector` connection to the specified database.
    On any failure (missing file, missing attributes, or connection error), it logs
    a message and returns `None`.

    Returns
    -------
    mysql.connector.MySQLConnection or None
        A live MySQL connection if successful; otherwise `None`.

    Notes
    -----
    - Expects `settings.py` at `../pms/settings.py` relative to this script.
    - Credentials must be defined as module-level variables named:
      `DAVE_HOST`, `DAVE_USER`, `DAVE_PASSWORD`, and `DAVE_DB`.
    - Uses dynamic import via `importlib.util`.
    - Errors are printed to stdout; no exceptions are propagated.
    """
    """
    Dynamically loads database credentials (DAVE_*) from settings.py and returns a MySQL connection object.
    """
    # Find the directory of this script
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Construct the path to settings.py
    settings_path = os.path.join(current_dir, '..', 'pms', 'settings.py')

    if not os.path.exists(settings_path):
        print(f"settings.py not found at: {settings_path}")
        return None

    # Dynamically import settings.py
    spec = importlib.util.spec_from_file_location("settings", settings_path)
    settings = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(settings)

    # Extract the database credentials
    dave_host = getattr(settings, "DAVE_HOST", None)
    dave_user = getattr(settings, "DAVE_USER", None)
    dave_password = getattr(settings, "DAVE_PASSWORD", None)
    dave_db = getattr(settings, "DAVE_DB", None)

    # Validate that all credentials are present
    if not all([dave_host, dave_user, dave_password, dave_db]):
        # print("Missing database credentials in settings.py")
        return None

    try:
        # Return a MySQL connection object
        connection = mysql.connector.connect(
            host=dave_host,
            user=dave_user,
            password=dave_password,
            database=dave_db
        )
        # print("Successfully connected to the database")
        return connection

    except Error as e:
        print(f"❌ Database connection error: {e}")
        return None



def remove_zeros(asset_value):
    """
    Removes trailing ".0" from asset values if they exist.
    """
    if isinstance(asset_value, str) and asset_value.endswith(".0"):
        return asset_value[:-2]  # Strip the last two characters (".0")
    return asset_value


# Function to fetch all table data
def get_all_data():
    """
    Retrieve all records from the `quality_epv_assets` table as dictionaries.

    Establishes a MySQL connection via `get_creds()`, then executes a SELECT query
    to fetch the columns `id, QC1, OP1, Check1, Desc1, Method1, Interval1, Person, Asset`.
    Each row is returned as a dict (`cursor(dictionary=True)`), and the `Asset` value
    is post-processed by `remove_zeros()` to strip any trailing “.0” suffix.

    Error Handling
    --------------
    - If the connection cannot be established or the query fails, logs the error
      to stdout and returns an empty list.
    - Ensures that the database cursor and connection are closed in all cases.

    Returns
    -------
    list of dict
        A list of row dictionaries with keys matching the selected columns. Returns
        an empty list if a database error occurs or if `get_creds()` fails.
    """
    try:
        connection = get_creds()
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT id, QC1, OP1, Check1, Desc1, Method1, Interval1, Person, Asset 
                FROM quality_epv_assets
            """
            cursor.execute(query)
            data = cursor.fetchall()

            # Process assets to remove trailing ".0"
            for row in data:
                row["Asset"] = remove_zeros(row["Asset"])

            return data
    except Error as e:
        print(f"Database error: {e}")
        return []
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()




# View to return all data to frontend
@login_required(login_url='/login/')
def epv_table_view(request):
    # Check if the user is in the 'quality_manager' group.
    if not request.user.groups.filter(name='quality_manager').exists():
        return HttpResponseForbidden("Only EPV admins are authorized to access this page. If you require access, please request an admin to add you to Quality_Managers group")
    
    # Call get_creds to verify the settings.py file can be found.
    settings_file = get_creds()
    # if settings_file:
    #     # print(f"Using settings.py at: {settings_file}")
    # else:
    #     print("Could not locate settings.py.")

    table_data = get_all_data()
    return render(request, 'quality/epv_interface.html', {'table_data': table_data})



# API to return all data in JSON
def fetch_all_data(request):
    return JsonResponse({'table_data': get_all_data()}, safe=False)



from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

# Function to delete an EPV entry
@csrf_exempt
def delete_epv(request):
    """
    Delete an EPV asset record by ID via a JSON POST request.

    Expects a POST request with a JSON body containing:
      - id (int): The primary key of the `quality_epv_assets` record to delete.

    Workflow:
      1. Parse and validate the JSON payload; return HTTP 400 if missing or invalid.
      2. Establish a MySQL connection via `get_creds()`; return HTTP 500 on connection error.
      3. Execute a DELETE statement on `quality_epv_assets` for the given `id`.
      4. Commit the transaction and close the connection.
      5. Return HTTP 200 with `{"message": "EPV deleted successfully"}` on success.

    Error Handling:
      - Missing `id` in payload: HTTP 400 with `{"error": "Missing ID"}`.
      - JSON decode error: HTTP 400 with `{"error": "Invalid JSON"}`.
      - Database errors: HTTP 500 with `{"error": "Database error: <details>"}`.
      - Non-POST requests: HTTP 405 with `{"error": "Invalid request method"}`.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, expected to be a POST with JSON body.

    Returns
    -------
    django.http.JsonResponse
        A JSON response indicating success or the type of error, with appropriate HTTP status.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            epv_id = data.get("id")

            if not epv_id:
                return JsonResponse({"error": "Missing ID"}, status=400)

            connection = get_creds()
            if connection.is_connected():
                cursor = connection.cursor()
                delete_query = "DELETE FROM quality_epv_assets WHERE id = %s"
                cursor.execute(delete_query, (epv_id,))
                connection.commit()
                cursor.close()
                connection.close()
                return JsonResponse({"message": "EPV deleted successfully"}, status=200)

        except Error as e:
            return JsonResponse({"error": f"Database error: {e}"}, status=500)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

    return JsonResponse({"error": "Invalid request method"}, status=405)



@csrf_exempt
def update_asset(request):
    """
    Update the Asset field of an EPV record via JSON POST.

    Expects a POST request with a JSON body containing:
      - id (int):    The primary key of the `quality_epv_assets` record to update.
      - asset (str): The new asset value (without trailing “.0”).

    Workflow:
      1. Parse and validate the JSON payload; return HTTP 400 if `id` or `asset` is missing.
      2. Append “.0” to the provided `asset` value.
      3. Establish a MySQL connection via `get_creds()`; return HTTP 500 on connection error.
      4. Execute an UPDATE statement on `quality_epv_assets` to set `Asset = %s` for the given `id`.
      5. Commit the transaction and close the connection.
      6. Return HTTP 200 with `{"message": "Asset updated successfully"}` on success.

    Error Handling:
      - Missing `id` or `asset`: HTTP 400 with `{"error": "Missing ID or Asset"}`.
      - JSON decode error: HTTP 400 with `{"error": "Invalid JSON"}`.
      - Database errors: HTTP 500 with `{"error": "Database error: <details>"}`.
      - Non-POST requests: HTTP 405 with `{"error": "Invalid request method"}`.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, expected to be POST with a JSON body.

    Returns
    -------
    django.http.JsonResponse
        A JSON response indicating success or error with an appropriate HTTP status.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            epv_id = data.get("id")
            new_asset = data.get("asset")

            if not epv_id or not new_asset:
                return JsonResponse({"error": "Missing ID or Asset"}, status=400)

            # Append .0 to the asset value
            new_asset = add_zeros(new_asset)

            connection = get_creds()
            if connection.is_connected():
                cursor = connection.cursor()
                update_query = "UPDATE quality_epv_assets SET Asset = %s WHERE id = %s"
                cursor.execute(update_query, (new_asset, epv_id))
                connection.commit()
                cursor.close()
                connection.close()
                return JsonResponse({"message": "Asset updated successfully"}, status=200)

        except Error as e:
            return JsonResponse({"error": f"Database error: {e}"}, status=500)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

    return JsonResponse({"error": "Invalid request method"}, status=405)

def add_zeros(asset_value):
    """
    Ensures that asset values always end with ".0".
    """
    if isinstance(asset_value, str) and not asset_value.endswith(".0"):
        return asset_value + ".0"
    return asset_value




def fetch_related_persons(epv_id, new_person):
    """
    Update the `Person` field for all EPV asset records sharing the same QC1 value.

    This function:
      1. Connects to the MySQL database using `get_creds()`.
      2. Retrieves the `QC1` value for the record with the given `epv_id`.
      3. Queries all rows in `quality_epv_assets` having that same `QC1`.
      4. Prints each matching record’s ID and old Person value, and the intended new value.
      5. Executes a bulk UPDATE to set `Person = new_person` for all those rows.
      6. Commits the transaction and closes the connection.

    Parameters
    ----------
    epv_id : int
        The primary key of the `quality_epv_assets` record whose `QC1` will be used as the grouping key.
    new_person : str
        The new name to assign to the `Person` field on all related records.

    Returns
    -------
    None

    Notes
    -----
    - Logs progress and errors via `print()`.
    - If no record is found for `epv_id`, the function prints a message and returns without error.
    - Database errors are caught and printed; no exception is propagated.
    """
    try:
        connection = get_creds()
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)

            # Step 1: Get the QC1 value for the given ID
            cursor.execute("SELECT QC1 FROM quality_epv_assets WHERE id = %s", (epv_id,))
            result = cursor.fetchone()

            if not result:
                print(f"No entry found for ID: {epv_id}")
                return

            qc1_value = result["QC1"]
            print(f"QC1 for ID {epv_id}: {qc1_value}")

            # Step 2: Find all entries with the same QC1
            cursor.execute("SELECT id, Person FROM quality_epv_assets WHERE QC1 = %s", (qc1_value,))
            related_entries = cursor.fetchall()

            print("Updating the following entries with new Person name:")
            for entry in related_entries:
                print(f"ID: {entry['id']}, Old Person: {entry['Person']} → New Person: {new_person}")

            # Step 3: Update the Person field for all related entries
            cursor.execute("UPDATE quality_epv_assets SET Person = %s WHERE QC1 = %s", (new_person, qc1_value))
            connection.commit()

            print("Person field updated successfully for all related entries.")

    except Error as e:
        print(f"Database error: {e}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()





@csrf_exempt
def update_person(request):
    """
    Update the `Person` field for all EPV asset records sharing the same QC1 value, based on a JSON POST.

    Expects a POST request with a JSON body containing:
      - id (int):     The primary key of the `quality_epv_assets` record whose QC1 will be used.
      - person (str): The new Person name to apply to all records with that QC1.

    Workflow:
      1. Parse and validate the JSON payload; return HTTP 400 if `id` or `person` is missing or JSON is invalid.
      2. Log the incoming `epv_id` and `new_person` for debugging.
      3. Invoke `fetch_related_persons(epv_id, new_person)` to:
         • Retrieve the QC1 value for `epv_id`.
         • Find all rows with that QC1.
         • Bulk-update their `Person` field.
      4. Return HTTP 200 with a success message.

    Error Handling:
      - Missing or empty `id`/`person`: HTTP 400 with `{"error": "Missing ID or Person"}`.
      - Malformed JSON: HTTP 400 with `{"error": "Invalid JSON"}`.
      - Non-POST requests: HTTP 405 with `{"error": "Invalid request method"}`.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, expected to be a POST with a JSON payload.

    Returns
    -------
    django.http.JsonResponse
        A JSON response indicating success or error, with the appropriate HTTP status code.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            epv_id = data.get("id")
            new_person = data.get("person")

            if not epv_id or not new_person:
                return JsonResponse({"error": "Missing ID or Person"}, status=400)

            print(f"EPV ID: {epv_id}, New Person: {new_person}")

            # Call the function to update related persons
            fetch_related_persons(epv_id, new_person)

            return JsonResponse({"message": "Person updated for all related entries"}, status=200)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

    return JsonResponse({"error": "Invalid request method"}, status=405)



def add_new_entry_with_asset(epv_id, new_asset):
    """
    Duplicate an existing EPV asset record with a new Asset value.

    Connects to the database via `get_creds()`, retrieves the row from
    `quality_epv_assets` identified by `epv_id`, and inserts a new record
    copying all fields except `Asset`, which is set to `new_asset` (with
    “.0” appended). Returns the newly inserted row as a dict with trailing
    “.0” stripped from its `Asset` value.

    Parameters
    ----------
    epv_id : int
        The primary key of the existing `quality_epv_assets` record to duplicate.
    new_asset : str
        The new Asset value (without “.0”); “.0” will be appended internally.

    Returns
    -------
    dict or None
        A dictionary representing the newly inserted row, with keys:
        `id, QC1, OP1, Check1, Desc1, Method1, Interval1, Person, Asset`.
        The returned `Asset` string will have any trailing “.0” removed.
        Returns `None` if the original row is not found or on database error.

    Notes
    -----
    - Uses `add_zeros()` to append “.0” to the provided `new_asset` string.
    - Commits the insert before fetching and returning the new record.
    - Errors are logged via `print()`; no exceptions are propagated.
    """
    try:
        connection = get_creds()
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)

            # Retrieve the original row's data
            cursor.execute("""
                SELECT QC1, OP1, Check1, Desc1, Method1, Interval1, Person 
                FROM quality_epv_assets 
                WHERE id = %s
            """, (epv_id,))
            original_row = cursor.fetchone()

            if not original_row:
                print(f"No entry found for ID: {epv_id}")
                return None

            # Ensure the new asset value has ".0" appended
            new_asset = add_zeros(new_asset)

            # Insert a new row with the copied data and the new asset
            insert_query = """
                INSERT INTO quality_epv_assets (QC1, OP1, Check1, Desc1, Method1, Interval1, Person, Asset)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (
                original_row["QC1"], original_row["OP1"], original_row["Check1"],
                original_row["Desc1"], original_row["Method1"], original_row["Interval1"],
                original_row["Person"], new_asset
            ))
            connection.commit()

            new_entry_id = cursor.lastrowid  # Get the ID of the inserted row
            print(f"New entry added with ID: {new_entry_id}")

            # Fetch the newly inserted row
            cursor.execute("""
                SELECT id, QC1, OP1, Check1, Desc1, Method1, Interval1, Person, Asset 
                FROM quality_epv_assets 
                WHERE id = %s
            """, (new_entry_id,))
            new_entry = cursor.fetchone()

            # Remove trailing ".0" before sending data to frontend
            if new_entry:
                new_entry["Asset"] = remove_zeros(new_entry["Asset"])

            return new_entry

    except Error as e:
        print(f"Database error: {e}")
        return None
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()







@csrf_exempt
def send_qc1_asset(request):
    """
    Handle JSON-based requests to duplicate an EPV record with a new Asset value.

    Expects a POST request with a JSON body containing:
      - id (int):     The primary key of the existing `quality_epv_assets` record.
      - asset (str):  The new Asset value (without trailing “.0”).

    Workflow:
      1. Parse and validate the JSON payload; return HTTP 400 if `id` or `asset` is missing or JSON is invalid.
      2. Log the incoming `epv_id` and `new_asset` for debugging.
      3. Invoke `add_new_entry_with_asset(epv_id, new_asset)` to:
         • Retrieve the original row’s data.
         • Append “.0” to the provided asset.
         • Insert a new record copying all other fields.
      4. If insertion succeeds, return HTTP 200 with:
         `{"message": "New entry added", "new_entry": <dict>}`.
      5. If insertion fails, return HTTP 500 with `{"error": "Failed to add new entry"}`.
      6. Non-POST requests return HTTP 405 with `{"error": "Invalid request method"}`.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, expected to be POST with a JSON payload.

    Returns
    -------
    django.http.JsonResponse
        A JSON response indicating success or error, with an appropriate HTTP status code.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            epv_id = data.get("id")
            new_asset = data.get("asset")

            if not epv_id or not new_asset:
                return JsonResponse({"error": "Missing ID or Asset"}, status=400)

            print(f"Received QC1 ID: {epv_id}, New Asset: {new_asset}")  # Print to console

            # Call function to insert new entry
            new_entry = add_new_entry_with_asset(epv_id, new_asset)

            if new_entry:
                return JsonResponse({"message": "New entry added", "new_entry": new_entry}, status=200)
            else:
                return JsonResponse({"error": "Failed to add new entry"}, status=500)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

    return JsonResponse({"error": "Invalid request method"}, status=405)





@csrf_exempt
def edit_column(request, column_name):
    """
    Update a specified column for all EPV asset records sharing the same QC1 value via JSON POST.

    Expects a POST request with a JSON body containing:
      - id (int):        The primary key of the `quality_epv_assets` record whose QC1 is used for grouping.
      - old_value (str): The original value in the specified column (for logging/validation).
      - new_value (str): The new value to set in the specified column.

    Workflow:
      1. Parse and validate the JSON payload; return HTTP 400 if any required field is missing or JSON is invalid.
      2. Log the action, including `epv_id`, `column_name`, `old_value`, and `new_value`.
      3. Invoke `edit_related_column_by_qc1(epv_id, column_name, new_value)` to:
         • Retrieve the QC1 value for `epv_id`.
         • Find all rows in `quality_epv_assets` with that QC1.
         • Bulk-update the specified column to `new_value`.
         • Return a list of IDs that were updated.
      4. Return HTTP 200 with a message indicating success and the list of updated record IDs.
      5. Non-POST requests return HTTP 405 with `{"error": "Invalid request method"}`.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, expected to be POST with a JSON body.
    column_name : str
        The name of the column in `quality_epv_assets` to update.

    Returns
    -------
    django.http.JsonResponse
        - On success: `{"message": "<column_name> updated for all related entries", "updated_ids": [<ids>]}` (HTTP 200).
        - On missing data or invalid JSON: `{"error": "Missing data"}` or `{"error": "Invalid JSON"}` (HTTP 400).
        - On invalid method: `{"error": "Invalid request method"}` (HTTP 405).
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            epv_id = data.get("id")
            old_value = data.get("old_value")
            new_value = data.get("new_value")

            if not epv_id or not old_value or not new_value:
                return JsonResponse({"error": "Missing data"}, status=400)

            print(f"EPV ID: {epv_id}, Column: {column_name}, Old Value: {old_value}, New Value: {new_value}")

            # Call function to update related column values
            updated_ids = edit_related_column_by_qc1(epv_id, column_name, new_value)

            return JsonResponse({"message": f"{column_name} updated for all related entries", "updated_ids": updated_ids}, status=200)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

    return JsonResponse({"error": "Invalid request method"}, status=405)



def edit_related_column_by_qc1(epv_id, column_name, new_value):
    """
    Update a specified column for all rows sharing the same QC1 group as a given record.

    This function:
      1. Connects to the database using `get_creds()`.
      2. Retrieves the `QC1` value for the row with primary key `epv_id`.
      3. Executes an UPDATE statement setting `column_name = new_value`
         for every row in `quality_epv_assets` with that same `QC1`.
      4. Commits the transaction and returns a list containing the
         original `epv_id` on success.
      5. Returns an empty list if the initial row is not found or if any
         database error occurs.

    Parameters
    ----------
    epv_id : int
        The primary key of the reference record whose QC1 value determines
        the group to update.
    column_name : str
        The name of the column to update (must match a valid column in
        `quality_epv_assets`).
    new_value : Any
        The new value to assign to `column_name` for all matching rows.

    Returns
    -------
    list[int]
        A single-element list `[epv_id]` if the update succeeded, or an
        empty list if no matching record was found or an error occurred.

    Notes
    -----
    - Relies on `get_creds()` to supply a valid, open database connection.
    - Uses a raw SQL query; ensure `column_name` is trusted or validated
      to avoid SQL injection risks.
    """
    try:
        connection = get_creds()
        if connection.is_connected():
            cursor = connection.cursor()

            # Get QC1 value
            cursor.execute("SELECT QC1 FROM quality_epv_assets WHERE id = %s", (epv_id,))
            result = cursor.fetchone()

            if not result:
                return []

            qc1_value = result[0]

            # Update column for all matching QC1 values
            query = f"UPDATE quality_epv_assets SET {column_name} = %s WHERE QC1 = %s"
            cursor.execute(query, (new_value, qc1_value))
            connection.commit()

            return [epv_id]

    except Exception as e:
        print(f"Database error: {e}")
        return []
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()




@csrf_exempt
def add_new_epv(request):
    """
    Create a new EPV asset record from a JSON payload.

    This view only accepts POST requests with a JSON body containing the fields:
      - qc1 (str|int):       QC1 grouping value.
      - op1 (str):           First operation identifier.
      - check1 (str):        First check description.
      - desc1 (str):         First description text.
      - method1 (str):       First method specification.
      - interval1 (str|int): Interval for the check.
      - person (str):        Responsible person’s name.
      - asset (str|int):     Asset identifier (will be zero-padded).

    Workflow:
      1. Parse and validate the JSON payload.
      2. Zero-pad the `asset` value via `add_zeros()`.
      3. Connect to the database and insert a new row into `quality_epv_assets`.
      4. Commit the transaction and fetch the newly inserted row.
      5. Remove any trailing “.0” from the Asset value via `remove_zeros()`.
      6. Return a JSON response with:
         - `message`: Success confirmation.
         - `new_entry`: Dict of the inserted record.
         - HTTP status 201.

    Error Handling:
      - If the request method is not POST, returns HTTP 405 with an error.
      - If the JSON body is invalid, returns HTTP 400 with `{"error": "Invalid JSON"}`.
      - If a database error occurs, returns HTTP 500 with `{"error": "Database error: <msg>"}`.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request containing the JSON payload.

    Returns
    -------
    django.http.JsonResponse
        - On success: `{"message": "New entry added successfully!", "new_entry": {...}}`, status=201.
        - On error: `{"error": <message>}`, status=400, 405, or 500.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            # Ensure asset is properly formatted
            if "asset" in data:
                data["asset"] = add_zeros(str(data["asset"]))  # Convert asset to string before processing

            connection = get_creds()
            if connection.is_connected():
                cursor = connection.cursor(dictionary=True)

                # Insert the new EPV entry into the database
                insert_query = """
                    INSERT INTO quality_epv_assets (QC1, OP1, Check1, Desc1, Method1, Interval1, Person, Asset)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(insert_query, (
                    data["qc1"], data["op1"], data["check1"], data["desc1"], 
                    data["method1"], data["interval1"], data["person"], data["asset"]
                ))
                connection.commit()

                new_entry_id = cursor.lastrowid  # Get the newly inserted row ID

                # Fetch the newly inserted row
                cursor.execute("""
                    SELECT id, QC1, OP1, Check1, Desc1, Method1, Interval1, Person, Asset 
                    FROM quality_epv_assets 
                    WHERE id = %s
                """, (new_entry_id,))
                new_entry = cursor.fetchone()

                # Remove trailing ".0" before sending data to frontend
                if new_entry:
                    new_entry["Asset"] = remove_zeros(new_entry["Asset"])

                cursor.close()
                connection.close()

                return JsonResponse({"message": "New entry added successfully!", "new_entry": new_entry}, status=201)

        except Error as e:
            return JsonResponse({"error": f"Database error: {e}"}, status=500)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

    return JsonResponse({"error": "Invalid request method"}, status=405)
