from ..models.visitorapp_models import *
from django.shortcuts import render




def visitor_app(request):
    return render(request, 'plant/visitor_app.html')
