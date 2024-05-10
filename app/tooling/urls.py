from django.urls import path
from . import views
from .views import tool_report_form


app_name = "tooling"

urlpatterns = [
    path('report/', tool_report_form, name='tool_report_form'),
]
