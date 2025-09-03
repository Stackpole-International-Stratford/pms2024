# quality/urls.py

from django.urls import path
from .views import *
from .views import epv_table_view, manage_red_rabbit_types, red_rabbits_form, pdfs_by_part_number, change_part, mark_pdf_as_viewed, pdf_part_clock_form, pdfs_to_view, pdf_edit, pdf_delete, pdf_upload, pdf_list, add_feat, delete_feat, update_feat, update_feat_order, scrap_form_management, feat_create, feat_update, feat_delete, index, final_inspection, feat_move_up, feat_move_down, submit_scrap_form, store_supervisor_auth, forms_page, new_manager

urlpatterns = [
    path('', index, name='quality_index'),
    path('final_inspection/', forms_page),  # Redirect /final_inspection/ without part number to /forms/
    path('final_inspection/<str:part_number>/', final_inspection, name='final_inspection'),
    path('scrap_form_management/', scrap_form_management, name='scrap_form_management'),
    path('feats/new/', feat_create, name='feat_create'),
    path('feats/<int:pk>/edit/', feat_update, name='feat_update'),
    path('feats/<int:pk>/delete/', feat_delete, name='feat_delete'),
    path('feat/move_up/<int:pk>/', feat_move_up, name='feat_move_up'),
    path('feat/move_down/<int:pk>/', feat_move_down, name='feat_move_down'),
    path('submit_scrap_form/', submit_scrap_form, name='submit_scrap_form'),  # New URL for form submission
    path('store_supervisor_auth/', store_supervisor_auth, name='store_supervisor_auth'),
    path('forms/', forms_page, name='forms_page'), 
    path('new_manager/', new_manager, name='new_manager'),  # Allow access without a part_number
    path('new_manager/<str:part_number>/', new_manager, name='new_manager'),
    path('update_feat_order/', update_feat_order, name='update_feat_order'),
    path('update_feat/', update_feat, name='update_feat'),
    path('delete_feat/', delete_feat, name='delete_feat'), 
    path('add_feat/', add_feat, name='add_feat'), 

    path('pdf/upload/', pdf_upload, name='pdf_upload'),
    path('pdf/list/', pdf_list, name='pdf_list'),   
    path('pdf/edit/<int:pdf_id>/', pdf_edit, name='pdf_edit'),
    path('pdf/delete/<int:pdf_id>/', pdf_delete, name='pdf_delete'),


    path('pdf/part_clock/', pdf_part_clock_form, name='pdf_part_clock_form'),
    path('pdfs_to_view/<str:part_number>/<str:clock_numbers>/', pdfs_to_view, name='pdfs_to_view'),
    path('pdf/mark_viewed/<int:pdf_id>/<str:clock_number>/', mark_pdf_as_viewed, name='mark_pdf_as_viewed'),

    path('change_part/', change_part, name='change_part'),  # New path for change_part.html


    path('pdfs_by_part/<str:part_number>/', pdfs_by_part_number, name='pdfs_by_part_number'),

    path('red_rabbits/<str:part_number>/', red_rabbits_form, name='red_rabbits_form'),
    path('rabbits_management/', manage_red_rabbit_types, name='manage_red_rabbit_types'),

    # Add this new path
    path('epv_interface/', epv_table_view, name='epv_table_view'),

    path('fetch_all_data/', fetch_all_data, name='fetch_all_data'),
    path('delete_epv/', delete_epv, name='delete_epv'),

    path('update_asset/', update_asset, name='update_asset'),  # New URL for updating asset
    path('update_person/', update_person, name='update_person'),

    path('send_qc1_asset/', send_qc1_asset, name='send_qc1_asset'),


    path('edit_<str:column_name>/', edit_column, name='edit_column'),
    path('add_new_epv/', add_new_epv, name='add_new_epv'),

    path('scrap-entry/', scrap_entry, name='scrap_entry'),
    path('scrap-entry/get-parts/', get_parts, name='get_parts'),
    path('scrap-entry/get-machines/', get_machines,     name='get_machines'),
    path('scrap-entry/get-operations/', get_operations, name='get_operations'),
    path('scrap-entry/get-categories/', get_categories, name='get_categories'),

    


    path("tpc-requests/", tpc_request, name="tpc_request_list"),

    path("tpc-requests/new/", tpc_request_create, name="tpc_request_new"),
    path("tpc-requests/<int:pk>/approve/", tpc_request_approve, name="tpc_approve"),
    path('tpc-requests/load-more/', tpc_request_load_more, name='tpc_request_load_more'),

    path("tpc/<int:pk>/pdf/", tpc_request_pdf, name="tpc_request_pdf"),
    path("tpc-requests/<int:pk>/edit/", tpc_request_edit, name="tpc_request_edit"),


    path("tpc-requests/<int:pk>/edit/", tpc_request_edit, name="tpc_request_edit"),

    path("tpc-requests/<int:pk>/verbal/", tpc_request_verbal, name="tpc_verbal"),

    path("tpc-requests/<int:pk>/reject/", tpc_request_reject, name="tpc_reject"),


]
