# plant/urls.py

from django.urls import path
from .views.setupfor_views import update_part_for_asset
from .views.setupfor_views import *
from .views.password_views import (auth_page, password_list, password_create, password_edit, password_delete, password_recover, deleted_passwords)
from .views.prodmon_views import *
from .views.maintenance_views import *
from .views.cycle_crud_views import *
from .views.temp_sensor_views import *
from .views.hr_views import *

urlpatterns = [
    path('', index, name='index'),  # New index page URL


    path('plant_setupfor/', display_setups, name='display_setups'),
    path('plant_setupfor/load_more/', load_more_setups, name='load_more_setups'),
    path('plant_setupfor/update/', update_setup, name='update_setup'),
    path('plant_setupfor/add/', add_setup, name='add_setup'),
    path('plant_setupfor/check_part/', check_part, name='check_part'),


    path('assets/', display_assets, name='display_assets'),
    path('assets/create/', create_asset, name='create_asset'),
    path('assets/edit/<int:id>/', edit_asset, name='edit_asset'),
    path('assets/delete/<int:id>/', delete_asset, name='delete_asset'),
    path('parts/', display_parts, name='display_parts'),
    path('parts/create/', create_part, name='create_part'),
    path('parts/edit/<int:id>/', edit_part, name='edit_part'),
    path('parts/delete/<int:id>/', delete_part, name='delete_part'),
    path('api/fetch_part_for_asset/', fetch_part_for_asset, name='fetch_part_for_asset'),

    # passwords/urls.py
    path('password_list', password_list, name='password_list'),
    path('new/', password_create, name='password_create'),
    path('edit/<int:pk>/', password_edit, name='password_edit'),
    path('delete/<int:pk>/', password_delete, name='password_delete'),
    path('recover/<int:pk>/', password_recover, name='password_recover'),
    path('deleted/', deleted_passwords, name='deleted_passwords'),
    path('auth/', auth_page, name='auth_page'),

    path('api/update_part_for_asset/', update_part_for_asset, name='update_part_for_asset'),

    path('prodmon_ping/', prodmon_ping, name='prodmon_ping'),


    path('asset_cycle_times/', asset_cycle_times_page, name='asset_cycle_times_page'),
    path('update/asset_cycle_times/', update_asset_cycle_times_page, name='update_asset_cycle_times_page'),



    path('maintenance/form/', maintenance_form, name='maintenance_form'),
    path('maintenance/form/entries/',    maintenance_entries, name='maintenance_entries'),
    path('maintenance/delete/', delete_downtime_entry, name='delete_downtime_entry'),
    path('maintenance/closeout/', closeout_downtime_entry, name='closeout_downtime_entry'),  # ← new


    path('maintenance/join/',  join_downtime_event,  name='join_downtime_event'),
    path('maintenance/leave/', leave_downtime_event, name='leave_downtime_event'),
    path('maintenance/all/', list_all_downtime_entries,  name='maintenance_all'),
    path('downtime/load-more/', load_more_downtime_entries, name='load_more_downtime_entries'),


    path('line-priority/<int:pk>/move/<str:direction>/', move_line_priority, name='move_line_priority'),

    path('employees/add/', add_employee, name='add_employee'),

    path('downtime/<int:event_id>/history/', downtime_history, name='downtime_history'),

    path("bulk_toggle_active/", bulk_toggle_active, name="bulk_toggle_active"),


    path('maintenance/edit/', maintenance_edit, name='maintenance_edit'),
    path('maintenance/update/', maintenance_update_event, name='maintenance_update_event'),

    
    path('temp-display/', temp_display, name='temp-display'),
    path("temp-display/emails/add/", add_temp_sensor_email,   name="add-temp-sensor-email"),
    path("temp-display/emails/delete/", delete_temp_sensor_email, name="delete-temp-sensor-email"),


    path('absentee/', absentee_forms, name='absentee_forms'),


    path('downtime-codes/', downtime_codes_list, name='downtime_codes_list'),


    # AJAX CRUD
    path('downtime-codes/create/', downtime_codes_create, name='downtime_codes_create'),
    path('downtime-codes/<int:pk>/edit/',  downtime_codes_edit,   name='downtime_codes_edit'),
    path('downtime-codes/<int:pk>/delete/',downtime_codes_delete, name='downtime_codes_delete'),



    path('maintenance/machine-history/', machine_history, name='machine_history'),


    path('maintenance/employee-login-status/', employee_login_status, name='employee_login_status'),

    path('maintenance/target_lines/', target_lines, name='target_lines'),


    path("downtime/participation/<int:pk>/force-leave/", force_leave_participation, name="force_leave_participation",),


    path('maintenance/bulk_add/', maintenance_bulk_form, name='maintenance_bulk_form'),

    path('quick-add/', quick_add, name='quick_add'),

    path('hello/', hello_view, name='hello_view'),
]