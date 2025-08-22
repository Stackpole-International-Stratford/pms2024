# quality/views.py
from django.shortcuts import render, get_object_or_404, redirect
from .models import Feat
from .forms import FeatForm
from plant.models.setupfor_models import Part, Asset
from django.db import transaction  
from django.db.models import F
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import ScrapForm, FeatEntry, SupervisorAuthorization, ScrapCategory, ScrapSubmission, ScrapSystemOperation
import json
from .models import Feat
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
import os
import importlib.util
import inspect
import re
from decimal import Decimal
from django.contrib import messages
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
import requests
from django.conf import settings
from django.views.decorators.http import require_GET
from plant.models.email_models import EmailCampaign
from .models import *
from django.db.models import Exists, OuterRef
from django.core import serializers
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, Http404
from django.shortcuts import redirect, render
from .models import TPCRequest

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
    # Get the Part object based on the part_number
    part = get_object_or_404(Part, part_number=part_number)
    
    # Get all feats associated with this part
    feats = part.feat_set.all()

    # Pass the feats and part to the template
    return render(request, 'quality/scrap_form.html', {'part': part, 'feats': feats})





def scrap_form_management(request):
    # Get all parts, whether or not they have feats
    parts = Part.objects.all().prefetch_related('feat_set')
    return render(request, 'quality/scrap_form_management.html', {'parts': parts})



def feat_create(request):
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
    feat = get_object_or_404(Feat, pk=pk)

    if request.method == 'POST':
        # Simply delete the feat without adjusting the orders of remaining feats
        feat.delete()
        return redirect('scrap_form_management')
    
    return render(request, 'quality/feat_confirm_delete.html', {'feat': feat})


def feat_move_up(request, pk):
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






# =============================================================================
# =============================================================================
# ======================= New Scrap System ====================================
# =============================================================================
# =============================================================================

def scrap_entry(request):
    """
    GET:  Render the “Add & Submit All” interface.
    POST: Bulk-create ScrapSubmission rows from the `entries` JSON,
          including a shared operator_number.
    """
    # 1) Master list of part numbers
    part_numbers = list(
        ScrapSystemOperation.objects
            .order_by('part_number')
            .values_list('part_number', flat=True)
            .distinct()
    )

    # 2) Form-state defaults (for re-render on validation errors)
    sel_pn        = ''
    sel_mc        = ''
    sel_op        = ''
    sel_cat       = ''
    sel_operator  = ''   # ← your new operator field
    sel_qty       = ''   # ← start blank

    machines   = []
    operations = []
    categories = []

    if request.method == 'POST':
        # --- pull back the operator number (single field) ---
        sel_operator = request.POST.get('operator', '').strip()

        # --- repopulate any dropdowns so they stay visible ---
        sel_pn = request.POST.get('part_number', '').strip()
        if sel_pn:
            machines = (
                Asset.objects
                     .filter(scrapsystemoperation__part_number=sel_pn)
                     .order_by('asset_number')
                     .values_list('asset_number', flat=True)
                     .distinct()
            )

        sel_mc = request.POST.get('machine', '').strip()
        if sel_pn and sel_mc:
            operations = list(
                ScrapSystemOperation.objects
                    .filter(part_number=sel_pn, assets__asset_number=sel_mc)
                    .order_by('operation')
                    .values_list('operation', flat=True)
                    .distinct()
            )

        sel_op = request.POST.get('operation', '').strip()
        if sel_pn and sel_mc and sel_op:
            qs = ScrapSystemOperation.objects.filter(
                part_number=sel_pn,
                operation=sel_op,
                assets__asset_number=sel_mc
            )
            if qs.exists():
                categories = list(
                    qs.first()
                      .scrap_categories
                      .values_list('name', flat=True)
                )

        # 3) pull in the JSON array of “added” rows
        raw_entries = request.POST.get('entries', '[]')
        try:
            entries = json.loads(raw_entries)
        except json.JSONDecodeError:
            entries = []

        # 4) Validation: need at least one entry
        if not entries:
            messages.error(request, "No entries to submit. Please Add at least one row.")
        else:
            created = 0
            for idx, e in enumerate(entries, start=1):
                part      = e.get('part')
                machine   = e.get('machine')
                operation = e.get('operation')
                category  = e.get('category')
                qty_str   = e.get('qty')

                # presence check
                if not all([part, machine, operation, category, qty_str, sel_operator]):
                    messages.warning(request,
                        f"Entry #{idx} missing data or operator—skipped."
                    )
                    continue

                # parse qty
                try:
                    qty = int(qty_str)
                    if qty < 1:
                        raise ValueError
                except ValueError:
                    messages.warning(request,
                        f"Entry #{idx} has invalid quantity “{qty_str}”—skipped."
                    )
                    continue

                # find matching ScrapSystemOperation
                sso = (
                    ScrapSystemOperation.objects
                        .filter(
                            part_number=part,
                            operation=operation,
                            assets__asset_number=machine
                        )
                        .first()
                )
                if not sso:
                    messages.warning(request,
                        f"Entry #{idx} has invalid part/op/machine—skipped."
                    )
                    continue

                # latest Asset
                asset = (
                    Asset.objects
                         .filter(asset_number=machine)
                         .order_by('-id')
                         .first()
                )
                if not asset:
                    messages.warning(request,
                        f"Entry #{idx} machine not found—skipped."
                    )
                    continue

                # latest Category
                cat = (
                    ScrapCategory.objects
                                 .filter(name=category)
                                 .order_by('-id')
                                 .first()
                )
                if not cat:
                    messages.warning(request,
                        f"Entry #{idx} category not found—skipped."
                    )
                    continue

                # compute & save
                unit_cost  = sso.cost
                total_cost = unit_cost * qty

                ScrapSubmission.objects.create(
                    scrap_system_operation=sso,
                    asset=asset,
                    scrap_category=cat,

                    part_number     = part,
                    machine         = machine,
                    operation_name  = operation,
                    category_name   = category,
                    operator_number = sel_operator,

                    quantity   = qty,
                    unit_cost  = unit_cost,
                    total_cost = total_cost,
                )
                created += 1

            if created:
                messages.success(request, f"{created} scrap entr{'y' if created == 1 else 'ies'} recorded.")
                return redirect('scrap_entry')
            else:
                messages.error(request, "No valid entries were recorded.")

    # 5) FINAL render (GET or POST with errors)
    return render(request, 'quality/scrap_entry.html', {
        'part_numbers':         part_numbers,
        'machines':             machines,
        'operations':           operations,
        'categories':           categories,
        'selected_part_number': sel_pn,
        'selected_machine':     sel_mc,
        'selected_operation':   sel_op,
        'selected_category':    sel_cat,
        'selected_operator':    sel_operator,
        'quantity':             sel_qty,
    })

def get_operations(request):
    """
    AJAX: return all operations for a given part_number.
    If machine is provided, only operations valid on that machine.
    """
    pn = request.GET.get('part_number')
    mc = request.GET.get('machine')  # may be None

    qs = ScrapSystemOperation.objects.filter(part_number=pn)
    if mc:
        qs = qs.filter(assets__asset_number=mc)

    ops = (
        qs.order_by('operation')
          .values_list('operation', flat=True)
          .distinct()
    )
    return JsonResponse({'results': list(ops)})


def get_machines(request):
    """
    AJAX: return one machine per asset_number (latest if duplicates) for a part.
    If operation is provided, only machines that perform that operation.
    """
    pn = request.GET.get('part_number')
    op = request.GET.get('operation')  # may be None

    qs = Asset.objects.filter(scrapsystemoperation__part_number=pn)
    if op:
        qs = qs.filter(scrapsystemoperation__operation=op)

    machines = (
        qs.order_by('asset_number', '-id')
          .values_list('asset_number', flat=True)
          .distinct()
    )
    return JsonResponse({'results': list(machines)})


def get_categories(request):
    """AJAX: return all scrap categories for PN + machine + operation."""
    pn = request.GET.get('part_number')
    mc = request.GET.get('machine')
    op = request.GET.get('operation')
    try:
        sso = ScrapSystemOperation.objects.get(
            part_number=pn,
            operation=op,
            assets__asset_number=mc
        )
        cats = sso.scrap_categories.all().values_list('name', flat=True)
        return JsonResponse({'results': list(cats)})
    except ScrapSystemOperation.DoesNotExist:
        return JsonResponse({'results': []})
    











# =====================================================================
# =====================================================================
# ============================ TPCs  ==================================
# =====================================================================
# =====================================================================



@login_required(login_url='/login/')
def tpc_request(request):
    page_size = settings.TPC_PAGE_SIZE
    is_tpc_approver = request.user.groups.filter(name="tpc_approvers").exists()

    # DEBUG PRINTS
    print("DEBUG: Logged in user:", request.user.username)
    print("DEBUG: Groups for user:", list(request.user.groups.values_list("name", flat=True)))
    print("DEBUG: Is TPC Approver?", is_tpc_approver)

    tpcs = (
        TPCRequest.objects
        .order_by('-id')
        .annotate(
            user_has_approved=Exists(
                TPCApproval.objects.filter(tpc=OuterRef("pk"), user=request.user)
            )
        )
        .prefetch_related("approvals")[:page_size]
    )

    return render(
        request,
        "quality/tpc_requests.html",
        {
            "tpcs": tpcs,
            "is_tpc_approver": is_tpc_approver,
            "tpc_page_size": settings.TPC_PAGE_SIZE
        },
    )



@login_required(login_url='/login/')
def tpc_request_load_more(request):
    try:
        offset = int(request.GET.get("offset", 0))
    except ValueError:
        offset = 0

    page_size = settings.TPC_PAGE_SIZE
    is_tpc_approver = request.user.groups.filter(name="tpc_approvers").exists()

    tpc_qs = (
        TPCRequest.objects
        .order_by('-date_requested')
        .annotate(
            user_has_approved=Exists(
                TPCApproval.objects.filter(tpc=OuterRef("pk"), user=request.user)
            )
        )
        .prefetch_related("approvals")[offset:offset + page_size + 1]
    )

    tpcs = list(tpc_qs[:page_size])
    has_more = len(tpc_qs) > page_size

    data = []
    for t in tpcs:
        data.append({
            "pk": t.pk,
            "date_requested": t.date_requested.strftime("%Y-%m-%d %H:%M"),
            "issuer_name": t.issuer_name,
            "parts": ", ".join(t.parts) if t.parts else "—",
            "reason": t.reason,
            "process": t.process,
            "supplier_issue": "Yes" if t.supplier_issue else "No",
            "machines": ", ".join(t.machines) if t.machines else "—",
            "expiration_date": t.expiration_date.strftime("%Y-%m-%d %H:%M"),
            "approved": t.approved,
            "approvals_got": t.approvals.count(),
            "approvals_req": t.required_approvals_count(),
            "approvers": ", ".join(
                a.user.get_full_name() or a.user.username
                for a in t.approvals.all()
            ) or "—",
            "user_has_approved": t.user_has_approved,
            "pdf_url": tpc_request_pdf and request.build_absolute_uri(
                f"/quality/tpc/{t.pk}/pdf/"
            ) if t.approved else None
        })

    return JsonResponse({"rows": data, "has_more": has_more, "is_tpc_approver": is_tpc_approver})



@login_required(login_url='/login/')
def tpc_request_create(request):
    if request.method == "POST":
        print("---- TPC Request Create POST ----")
        print("POST data:", request.POST)

        issuer_name = request.POST.get("issuer_name", "").strip()
        parts = request.POST.getlist("parts")
        reason = request.POST.get("reason", "").strip()
        process = request.POST.get("process", "").strip()
        supplier_issue = bool(request.POST.get("supplier_issue"))
        machines = request.POST.getlist("machines")
        reason_note = request.POST.get("reason_note", "").strip()
        feature = request.POST.get("feature", "").strip()
        expiration_date_str = request.POST.get("expiration_date", "").strip()
        current_process = request.POST.get("current_process", "").strip()
        changed_to = request.POST.get("changed_to", "").strip()

        print("Parsed values:")
        print("  issuer_name:", issuer_name)
        print("  parts:", parts)
        print("  reason:", reason)
        print("  process:", process)
        print("  supplier_issue:", supplier_issue)
        print("  machines:", machines)
        print("  reason_note:", reason_note)
        print("  feature:", feature)
        print("  expiration_date_str:", expiration_date_str)
        print("  current_process:", current_process)
        print("  changed_to:", changed_to)

        # --- Validation ---
        missing = []
        if not issuer_name: missing.append("Issuer name")
        if not parts: missing.append("At least one part")
        if not reason: missing.append("Reason")
        if not process: missing.append("Process")
        if not machines: missing.append("At least one machine")
        if not expiration_date_str: missing.append("Expiration date")
        if not current_process: missing.append("Current process")
        if not changed_to: missing.append("Changed to")

        if missing:
            print("Missing fields:", missing)
            return render(request, "quality/tpc_request_form.html", {
                "issuer_default": issuer_name or (request.user.get_full_name() or request.user.username),
                "parts_qs": Part.objects.all().order_by("part_number"),
                "machines_qs": Asset.objects.all().order_by("asset_number"),
            })

        # Parse datetime-local input (YYYY-MM-DDTHH:MM)
        try:
            expiration_dt = timezone.make_aware(
                timezone.datetime.fromisoformat(expiration_date_str)
            )
            print("Parsed expiration_dt:", expiration_dt)
        except Exception as e:
            print("Expiration date parse error:", e)
            return render(request, "quality/tpc_request_form.html", {
                "issuer_default": issuer_name,
                "parts_qs": Part.objects.all().order_by("part_number"),
                "machines_qs": Asset.objects.all().order_by("asset_number"),
            })

        # Create TPCRequest with JSON fields
        try:
            tpc = TPCRequest.objects.create(
                issuer_name=issuer_name,
                parts=parts,                # stored as JSON list
                reason=reason,
                process=process,
                supplier_issue=supplier_issue,
                machines=machines,          # stored as JSON list
                reason_note=reason_note,
                feature=feature,
                expiration_date=expiration_dt,
                current_process=current_process,
                changed_to=changed_to,
            )
            print("Created TPC with PK:", tpc.pk)
        except Exception as e:
            print("Error creating TPCRequest:", e)
            raise

        return redirect("tpc_request_list")

    # GET: render form
    print("---- TPC Request Create GET ----")
    return render(request, "quality/tpc_request_form.html", {
        "issuer_default": request.user.get_full_name() or request.user.username,
        "parts_qs": Part.objects.all().order_by("part_number"),
        "machines_qs": Asset.objects.all().order_by("asset_number"),
    })


@login_required(login_url='/login/')
def tpc_request_edit(request, pk):
    tpc = get_object_or_404(
        TPCRequest.objects.select_related("approved_by").prefetch_related("approvals__user"),
        pk=pk
    )

    if request.method == "POST":
        print("---- TPC Request Edit POST ----")
        print("POST data:", request.POST)

        issuer_name = request.POST.get("issuer_name", "").strip()
        parts = request.POST.getlist("parts")
        reason = request.POST.get("reason", "").strip()
        process = request.POST.get("process", "").strip()
        supplier_issue = bool(request.POST.get("supplier_issue"))
        machines = request.POST.getlist("machines")
        reason_note = request.POST.get("reason_note", "").strip()
        feature = request.POST.get("feature", "").strip()
        expiration_date_str = request.POST.get("expiration_date", "").strip()
        current_process = request.POST.get("current_process", "").strip()
        changed_to = request.POST.get("changed_to", "").strip()

        print("Parsed values:")
        print("  issuer_name:", issuer_name)
        print("  parts:", parts)
        print("  reason:", reason)
        print("  process:", process)
        print("  supplier_issue:", supplier_issue)
        print("  machines:", machines)
        print("  reason_note:", reason_note)
        print("  feature:", feature)
        print("  expiration_date_str:", expiration_date_str)
        print("  current_process:", current_process)
        print("  changed_to:", changed_to)

        # --- Validation (same rules as create) ---
        missing = []
        if not issuer_name: missing.append("Issuer name")
        if not parts: missing.append("At least one part")
        if not reason: missing.append("Reason")
        if not process: missing.append("Process")
        if not machines: missing.append("At least one machine")
        if not expiration_date_str: missing.append("Expiration date")
        if not current_process: missing.append("Current process")
        if not changed_to: missing.append("Changed to")

        if missing:
            print("Missing fields:", missing)
            return render(request, "quality/tpc_edit.html", {
                "tpc": tpc,  # re-show existing DB values below if parsing fails
                "issuer_default": issuer_name or (request.user.get_full_name() or request.user.username),
                "parts_qs": Part.objects.all().order_by("part_number"),
                "machines_qs": Asset.objects.all().order_by("asset_number"),
                "form_error": "Please fill all required fields."
            })

        # Parse datetime-local input (YYYY-MM-DDTHH:MM)
        try:
            expiration_dt = timezone.make_aware(
                timezone.datetime.fromisoformat(expiration_date_str)
            )
        except Exception as e:
            print("Expiration date parse error:", e)
            return render(request, "quality/tpc_edit.html", {
                "tpc": tpc,
                "issuer_default": issuer_name,
                "parts_qs": Part.objects.all().order_by("part_number"),
                "machines_qs": Asset.objects.all().order_by("asset_number"),
                "form_error": "Invalid expiration date."
            })

        # Update fields
        try:
            tpc.issuer_name = issuer_name
            tpc.parts = parts
            tpc.reason = reason
            tpc.process = process
            tpc.supplier_issue = supplier_issue
            tpc.machines = machines
            tpc.reason_note = reason_note
            tpc.feature = feature
            tpc.expiration_date = expiration_dt
            tpc.current_process = current_process
            tpc.changed_to = changed_to
            tpc.save()
            print("Updated TPC with PK:", tpc.pk)
        except Exception as e:
            print("Error updating TPCRequest:", e)
            raise

        return redirect("tpc_request_list")

    # GET: render edit form prepopulated
    print("---- TPC Request Edit GET ----")
    return render(request, "quality/tpc_edit.html", {
        "tpc": tpc,
        "issuer_default": tpc.issuer_name or (request.user.get_full_name() or request.user.username),
        "parts_qs": Part.objects.all().order_by("part_number"),
        "machines_qs": Asset.objects.all().order_by("asset_number"),
    })


@login_required(login_url='/login/')
def tpc_request_approve(request, pk):
    """POST-only endpoint to record *this user's* approval toward the group consensus."""
    if request.method != "POST":
        return redirect("tpc_request_list")

    if not request.user.groups.filter(name="tpc_approvers").exists():
        return redirect("tpc_request_list")

    tpc = get_object_or_404(TPCRequest, pk=pk)

    if tpc.approved:
        return redirect("tpc_request_list")

    if tpc.has_user_approved(request.user):
        return redirect("tpc_request_list")

    try:
        tpc.approve(request.user)
        tpc.refresh_from_db()
    except PermissionError:
        return redirect("tpc_request_list")

    # inside tpc_request_approve, where you already have:
    if tpc.approved:
        # fire the email AFTER the DB commit
        send_tpc_broadcast_email(tpc.pk)

    return redirect("tpc_request_list")


def _render_tpc_html(tpc) -> str:
    def join_list(val):
        if not val:
            return "—"
        return ", ".join(val)

    local_exp = timezone.localtime(tpc.expiration_date) if timezone.is_aware(tpc.expiration_date) else tpc.expiration_date
    approved_at_local = timezone.localtime(tpc.approved_at) if tpc.approved_at else None

    approver_names = [a.user.get_full_name() or a.user.username for a in tpc.approvals.all()]
    approvals_block = ", ".join(approver_names) if approver_names else "—"

    supplier_issue = "Yes" if tpc.supplier_issue else "No"

    pdf_url = f"http://10.4.1.234/quality/tpc/{tpc.pk}/pdf/"

    return f"""
        <div style="font-family: Arial, sans-serif; line-height:1.6; color:#333; background-color:#f7f9fc; padding:20px;">
        <div style="max-width:700px; margin:0 auto; background-color:#fff; border-radius:8px; overflow:hidden; box-shadow:0 2px 6px rgba(0,0,0,0.1);">
            
            <!-- PDF Link Banner -->
            <div style="background-color:#ffd84d; text-align:center; padding:10px;">
                <a href="{pdf_url}" target="_blank" style="font-weight:bold; color:#004085; text-decoration:none; font-size:15px;">
                📄 View TPC #{tpc.pk} PDF
                </a>
            </div>

            <!-- Header -->
            <div style="background-color:#000000; color:#fff; padding:16px 20px; text-align:center;">
                <h2 style="margin:0; font-size:22px;">Temporary Process Change</h2>
                <div style="font-size:26px; font-weight:700; margin-top:5px;">TPC #{tpc.pk}</div>
                <p style="margin:6px 0 0; font-size:14px; opacity:0.85;">
                    Issued by {tpc.issuer_name or '—'} &middot; {tpc.date_requested}
                </p>
            </div>
            
            <!-- Body -->
            <div style="padding:20px;">
                <p style="margin-top:0; font-size:15px;">
                    The following Temporary Process Change request has received all required approvals and is now official.
                </p>

                <table style="width:100%; border-collapse:collapse; font-size:14px;">
                <tbody>
                    <tr style="background-color:#f0f4f8;">
                    <td style="padding:8px; width:200px; font-weight:bold;">ID</td>
                    <td style="padding:8px;">{tpc.pk}</td>
                    </tr>
                    <tr>
                    <td style="padding:8px; font-weight:bold;">Date Requested</td>
                    <td style="padding:8px;">{tpc.date_requested}</td>
                    </tr>
                    <tr style="background-color:#f0f4f8;">
                    <td style="padding:8px; font-weight:bold;">Parts</td>
                    <td style="padding:8px;">{join_list(tpc.parts)}</td>
                    </tr>
                    <tr>
                    <td style="padding:8px; font-weight:bold;">Reason</td>
                    <td style="padding:8px; white-space:pre-wrap;">{tpc.reason or '—'}</td>
                    </tr>
                    <tr style="background-color:#f0f4f8;">
                    <td style="padding:8px; font-weight:bold;">Process</td>
                    <td style="padding:8px; white-space:pre-wrap;">{tpc.process or '—'}</td>
                    </tr>
                    <tr>
                    <td style="padding:8px; font-weight:bold;">Supplier Issue</td>
                    <td style="padding:8px;">{supplier_issue}</td>
                    </tr>
                    <tr style="background-color:#f0f4f8;">
                    <td style="padding:8px; font-weight:bold;">Machines</td>
                    <td style="padding:8px;">{join_list(tpc.machines)}</td>
                    </tr>
                    <tr>
                    <td style="padding:8px; font-weight:bold;">Feature</td>
                    <td style="padding:8px;">{tpc.feature or '—'}</td>
                    </tr>
                    <tr style="background-color:#f0f4f8;">
                    <td style="padding:8px; font-weight:bold;">Current Process</td>
                    <td style="padding:8px; white-space:pre-wrap;">{tpc.current_process or '—'}</td>
                    </tr>
                    <tr>
                    <td style="padding:8px; font-weight:bold;">Changed To</td>
                    <td style="padding:8px; white-space:pre-wrap;">{tpc.changed_to or '—'}</td>
                    </tr>
                    <tr style="background-color:#f0f4f8;">
                    <td style="padding:8px; font-weight:bold;">Expiration</td>
                    <td style="padding:8px;">{local_exp:%Y-%m-%d %H:%M %Z}</td>
                    </tr>
                    <tr>
                    <td style="padding:8px; font-weight:bold;">Approvals</td>
                    <td style="padding:8px;">{tpc.approvals.count()}/{tpc.required_approvals_count()} – {approvals_block}</td>
                    </tr>
                    <tr style="background-color:#f0f4f8;">
                    <td style="padding:8px; font-weight:bold;">Approved By (Last)</td>
                    <td style="padding:8px;">{(tpc.approved_by.get_full_name() if tpc.approved_by else None) or (tpc.approved_by.username if tpc.approved_by else '—')}</td>
                    </tr>
                    <tr>
                    <td style="padding:8px; font-weight:bold;">Approved At</td>
                    <td style="padding:8px;">{approved_at_local.strftime('%Y-%m-%d %H:%M %Z') if approved_at_local else '—'}</td>
                    </tr>
                </tbody>
                </table>

                <p style="margin-top:20px; font-size:13px; color:#666;">
                    This message was sent automatically after all required approvers confirmed the TPC.
                </p>
            </div>
        </div>
        </div>
        """



def send_tpc_broadcast_email(tpc_pk: int) -> None:
    """
    Fetch recipients from the 'TPC Email' campaign and send the email via Flask.
    Prints detailed debug info at every step.
    """
    from .models import TPCRequest  # avoid circular import
    print(f"[DEBUG] Preparing broadcast email for TPC #{tpc_pk}")

    try:
        tpc = (
            TPCRequest.objects
            .select_related("approved_by")
            .prefetch_related("approvals__user")
            .get(pk=tpc_pk)
        )
    except TPCRequest.DoesNotExist:
        print(f"[ERROR] TPC #{tpc_pk} does not exist.")
        return

    # 1) Load campaign + recipients
    try:
        campaign = (
            EmailCampaign.objects
            .filter(name="TPC Email")
            .prefetch_related("recipients")
            .first()
        )
    except Exception as e:
        print(f"[ERROR] Could not fetch EmailCampaign: {e}")
        return

    if not campaign:
        print("[ERROR] Campaign 'TPC Email' not found.")
        return

    # Flask expects a list of strings for 'recipients'
    recips_emails = [r.email for r in campaign.recipients.all()]
    if not recips_emails:
        print("[ERROR] No recipients in 'TPC Email' campaign.")
        return

    print(f"[DEBUG] Found {len(recips_emails)} recipient emails: {recips_emails}")

    # 2) Build content
    subject = f"TPC #{tpc.pk} fully approved – {tpc.issuer_name} – {tpc.date_requested:%Y-%m-%d}"
    html_body = _render_tpc_html(tpc)
    # text is optional for your Flask service; keep it if it accepts, otherwise drop it.
    text_body = strip_tags(html_body)

    print(f"[DEBUG] Email subject: {subject}")
    print(f"[DEBUG] HTML body length: {len(html_body)} chars")
    print(f"[DEBUG] Text body length: {len(text_body)} chars")

    # 3) Payload per Flask error: needs 'html' and 'recipients'
    payload = {
        "subject": subject,
        "html": html_body,
        "recipients": recips_emails,   # <-- key change from 'to' -> 'recipients'
        "text": text_body,             # keep if your service allows; harmless if ignored
    }

    print("[DEBUG] Payload JSON to be sent:")
    print(payload)

    # 4) Send
    url = getattr(settings, "FLASK_EMAILER_URL", None)
    if not url:
        print("[ERROR] FLASK_EMAILER_URL not configured in settings.")
        return

    print(f"[DEBUG] Sending POST to {url}")
    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"[DEBUG] HTTP status: {resp.status_code}")
        print(f"[DEBUG] Response body: {resp.text}")

        if resp.status_code >= 400:
            print(f"[ERROR] Flask emailer returned error: {resp.status_code} {resp.text}")
        else:
            print(f"[SUCCESS] Broadcast email for TPC #{tpc.pk} sent to {len(recips_emails)} recipients.")
    except Exception as e:
        print(f"[ERROR] Exception while sending broadcast email: {e}")



# quality/views.py

# (optional) remove the top-level import to keep it lazy:
# from weasyprint import HTML



@login_required(login_url='/login/')
def tpc_request_pdf(request, pk):
    """
    Generate a PDF for a TPC.
    - If fully approved (official), render the official PDF.
    - Else, if at least one verbal approval exists, render the verbal PDF.
    - Else, forbid access.
    """
    # Lazy import so the whole site doesn't crash if libs are missing
    from weasyprint import HTML

    tpc = (
        TPCRequest.objects
        .select_related("approved_by")
        .prefetch_related("approvals__user", "verbal_approvals")
        .filter(pk=pk)
        .first()
    )
    if not tpc:
        raise Http404("TPC not found")

    # Official PDF
    if tpc.approved:
        html = render_to_string("quality/tpc_print.html", {"tpc": tpc}, request=request)
        filename = f"tpc-{tpc.pk}.pdf"

    else:
        # Verbal PDF fallback (if any verbal approval exists)
        verbal = tpc.verbal_approvals.order_by("-created_at").first()
        if not verbal:
            return HttpResponseForbidden("This TPC is not approved yet.")
        html = render_to_string(
            "quality/tpc_print_verbal.html",
            {"tpc": tpc, "verbal": verbal},
            request=request
        )
        filename = f"tpc-{tpc.pk}-verbal.pdf"

    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp


@login_required(login_url='/login/')
def tpc_request_verbal(request, pk):
    tpc = get_object_or_404(TPCRequest, pk=pk)

    if request.method == "POST":
        approver_name = request.POST.get("approver_name", "").strip()
        approver_phone = request.POST.get("approver_phone", "").strip()
        approver_response = request.POST.get("approver_response", "").strip()
        approved = bool(request.POST.get("approved"))

        if not approver_name or not approver_phone or not approver_response:
            return render(request, "quality/tpc_verbal_form.html", {
                "tpc": tpc,
                "form_error": "All fields are required."
            })

        VerbalApproval.objects.create(
            tpc=tpc,
            issuer=request.user,
            approver_name=approver_name,
            approver_phone=approver_phone,
            approver_response=approver_response,
            approved=approved,
        )

        return redirect("tpc_request_list")

    return render(request, "quality/tpc_verbal_form.html", {"tpc": tpc})
