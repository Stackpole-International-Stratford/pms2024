# /home/tcareless/pms2024/app/plant/views/maintenance_views.py

from django.shortcuts import render
from django.http import HttpRequest, HttpResponse

def maintenance_form(request: HttpRequest) -> HttpResponse:
    """
    A placeholder view for the maintenance form.
    Renders a simple 'Hello, world!' message.
    """
    # you could pass a form instance or context here later
    context = {
        'message': 'Hello, world! This is the maintenance form.'
    }
    return render(request, 'plant/maintenance_form.html', context)
