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



def index(request):
    is_epv_manager = False
    if request.user.is_authenticated:
        is_epv_manager = request.user.groups.filter(name="epv_manager").exists()
    context = {
        'is_epv_manager': is_epv_manager,
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
        data = json.loads(request.body)
        part_number = data.get('part_number')
        name = data.get('name')
        alarm = data.get('alarm')
        critical = data.get('critical', False)  # Get the critical field, defaulting to False

        try:
            part = Part.objects.get(part_number=part_number)
            new_order = part.feat_set.count() + 1

            feat = Feat.objects.create(
                part=part,
                name=name,
                order=new_order,
                alarm=alarm,
                critical=critical  # Save the critical field
            )

            return JsonResponse({'status': 'success', 'feat_id': feat.id, 'new_order': new_order})
        except Part.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Part not found.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

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

# Utility function to connect to the database
def get_db_connection():
    return mysql.connector.connect(
        host="10.4.1.224",
        user="stuser",
        password="stp383",
        database="prodrptdb"
    )



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
        connection = get_db_connection()
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            query = """
                SELECT id, QC1, OP1, Check1, Desc1, Method1, Interval1, Person, Asset 
                FROM quality_epv_assets_backup
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
    # Check if the user is in the 'epv_manager' group.
    if not request.user.groups.filter(name='epv_manager').exists():
        return HttpResponseForbidden("Only EPV admins are authorized to access this page. If you require access, please request an admin to add you to EPV_Managers group")
     
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

            connection = get_db_connection()
            if connection.is_connected():
                cursor = connection.cursor()
                delete_query = "DELETE FROM quality_epv_assets_backup WHERE id = %s"
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

            connection = get_db_connection()
            if connection.is_connected():
                cursor = connection.cursor()
                update_query = "UPDATE quality_epv_assets_backup SET Asset = %s WHERE id = %s"
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
        connection = get_db_connection()
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)

            # Step 1: Get the QC1 value for the given ID
            cursor.execute("SELECT QC1 FROM quality_epv_assets_backup WHERE id = %s", (epv_id,))
            result = cursor.fetchone()

            if not result:
                print(f"No entry found for ID: {epv_id}")
                return

            qc1_value = result["QC1"]
            print(f"QC1 for ID {epv_id}: {qc1_value}")

            # Step 2: Find all entries with the same QC1
            cursor.execute("SELECT id, Person FROM quality_epv_assets_backup WHERE QC1 = %s", (qc1_value,))
            related_entries = cursor.fetchall()

            print("Updating the following entries with new Person name:")
            for entry in related_entries:
                print(f"ID: {entry['id']}, Old Person: {entry['Person']} → New Person: {new_person}")

            # Step 3: Update the Person field for all related entries
            cursor.execute("UPDATE quality_epv_assets_backup SET Person = %s WHERE QC1 = %s", (new_person, qc1_value))
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
        connection = get_db_connection()
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)

            # Retrieve the original row's data
            cursor.execute("""
                SELECT QC1, OP1, Check1, Desc1, Method1, Interval1, Person 
                FROM quality_epv_assets_backup 
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
                INSERT INTO quality_epv_assets_backup (QC1, OP1, Check1, Desc1, Method1, Interval1, Person, Asset)
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
                FROM quality_epv_assets_backup 
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
        connection = get_db_connection()
        if connection.is_connected():
            cursor = connection.cursor()

            # Get QC1 value
            cursor.execute("SELECT QC1 FROM quality_epv_assets_backup WHERE id = %s", (epv_id,))
            result = cursor.fetchone()

            if not result:
                return []

            qc1_value = result[0]

            # Update column for all matching QC1 values
            query = f"UPDATE quality_epv_assets_backup SET {column_name} = %s WHERE QC1 = %s"
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

            connection = get_db_connection()
            if connection.is_connected():
                cursor = connection.cursor(dictionary=True)

                # Insert the new EPV entry into the database
                insert_query = """
                    INSERT INTO quality_epv_assets_backup (QC1, OP1, Check1, Desc1, Method1, Interval1, Person, Asset)
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
                    FROM quality_epv_assets_backup 
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
