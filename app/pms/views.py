from django.conf import settings
from importlib import import_module
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib import messages
from django.http import HttpRequest, HttpResponse

def login_view(request):
    if request.method == 'POST':
        # Grab exactly what the user typed
        original_username = request.POST.get('username', '')
        password = request.POST.get('password', '')

        # Debug: print before lowercasing
        # print(f"Login attempt username before lowercase: '{original_username}'")

        # Force lowercase so auto-caps on mobile won't matter
        username = original_username.lower()

        # Debug: print after lowercasing
        # print(f"Login attempt username after lowercase:  '{username}'")

        # Now authenticate with the lowercased username
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Redirect to 'next' param or fallback to home
            next_url = request.GET.get('next', '/')
            return redirect(next_url)
        else:
            messages.error(request, "Invalid login credentials. Please try again.")
            return redirect('login')

    return render(request, 'login.html')



def pms_index_view(request):
    context = {}
    context["main_heading"] = "PMS Index"
    context["title"] = "Index - pmdsdata12"
    
    app_infos = []
    for app in settings.INSTALLED_APPS:
        if app.startswith('django.') or app in ['whitenoise.runserver_nostatic', 'debug_toolbar', 'django_bootstrap5', 'widget_tweaks', 'corsheaders']:
            continue

        try:
            app_info_module = import_module(f"{app}.app_info")
            if hasattr(app_info_module, 'get_app_info'):
                app_info = app_info_module.get_app_info()
                app_infos.append(app_info)
        except ModuleNotFoundError:
            pass
        except AttributeError as e:
            pass

    context["app_infos"] = app_infos
    
    return render(request, 'index_pms.html', context)

