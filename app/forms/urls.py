from django.urls import path
from .views import *

urlpatterns = [
    path('', index, name='forms_index'),
    # FormType URLs
    path('formtypes/', FormTypeListView.as_view(), name='formtype_list'),
    path('formtypes/new/', FormTypeCreateView.as_view(), name='formtype_create'),
    path('formtypes/<int:pk>/edit/', FormTypeUpdateView.as_view(), name='formtype_edit'),
    path('formtypes/<int:pk>/delete/', FormTypeDeleteView.as_view(), name='formtype_delete'),

    path('create/', form_create_view, name='form_create'),
    path('edit/<int:form_id>/', form_create_view, name='form_edit'),  # Edit form URL
    path('find/', find_forms_view, name='find_forms'),  # Add this new URL


    path('bulk_question_create/', bulk_form_and_question_create_view, name='bulk_question_create'),


    path('form/<int:form_id>/', form_questions_view, name='form_questions'),
    # When the metadata is available and you want the slug in the URL:
    path('forms/form/<int:form_id>/<str:operation>/<str:partnumber>/', unified_form_view, name='unified_form'),
    # Fallback pattern when no slug is provided:
    path('forms/form/<int:form_id>/', unified_form_view, name='unified_form'),


    path('form/<int:form_id>/records/', view_records, name='view_records'),  # New URL for viewing records


    path('lpa_closeout/', lpa_closeout_view, name='lpa_closeout'),

    path('closed_lpas/', closed_lpas_view, name='closed_lpas'),


    path('na-answers/', na_answers_view, name='na_answers_list'),
    path('na-dealt-answers/', na_dealt_answers_view, name='na_dealt_answers_list'),



    path('form/<int:form_id>/create-copy/', create_form_copy_view, name='create_form_copy'),

    path('process-selected-forms/', process_selected_forms, name='process_selected_forms'),
    path('process-form-deletion/', process_form_deletion, name='process_form_deletion'),


    path('na-answers/', na_answers_view, name='na_answers_list'),
    path('na-dealt-answers/', na_dealt_answers_view, name='na_dealt_answers_list'),



    path('load_more_answers/<int:form_id>/<int:offset>/', load_more_answers, name='load_more_answers'),

    path('ois-answer-chart/', ois_answer_chart_view, name='ois_answer_chart'),

    path('out-of-spec-lockout-email-event/', out_of_spec_lockout_email_event, name='out_of_spec_lockout_email_event'),

]
