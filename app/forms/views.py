from django.shortcuts import render, redirect, get_object_or_404
from .forms import FORM_TYPE_FORMS, OISQuestionForm
from .models import FormType, Form, FormQuestion
from django.forms import modelformset_factory
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib import messages
from django.db.models import Max
from django.urls import reverse
from django.db import transaction
from .forms import QUESTION_FORM_CLASSES



def index(request):
    # Check if the user is logged in and belongs to the LPA Managers group
    is_lpa_manager = request.user.is_authenticated and request.user.groups.filter(name="LPA Managers").exists()

    return render(request, 'forms/index.html', {'is_lpa_manager': is_lpa_manager})


# CRUD for FormType
class FormTypeListView(ListView):
    model = FormType
    template_name = 'forms/formtypes/formtype_list.html'
    context_object_name = 'formtypes'


class FormTypeCreateView(CreateView):
    model = FormType
    fields = ['name', 'template_name']
    template_name = 'forms/formtypes/formtype_form.html'
    success_url = reverse_lazy('formtype_list')


class FormTypeUpdateView(UpdateView):
    model = FormType
    fields = ['name', 'template_name']
    template_name = 'forms/formtypes/formtype_form.html'
    success_url = reverse_lazy('formtype_list')


class FormTypeDeleteView(DeleteView):
    model = FormType
    template_name = 'forms/formtypes/formtype_confirm_delete.html'
    success_url = reverse_lazy('formtype_list')




# View to create form and its questions
from django.shortcuts import render, redirect, get_object_or_404
from .forms import FORM_TYPE_FORMS, QUESTION_FORM_CLASSES
from .models import FormType, Form, FormQuestion
from django.forms import modelformset_factory

def form_create_view(request, form_id=None):
    form_instance = None
    form_type = None
    if form_id:
        # Fetch the existing form to edit
        form_instance = get_object_or_404(Form, id=form_id)
        form_type = form_instance.form_type
    else:
        # Fetch the form type from the request for new forms
        form_type_id = request.GET.get('form_type')
        if form_type_id:
            form_type = get_object_or_404(FormType, id=form_type_id)

    if form_type:
        # Dynamically get the form class for the form type
        form_class = FORM_TYPE_FORMS.get(form_type.name)
        question_form_class = QUESTION_FORM_CLASSES.get(form_type.name)

        if form_class is None or question_form_class is None:
            return render(request, 'forms/error.html', {'message': 'Form type not supported.'})

        # Create a dynamic formset for questions
        QuestionFormSet = modelformset_factory(
            FormQuestion,
            form=question_form_class,
            extra=0,  # Set extra to 0 to prevent empty forms unless added by the user
            can_delete=True  # Allow deletion of forms
        )

        if request.method == 'POST':
            form = form_class(request.POST, instance=form_instance)
            question_formset = QuestionFormSet(
                request.POST,
                queryset=form_instance.questions.filter(
                    ~Q(question__has_key='expired') | Q(question__expired=False)  # Exclude expired questions
                ).order_by('question__order') if form_instance else FormQuestion.objects.none()
            )

            if form.is_valid() and question_formset.is_valid():
                form_instance = form.save()

                # Save each question in the formset
                for index, question_form in enumerate(question_formset.forms, start=1):
                    if question_form.cleaned_data and not question_form.cleaned_data.get('DELETE', False):
                        question_form.save(form_instance=form_instance, order=index)
                    elif question_form.cleaned_data.get('DELETE', False) and question_form.instance.pk:
                        # If the form is marked for deletion and exists in the DB, delete it
                        question_form.instance.delete()

                return redirect('form_edit', form_id=form_instance.id)  # Redirect after saving

        else:
            # Fetch questions ordered by the 'order' field in the JSON, excluding expired
            form = form_class(instance=form_instance)
            question_formset = QuestionFormSet(
                queryset=form_instance.questions.filter(
                    ~Q(question__has_key='expired') | Q(question__expired=False)  # Exclude expired questions
                ).order_by('question__order') if form_instance else FormQuestion.objects.none()
            )

        # Pass `form_instance` to the template
        return render(request, 'forms/form_create.html', {
            'form': form,
            'question_formset': question_formset,
            'form_type': form_type,
            'original_form': form_instance,  # Ensure this is passed to the template
        })

    # If no form_type is provided, show a page to select the form type
    form_types = FormType.objects.all()
    return render(request, 'forms/select_form_type.html', {'form_types': form_types})









# =============================================================================
# =============================================================================
# ======================= Find forms Now ======================================
# =============================================================================
# =============================================================================


from django.shortcuts import render, get_object_or_404
from .models import Form, FormType
from django.contrib.auth.models import Group
from django.utils.timezone import now
import datetime

def find_and_tag_expired_questions():
    """
    Finds and tags all expired questions based on their expiry_date field.
    """
    # Get the current date
    today = now().date()

    # Fetch all questions from the FormQuestion model
    questions = FormQuestion.objects.all()

    for question in questions:
        # Extract the JSON object
        question_data = question.question

        # Check if the expiry_date key exists in the JSON and is valid
        expiry_date_str = question_data.get('expiry_date')
        if expiry_date_str:
            try:
                # Parse the expiry_date from the JSON object
                expiry_date = datetime.date.fromisoformat(expiry_date_str)
                if expiry_date < today:
                    # Tag the question as expired if the date is in the past
                    question_data['expired'] = True
                else:
                    # Ensure the expired key is False if the expiry_date is valid and not expired
                    question_data['expired'] = False
            except ValueError:
                # If the expiry_date is invalid, skip this question
                continue

            # Save the updated question data back to the model
            question.question = question_data
            question.save()


def find_deleted_forms(form_type_id):
    """
    Find and return the IDs of all forms for the specified form type
    that have 'deleted: true' in their metadata.
    """
    # Fetch all forms for the given form type that are marked as deleted
    deleted_forms = Form.objects.filter(
        form_type_id=form_type_id,
        metadata__deleted=True  # Filter forms with 'deleted: true' in metadata
    )

    # Collect the IDs of the deleted forms
    deleted_form_ids = [form.id for form in deleted_forms]
    print(f"[INFO] Deleted forms for form type {form_type_id}: {deleted_form_ids}")

    # Return the list of deleted form IDs
    return deleted_form_ids



def find_forms_view(request):
    # 1) Tag expired questions
    find_and_tag_expired_questions()

    # 2) Choose form_type or show selector
    form_type_id = request.GET.get('form_type')
    if not form_type_id:
        return render(request, 'forms/select_form_type.html', {
            'form_types': FormType.objects.all(),
            'is_lpa_manager': request.user.is_authenticated
                              and request.user.groups.filter(name="LPA Managers").exists(),
            'is_quality_engineer': request.user.is_authenticated
                                   and request.user.groups.filter(name="Quality Engineer").exists(),
            'is_authenticated': request.user.is_authenticated,
        })

    # 3) Load FormType or 404
    form_type = get_object_or_404(FormType, id=form_type_id)

    # 4) Fetch all non‐deleted forms for this type
    deleted_ids = find_deleted_forms(form_type_id)
    forms = (Form.objects
                 .filter(form_type_id=form_type_id)
                 .exclude(id__in=deleted_ids)
                 .order_by('-created_at'))

    # 5) Role flags
    is_lpa_manager      = request.user.is_authenticated \
                          and request.user.groups.filter(name="LPA Managers").exists()
    is_quality_engineer = request.user.is_authenticated \
                          and request.user.groups.filter(name="Quality Engineer").exists()

    # 6) Render everything—no filter logic here anymore!
    return render(request, 'forms/find_forms.html', {
        'form_type': form_type,
        'forms': forms,
        'is_lpa_manager': is_lpa_manager,
        'is_quality_engineer': is_quality_engineer,
        'is_authenticated': request.user.is_authenticated,
    })












# ==============================================================================
# ==============================================================================
# ======================== Bulk insert tool ====================================
# ==============================================================================
# ==============================================================================


from django.shortcuts import render, redirect
from .models import Form, FormQuestion, FormType
import json

def bulk_form_and_question_create_view(request):
    if request.method == 'POST':
        data_json = request.POST.get('data_json')
        delete_existing = request.POST.get('delete_existing') == 'on'

        try:
            data = json.loads(data_json)
        except json.JSONDecodeError as e:
            return render(request, 'forms/bulk_question_create.html', {
                'error': f'Invalid JSON data: {e}',
                'data_json': data_json,
            })

        form_data = data.get('form')
        questions_data = data.get('questions', [])

        # Create the new OIS Form
        form_instance = Form(
            name=form_data.get('name'),
            form_type=FormType.objects.get(name="OIS"),
            metadata={
                'part_number': form_data.get('part_number'),
                'operation': form_data.get('operation'),
                'part_name': form_data.get('part_name'),
                'year': form_data.get('year'),
                'mod_level': form_data.get('mod_level'),
                'machine': form_data.get('machine'),
                'mod_date': form_data.get('mod_date')
            }
        )
        form_instance.save()

        # Optionally delete existing questions if specified
        if delete_existing:
            form_instance.questions.all().delete()

        # Create questions associated with this form
        for index, question_data in enumerate(questions_data, start=1):
            question_data['order'] = question_data.get('order', index)
            FormQuestion.objects.create(
                form=form_instance,
                question=question_data
            )

        return redirect('form_edit', form_id=form_instance.id)

    else:
        return render(request, 'forms/bulk_question_create.html')





# {
#     "form": {
#         "name": "Sample OIS Form",
#         "part_number": "PN123",
#         "operation": "Op456",
#         "part_name": "Sample Part",
#         "year": "2023",
#         "mod_level": "A1",
#         "machine": "Machine XYZ",
#         "mod_date": "2023-11-11"
#     },
#     "questions": [
#         {
#             "feature": "67",
#             "special_characteristic": "Bu",
#             "characteristic": "Hub OD (Air Gauge)",
#             "specifications": "Ø30.187 - Ø30.213 mm",
#             "sample_frequency": "100%",
#             "sample_size": "100%",
#             "done_by": "OP/QA",
#             "checkmark": true
#         },
#         {
#             "feature": "HP",
#             "special_characteristic": "D",
#             "characteristic": "Hole(s) Presence (Visual/Gauge)",
#             "specifications": "Present YES / NO",
#             "sample_frequency": "100%",
#             "sample_size": "100%",
#             "done_by": "OP / QA",
#             "checkmark": false
#         }
#         // Add more questions as needed...
#     ]
# }








        




# ==================================================================
# ==================================================================
# ================= Operator Form Template OIS =====================
# ==================================================================
# ==================================================================

from django.shortcuts import render, get_object_or_404, redirect
from django.forms import modelformset_factory
from .models import Form, FormQuestion, FormAnswer
from .forms import OISAnswerForm, LPAAnswerForm
import datetime
import json

def form_questions_view(request, form_id):
    # Get the form instance and its form type
    form_instance = get_object_or_404(Form, id=form_id)
    form_type = form_instance.form_type

    # Debug print to check form instance and type
    print(f"[DEBUG] Form instance: {form_instance}, Form type: {form_type}")

    # Determine the template to render based on the form type's template name
    template_name = f'forms/{form_type.template_name}'

    # Map form types to their respective form classes
    answer_form_classes = {
        'OIS': OISAnswerForm,
        'LPA': LPAAnswerForm,
        # Add more form types as needed
    }

    # Get the form class for the current form type
    answer_form_class = answer_form_classes.get(form_type.name)
    if not answer_form_class:
        raise ValueError(f"No form class defined for form type: {form_type.name}")

    # Debug print to check selected form class
    # print(f"[DEBUG] Selected form class: {answer_form_class}")

    # Sort questions by the "order" key in the question JSON field directly
    questions = sorted(
        form_instance.questions.all(),
        key=lambda q: q.question.get("order", 0)  # Access the 'order' directly from the dictionary
    )

    # Debug print to check the number of questions
    # print(f"[DEBUG] Number of questions: {len(questions)}")

    # Prepare formset for submitting answers, initializing with the number of questions
    AnswerFormSet = modelformset_factory(FormAnswer, form=answer_form_class, extra=len(questions))

    # Prepare initial data for each question
    initial_data = [{'question': question} for question in questions]

    error_message = None  # Initialize error message variable

    # Retrieve the operator number from cookies
    operator_number = request.COOKIES.get('operator_number', '')

    # Debug print to check operator number
    # print(f"[DEBUG] Operator number from cookies: {operator_number}")

    if request.method == 'POST':
        operator_number = request.POST.get('operator_number')

        # Debug print to check operator number from POST
        # print(f"[DEBUG] Operator number from POST: {operator_number}")

        if not operator_number:
            error_message = "Operator number is required."
            formset = AnswerFormSet(
                request.POST, 
                queryset=FormAnswer.objects.none(), 
                form_kwargs={'user': request.user}  # Pass user to forms
            )
        else:
            # Set the operator number as a cookie to persist it
            response = redirect('form_questions', form_id=form_instance.id)
            response.set_cookie('operator_number', operator_number, expires=datetime.datetime.now() + datetime.timedelta(days=365))

            # Initialize formset with the posted data and pass the user
            formset = AnswerFormSet(
                request.POST, 
                queryset=FormAnswer.objects.none(), 
                form_kwargs={'user': request.user}  # Pass user during POST
            )

            # Debug print to check if user is being passed to the formset
            # print(f"[DEBUG] User passed to formset during POST: {request.user}")

            if formset.is_valid():
                for i, form in enumerate(formset):
                    answer_data = form.cleaned_data.get('answer')
                    if answer_data:
                        # Get the corresponding question
                        question = questions[i]

                        # Debug print to check answer data and operator number
                        # print(f"[DEBUG] Answer data: {answer_data}, Operator number: {operator_number}")

                        # Create a new answer object including the operator number
                        FormAnswer.objects.create(
                            question=question,
                            answer=answer_data,
                            operator_number=operator_number  # Store the operator number
                        )
                return response
            else:
                error_message = "There was an error with your submission. Please check your answers."
    else:
        # Generate a formset with initial data, setting up the answer options based on checkmark
        formset = AnswerFormSet(
            queryset=FormAnswer.objects.none(), 
            initial=initial_data, 
            form_kwargs={'user': request.user}  # Pass user during GET
        )

        # Debug print to verify user is being passed during initialization
        # print(f"[DEBUG] User passed to formset initialization: {request.user}")

        for form, question in zip(formset.forms, questions):
            form.__init__(question=question)  # Pass question to form for conditional field handling

    # Zip the questions and formset forms for paired rendering
    question_form_pairs = zip(questions, formset.forms)

    # Render the template
    return render(request, template_name, {
        'form_instance': form_instance,
        'question_form_pairs': question_form_pairs,
        'formset': formset,
        'error_message': error_message,
        'operator_number': operator_number,  # Pass the operator number to the template
    })




from django.shortcuts import render, get_object_or_404
from .models import Form
from collections import defaultdict
import pprint
from datetime import timedelta

def view_records(request, form_id):
    # Fetch the form instance and its questions
    form_instance = get_object_or_404(Form, id=form_id)
    questions = form_instance.questions.all()

    # Initialize a list for timestamps and the final data structure for table rows
    submission_timestamps = []
    submission_data = []

    # Collect unique timestamps and organize answers by feature
    answers_by_timestamp = defaultdict(lambda: defaultdict(lambda: None))
    for question in questions:
        for answer in question.answers.order_by("created_at"):
            # Convert UTC datetime to EST by subtracting 5 hours
            utc_timestamp = answer.created_at
            est_timestamp = utc_timestamp - timedelta(hours=5)  # UTC to EST (UTC - 5)

            # Format the EST timestamp to "YYYY-MM-DD HH:MM"
            timestamp_str = est_timestamp.strftime("%Y-%m-%d %H:%M")

            # Track unique submission timestamps in order of creation
            if timestamp_str not in submission_timestamps:
                submission_timestamps.append(timestamp_str)
            
            # Map answer by question and timestamp
            answers_by_timestamp[question.id][timestamp_str] = {
                "answer": answer.answer,
                "created_at": est_timestamp,
            }

    # Reverse sort submission timestamps to display latest submissions first
    submission_timestamps.sort(reverse=True)

    # Limit to the 10 most recent timestamps
    submission_timestamps = submission_timestamps[:48]

    # Prepare each question record for display
    for question in questions:
        row_data = {
            "feature": question.question.get("feature", "N/A"),
            "characteristic": question.question.get("characteristic", "N/A"),
            "answers": []
        }

        # Fill in answers for each submission timestamp, aligned with the correct column
        for timestamp in submission_timestamps:
            if timestamp in answers_by_timestamp[question.id]:
                answer_data = answers_by_timestamp[question.id][timestamp]
                row_data["answers"].append({
                    "answer": answer_data["answer"],
                    "created_at": answer_data["created_at"],
                    "blank": False  # Not blank if there's an answer
                })
            else:
                # Mark missing answers as blank
                row_data["answers"].append({"blank": True})

        submission_data.append(row_data)

    return render(request, 'forms/view_records.html', {
        "form_instance": form_instance,
        "submission_timestamps": submission_timestamps,
        "submission_data": submission_data,
    })





def form_by_metadata_view(request):
    # Extract query parameters
    form_type_id = request.GET.get('formtype')
    operation = request.GET.get('operation')
    part_number = request.GET.get('part_number')

    if not form_type_id or not operation or not part_number:
        return render(request, 'forms/error.html', {
            'message': 'Missing query parameters. Please provide formtype, operation, and part_number.'
        })

    form_instance = get_object_or_404(
        Form,
        form_type_id=form_type_id,
        metadata__operation=operation,
        metadata__part_number=part_number
    )

    form_type = form_instance.form_type
    template_name = f'forms/{form_type.template_name}'

    answer_form_classes = {
        'OIS': OISAnswerForm,
        'LPA': LPAAnswerForm,
    }
    answer_form_class = answer_form_classes.get(form_type.name)

    if not answer_form_class:
        raise ValueError(f"No form class defined for form type: {form_type.name}")

    questions = sorted(
        form_instance.questions.filter(
            ~Q(question__has_key='expired') | Q(question__expired=False)
        ),
        key=lambda q: q.question.get("order", 0)
    )

    AnswerFormSet = modelformset_factory(FormAnswer, form=answer_form_class, extra=len(questions))
    initial_data = [{'question': question} for question in questions]

    error_message = None
    operator_number = request.COOKIES.get('operator_number', '')

    if request.method == 'POST':
        operator_number = request.POST.get('operator_number')
        machine = request.POST.get('machine', '')

        # Capture the timestamp at the start of submission handling
        common_timestamp = timezone.now()

        formset = AnswerFormSet(
            request.POST,
            queryset=FormAnswer.objects.none(),
            form_kwargs={'user': request.user, 'machine': machine}
        )

        if not operator_number:
            error_message = "Operator number is required."
        else:
            if formset.is_valid():
                for i, form in enumerate(formset):
                    answer_data = form.cleaned_data.get('answer')
                    if answer_data:
                        # Manually set the common timestamp for all answers
                        FormAnswer.objects.create(
                            question=questions[i],
                            answer=answer_data,
                            operator_number=operator_number,
                            created_at=common_timestamp  # Same timestamp for all
                        )
                return redirect(f"{request.path}?formtype={form_type_id}&operation={operation}&part_number={part_number}")
            else:
                error_message = "There was an error with your submission."
    else:
        machine = request.GET.get('machine', '')
        formset = AnswerFormSet(
            queryset=FormAnswer.objects.none(),
            initial=initial_data,
            form_kwargs={'user': request.user, 'machine': machine}
        )

    question_form_pairs = zip(questions, formset.forms)

    return render(request, template_name, {
        'form_instance': form_instance,
        'question_form_pairs': question_form_pairs,
        'formset': formset,
        'error_message': error_message,
        'operator_number': operator_number,
    })



from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from .models import Form

def smart_form_redirect_view(request, form_id):
    form_instance = get_object_or_404(Form, id=form_id)
    
    form_type_id = form_instance.form_type_id
    operation = form_instance.metadata.get('operation')
    part_number = form_instance.metadata.get('part_number')
    
    # Only attempt metadata-based redirect if we have both operation & part_number
    if operation and part_number:
        # Check if a matching Form actually exists. If it does, we redirect to metadata‐based URL
        try:
            Form.objects.get(
                form_type_id=form_type_id,
                metadata__operation=operation,
                metadata__part_number=part_number
            )
            # If we get here, a valid Form with that metadata exists
            querystring = f"?formtype={form_type_id}&operation={operation}&part_number={part_number}"
            return redirect(reverse('form_by_metadata') + querystring)
        except Form.DoesNotExist:
            pass
    
    # Fallback to the ID-based URL
    return redirect('form_questions', form_id=form_id)




def lpa_closeout_view(request):
    from datetime import datetime
    if request.method == 'POST':
        # Process closeout submission
        answer_id = request.POST.get('answer_id')
        closeout_notes = request.POST.get('closeout_notes', '')
        closeout_date = request.POST.get('closeout_date', '')

        # Validate closeout_date
        try:
            closeout_date_parsed = datetime.strptime(closeout_date, '%Y-%m-%d') if closeout_date else None
        except ValueError:
            closeout_date_parsed = None

        if not closeout_date_parsed:
            return redirect('lpa_closeout')  # Invalid date, just refresh for now

        # Fetch the answer and update the JSON field
        try:
            answer = FormAnswer.objects.get(id=answer_id)
            updated_answer = answer.answer.copy()  # Create a copy of the JSON field
            updated_answer['closed_out'] = True
            updated_answer['closeout_date'] = closeout_date_parsed.strftime('%Y-%m-%d')  # Store the date
            if closeout_notes:
                updated_answer['closeout_notes'] = closeout_notes
            answer.answer = updated_answer
            answer.save()
        except FormAnswer.DoesNotExist:
            pass  # Handle gracefully if answer is missing

        return redirect('lpa_closeout')  # Redirect to refresh the page

    # Filter answers where closed_out != true and answer is "No"
    lpa_answers = FormAnswer.objects.filter(
        Q(answer__contains={'answer': 'No'}) & ~Q(answer__contains={'closed_out': True}),
        question__form__form_type__id=15
    ).select_related('question__form__form_type')

    # Debug: Print data to check the backend response
    print("DEBUG: Fetched answers:")
    for answer in lpa_answers:
        print(
            f"Answer ID: {answer.id}, Question ID: {answer.question.id}, "
            f"Question Text: {answer.question.question.get('question_text', 'N/A')}, "
            f"Form Name: {answer.question.form.name}, Answer Data: {answer.answer}"
        )

    # Pass the filtered answers to the template
    context = {
        'lpa_answers': lpa_answers
    }
    return render(request, 'forms/lpa_closeout.html', context)



def closed_lpas_view(request):
    from datetime import datetime
    if request.method == 'POST':
        # Handle editing closeout notes and date
        answer_id = request.POST.get('answer_id')
        closeout_notes = request.POST.get('closeout_notes', '')
        closeout_date = request.POST.get('closeout_date', '')

        # Validate closeout_date
        try:
            closeout_date_parsed = datetime.strptime(closeout_date, '%Y-%m-%d') if closeout_date else None
        except ValueError:
            closeout_date_parsed = None

        if not closeout_date_parsed:
            return redirect('closed_lpas')  # Invalid date, refresh for now

        # Fetch the answer and update the JSON field
        try:
            answer = FormAnswer.objects.get(id=answer_id)
            updated_answer = answer.answer.copy()  # Create a copy of the JSON field
            updated_answer['closeout_date'] = closeout_date_parsed.strftime('%Y-%m-%d')
            updated_answer['closeout_notes'] = closeout_notes
            answer.answer = updated_answer
            answer.save()
        except FormAnswer.DoesNotExist:
            pass  # Handle gracefully if answer is missing

        return redirect('closed_lpas')  # Redirect to refresh the page

    # Fetch answers where closed_out = true
    closed_answers = FormAnswer.objects.filter(
        answer__contains={'closed_out': True},
        question__form__form_type__id=15
    ).select_related('question__form__form_type')

    # Debugging output
    print("DEBUG: Closed LPAs fetched:")
    for answer in closed_answers:
        print(
            f"Answer ID: {answer.id}, Question ID: {answer.question.id}, "
            f"Closeout Date: {answer.answer.get('closeout_date', 'N/A')}, "
            f"Closeout Notes: {answer.answer.get('closeout_notes', 'N/A')}, "
            f"Form Name: {answer.question.form.name}"
        )

    context = {
        'closed_answers': closed_answers
    }
    return render(request, 'forms/closed_lpas.html', context)



from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import Form, FormQuestion

def create_form_copy_view(request, form_id):
    """
    View to create a copy of a form and its questions with new metadata.
    """
    print(f"[DEBUG] Entering create_form_copy_view with form_id: {form_id}")

    # Attempt to retrieve the original form
    try:
        original_form = get_object_or_404(Form, id=form_id)
        print(f"[DEBUG] Original form retrieved: {original_form}")
    except Exception as e:
        print(f"[ERROR] Could not retrieve original form: {e}")
        return JsonResponse({'error': 'Original form not found.'}, status=404)

    if request.method == 'POST':
        print("[DEBUG] Processing POST request")
        
        # Get new metadata from the request
        name = request.POST.get('name')
        part_number = request.POST.get('part_number')
        operation = request.POST.get('operation')

        print(f"[DEBUG] Received POST data: name={name}, part_number={part_number}, operation={operation}")

        # Check for missing fields
        if not name or not part_number or not operation:
            print("[ERROR] Missing required fields in POST data")
            return JsonResponse({'error': 'All fields (name, part_number, operation) are required.'}, status=400)

        try:
            # Create the new form instance with new metadata
            new_form = Form.objects.create(
                name=name,
                form_type=original_form.form_type,
                metadata={
                    'part_number': part_number,
                    'operation': operation,
                    **{k: v for k, v in original_form.metadata.items() if k not in ['part_number', 'operation']}
                }
            )
            print(f"[DEBUG] New form created: {new_form}")
        except Exception as e:
            print(f"[ERROR] Failed to create new form: {e}")
            return JsonResponse({'error': 'Failed to create a new form.'}, status=500)

        try:
            # Copy all questions from the original form to the new form
            for question in original_form.questions.all():
                FormQuestion.objects.create(
                    form=new_form,
                    question=question.question
                )
            print(f"[DEBUG] Questions copied to new form (id={new_form.id})")
        except Exception as e:
            print(f"[ERROR] Failed to copy questions: {e}")
            return JsonResponse({'error': 'Failed to copy questions to the new form.'}, status=500)

        # Return a success message
        return JsonResponse({'message': f'Successfully created a copy of the form: {new_form.name}.'}, status=200)

    return JsonResponse({'error': 'Invalid request method.'}, status=405)




from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from .models import Form, FormQuestion
from .forms import LPAQuestionForm


@csrf_exempt
def process_selected_forms(request):
    if request.method == "POST":
        print("[DEBUG] Received POST request")

        # Get form IDs and split if necessary
        raw_form_ids = request.POST.getlist('form_ids[]')
        print(f"[DEBUG] Raw form_ids: {raw_form_ids}")

        # Handle both single string and list cases
        form_ids = []
        for item in raw_form_ids:
            form_ids.extend(item.split(','))  # Split comma-separated strings into individual IDs

        print(f"[DEBUG] Parsed form_ids: {form_ids}")

        question_text = request.POST.get('question_text', '')
        what_to_look_for = request.POST.get('what_to_look_for', '')
        recommended_action = request.POST.get('recommended_action', '')
        typed_answer = request.POST.get('typed_answer', 'false') == 'true'
        expiry_date = request.POST.get('expiry_date', None)

        print(f"[DEBUG] question_text: {question_text}")
        print(f"[DEBUG] what_to_look_for: {what_to_look_for}")
        print(f"[DEBUG] recommended_action: {recommended_action}")
        print(f"[DEBUG] typed_answer: {typed_answer}")
        print(f"[DEBUG] expiry_date: {expiry_date}")

        # Ensure form IDs are provided
        if not form_ids:
            print("[ERROR] No form IDs provided")
            return JsonResponse({"error": "No forms selected."}, status=400)

        # Ensure the question text is provided
        if not question_text:
            print("[ERROR] No question text provided")
            return JsonResponse({"error": "Question text is required."}, status=400)

        # Add the question to each form
        for form_id in form_ids:
            try:
                form = Form.objects.get(id=form_id)
                print(f"[DEBUG] Found form: {form}")

                # Create the new question
                question_data = {
                    'question_text': question_text,
                    'what_to_look_for': what_to_look_for,
                    'recommended_action': recommended_action,
                    'typed_answer': typed_answer,
                    'expiry_date': expiry_date,
                }
                print(f"[DEBUG] Creating question with data: {question_data}")
                FormQuestion.objects.create(
                    form=form,
                    question=question_data,
                )
                print(f"[DEBUG] Question created for form {form_id}")

            except Form.DoesNotExist:
                print(f"[ERROR] Form with ID {form_id} does not exist")
                return JsonResponse({"error": f"Form with ID {form_id} not found."}, status=404)
            except Exception as e:
                print(f"[ERROR] Unexpected error while creating question for form {form_id}: {e}")
                return JsonResponse({"error": f"Failed to create question for form {form_id}."}, status=500)

        print("[DEBUG] All questions added successfully")
        return JsonResponse({"message": "Question added successfully!", "form_ids": form_ids})

    elif request.method == "GET":
        print("[DEBUG] Received GET request for modal form")
        form = LPAQuestionForm()  # Initialize the form
        form_html = render_to_string(
            "forms/question_form.html",  # Template to render the form
            {"form": form},
            request=request,
        )
        print("[DEBUG] Returning rendered form HTML")
        return JsonResponse({"form_html": form_html})

    else:
        print(f"[ERROR] Invalid request method: {request.method}")
        return JsonResponse({"error": "Invalid request method"}, status=400)



from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Form

@csrf_exempt
def process_form_deletion(request):
    if request.method == "POST":
        form_id = request.POST.get("form_id")
        if not form_id:
            return JsonResponse({"error": "Form ID not provided."}, status=400)

        try:
            # Retrieve the form and update its metadata
            form = Form.objects.get(id=form_id)
            form.metadata["deleted"] = True  # Add "deleted": true to metadata
            form.save()  # Save changes
            print(f"[DEBUG] Form {form_id} marked as deleted.")
            return JsonResponse({"message": f"Form {form_id} marked as deleted successfully!"})
        except Form.DoesNotExist:
            print(f"[ERROR] Form with ID {form_id} not found.")
            return JsonResponse({"error": f"Form with ID {form_id} not found."}, status=404)
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            return JsonResponse({"error": "An error occurred while marking the form as deleted."}, status=500)
    else:
        return JsonResponse({"error": "Invalid request method."}, status=400)
    









# =======================================================================
# =======================================================================
# ======================== LPA N/A Closeout =============================
# =======================================================================
# =======================================================================



def na_answers_view(request):
    if request.method == "POST":
        answer_id = request.POST.get("answer_id")
        form_answer = get_object_or_404(FormAnswer, id=answer_id)

        # Update the answer field from "N/A" to "N/A-Dealt"
        if form_answer.answer.get("answer") == "N/A":
            form_answer.answer["answer"] = "N/A-Dealt"
            form_answer.save(update_fields=["answer"])

            # Handle AJAX response if needed
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({"status": "success", "message": "Updated successfully!"})

        return redirect("na_answers_list")  # Redirect after POST

    # Define the date threshold (last 3 years)
    three_years_ago = now() - timedelta(days=3*365)  # Approximate 3 years

    # Fetch all answers marked as "N/A" from forms with form_type = 15, within last 3 years
    na_answers = (
        FormAnswer.objects
        .filter(
            answer__answer="N/A",
            question__form__form_type__id=15,
            created_at__gte=three_years_ago  # Only last 3 years
        )
        .select_related("question", "question__form")  # Optimize DB queries
        .order_by('-id')
    )

    # Substrings to exclude
    substrings_to_exclude = [
        "If a Quality alert is present, has it been signed by the Operator?",
        "If the Process Sheet refers to any Special Characteristics"
    ]

    filtered_na_answers = []

    for answer in na_answers:
        question_text = answer.question.question.get("question_text")  # Extract text from JSON field
        
        if question_text and any(substring in question_text for substring in substrings_to_exclude):
            print(f"Removing question: {question_text}")
        else:
            filtered_na_answers.append(answer)

    # print(f"Total questions removed: {len(na_answers) - len(filtered_na_answers)}")
    # print(f"Total questions kept (last 3 years): {len(filtered_na_answers)}")

    return render(request, 'forms/na_answers_list.html', {'na_answers': filtered_na_answers})







def na_dealt_answers_view(request):
    """View to list answers marked as 'N/A-Dealt' and allow recovering them back to 'N/A'."""
    if request.method == "POST":
        answer_id = request.POST.get("answer_id")
        form_answer = get_object_or_404(FormAnswer, id=answer_id)

        # Update the answer field from "N/A-Dealt" to "N/A"
        if form_answer.answer.get("answer") == "N/A-Dealt":
            form_answer.answer["answer"] = "N/A"
            form_answer.save(update_fields=["answer"])

            # Handle AJAX response if needed
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({"status": "success", "message": "Recovered successfully!"})

        return redirect("na_dealt_answers_list")  # Redirect after POST

    # Define the date threshold (last 3 years)
    three_years_ago = now() - timedelta(days=3*365)  # Approximate 3 years

    # Fetch all answers marked as "N/A-Dealt" from the last 3 years
    na_dealt_answers = (
        FormAnswer.objects
        .filter(
            answer__answer="N/A-Dealt",
            question__form__form_type__id=15,  # Ensure it's from form type 15
            created_at__gte=three_years_ago  # Limit to last 3 years
        )
        .select_related("question", "question__form")  # Optimize DB queries
        .order_by('-id')
    )

    # print(f"Total 'N/A-Dealt' questions in the last 3 years: {na_dealt_answers.count()}")

    return render(request, 'forms/na_dealt_answers_list.html', {'na_dealt_answers': na_dealt_answers})







# ===========================================================================
# ===========================================================================
# Bulk add question fix
# ===========================================================================
# ===========================================================================




def bulk_add_question_view(request):
    """
    Render a page with a question form; when submitted, add that question
    to all selected forms (appending to the end based on JSON 'order').
    """
    # Get ids from GET (first render) or POST (submit)
    raw_ids = request.GET.get('form_ids') if request.method == 'GET' else request.POST.get('form_ids')
    if not raw_ids:
        messages.error(request, "No forms selected.")
        return redirect('find_forms')

    try:
        form_ids = [int(fid) for fid in raw_ids.split(',') if fid.strip()]
    except ValueError:
        messages.error(request, "Invalid form ids.")
        return redirect('find_forms')

    # Determine form_type (from query or inferred from first form)
    form_type_id = request.GET.get('form_type') if request.method == 'GET' else request.POST.get('form_type')
    if form_type_id:
        form_type = get_object_or_404(FormType, id=form_type_id)
    else:
        first_form = get_object_or_404(Form, id=form_ids[0])
        form_type = first_form.form_type

    # Pick the right Question form class
    question_form_class = QUESTION_FORM_CLASSES.get(form_type.name)
    if not question_form_class:
        return render(request, 'forms/error.html', {
            'message': f'Form type "{form_type.name}" not supported for bulk add.'
        })

    if request.method == 'POST':
        form = question_form_class(request.POST)
        if form.is_valid():
            created_count = 0
            with transaction.atomic():
                # Fetch target forms
                targets = list(Form.objects.filter(id__in=form_ids).select_related('form_type'))
                for f in targets:
                    # Compute next order in Python from existing JSON
                    existing_orders = [
                        (q.question or {}).get('order', 0)
                        for q in f.questions.all().only('id', 'question')
                    ]
                    next_order = (max(existing_orders) if existing_orders else 0) + 1

                    # Use your question form's save() hook to build JSON and persist
                    form.save(form_instance=f, order=next_order, commit=True)
                    created_count += 1

            messages.success(request, f"Question added to {created_count} forms.")
            return redirect(f"{reverse('find_forms')}?form_type={form_type.id}")
    else:
        form = question_form_class()

    target_forms = Form.objects.filter(id__in=form_ids).select_related('form_type').order_by('-created_at')
    return render(request, 'forms/bulk_add_question.html', {
        'form': form,
        'target_forms': target_forms,
        'form_ids_csv': ",".join(str(x) for x in form_ids),
        'form_type': form_type,
    })