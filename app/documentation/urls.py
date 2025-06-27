from django.urls import path
from . import views

app_name = 'documenmtation'
urlpatterns = [
    path('', views.index, name='index'),
]
