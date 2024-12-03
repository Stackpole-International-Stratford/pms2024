from django.urls import path

from . import views

app_name = "prod_query"

urlpatterns = [
    path('index/', views.prod_query_index_view, name='prod-query_index'),
    path('', views.prod_query, name='prod-query'),
    # path('test', views.weekly_summary, name='weekly-summary'),
    path('weekly-prod', views.weekly_prod, name='weekly-prod'),
    path('rejects', views.reject_query, name='rejects'),
    path('cycle-times', views.cycle_times, name='cycle-times'),
    path('spm/', views.strokes_per_min_graph, name='strokes-per-minute'),
    path('<str:machine>/<int:start_timestamp>/<int:times>/',
         views.machine_detail, name='machine_detail'),

    path('sub-index/', views.sub_index, name='sub-index'),  # New sub-index
    path('shift-totals/', views.shift_totals_view, name='shift-totals'),  # New shift totals URL


    path('get-sc-production-data/', views.get_sc_production_data, name='get_sc_production_data'),

    path('get-sc-production-data-v2/', views.get_sc_production_data_v2, name='get_sc_production_data_v2'),

    path('oa-display/', views.oa_display, name='oa_display'),

    # Updated path for the combined downtime and production view
    path('gfx-downtime/', views.gfx_downtime_and_produced_view, name='gfx_downtime_and_produced'),

    path('pr-downtime/', views.pr_downtime_view, name='pr_downtime'),
    path('total-scrap/', views.total_scrap_view, name='total_scrap'),
    path('get-machine-data/', views.get_machine_data, name='get_machine_data'),
    path('get-scrap-lines/', views.get_scrap_lines, name='get_scrap_lines'),
    path('calculate-oa/', views.calculate_oa, name='calculate_oa'),  # New OA calculation route


    path('oa-display-v2/', views.oa_display_v2, name='oa_display_v2'),
    path('oa-byline/', views.oa_display_v2, name='oa-byline'),


]