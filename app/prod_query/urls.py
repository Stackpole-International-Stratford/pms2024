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
    path('spm', views.strokes_per_min_graph, name='strokes-per-minute'),
    path('<str:machine>/<int:start_timestamp>/<int:times>/',
         views.machine_detail, name='machine_detail'),

    path('sub-index/', views.sub_index, name='sub-index'),  # New sub-index
    path('shift-totals/', views.shift_totals_view, name='shift-totals'),  # New shift totals URL


]
