from django.urls import path
from .views import *


urlpatterns = [
    path('', hellworld, name='hello_world'),
]
