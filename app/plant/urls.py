# plant/urls.py

from django.urls import path
from .views.setupfor_views import update_part_for_asset
from .views.setupfor_views import *
from .views.password_views import (auth_page, password_list, password_create, password_edit, password_delete, password_recover, deleted_passwords)
from .views.prodmon_views import *
from .views.cycle_crud_views import *
from .views.temp_sensor_views import *

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



    path('temp-display/', temp_display, name='temp-display'),


]