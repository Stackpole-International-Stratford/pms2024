from django.urls import path

from . import views

app_name = "dashboards"

urlpatterns = [
    path('', views.dashboard_index_view, name='dashboard_index'),
    path('index/', views.dashboard_index_view, name='dashboard_index'),

    path('cell_track_9341/', views.cell_track_9341, {'target': 'desk'}, name='track9341'),
    path('cell_track_9341_TV/', views.cell_track_9341, {'target': 'tv'}, name='track9341_TV'),
    path('cell_track_9341_mobile/', views.cell_track_9341, {'target': 'mobile'}, name='track9341_mobile'),
    path('9341/', views.cell_track_9341, {'target': 'desk'}, name='9341'),
    

    path('1467/', views.cell_track_1467, {'template': 'cell_track_1467.html'}, name='1467'),
    path('cell_track_1467/', views.cell_track_1467, {'template': 'cell_track_1467.html'}, name='track1467'),

    path('trilobe/', views.cell_track_trilobe, {'template': 'cell_track_trilobe.html'}, name='trilobe'),
    path('cell_track_trilobe/', views.cell_track_trilobe, {'template': 'cell_track_trilobe.html'}, name='tracktrilobe'),

    path('8670/', views.cell_track_8670, {'template': 'cell_track_8670.html'}, name='ab1v'),
    path('cell_track_8670/', views.cell_track_8670, {'template': 'cell_track_8670.html'}, name='track8670'),
    path('track_graph_track/get/<str:index>/', views.track_graph_track, name='track_graph'),

    path('sub-index/', views.sub_index, name='sub-index'),  # New sub-index


    # New URLs for shift points
    path('shift_points/update/', views.list_and_update_shift_points, name='list_and_update_shift_points'),
    path('shift_points/<int:tv_number>/', views.display_shift_points, name='display_shift_points'),




    # Finder page
    path("rejects-dashboard/", views.rejects_dashboard_finder, name="rejects_dashboard_finder"),

    # Main dashboard: with or without a machine param
    path("rejects-dashboard/", views.rejects_dashboard, name="rejects_dashboard"),
    path("rejects-dashboard/<str:line>/", views.rejects_dashboard, name="rejects_dashboard_by_line"),





    path("dashboard/<str:page>/", views.dashboard_last_hour, name="dashboard_last_hour"),
]
