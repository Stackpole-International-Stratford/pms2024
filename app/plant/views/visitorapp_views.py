# plant/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from ..forms.visitorapp_forms import *
import base64

def visitor_app(request):
    if request.method == "POST":
        form = VisitorLogForm(request.POST, request.FILES)
        if form.is_valid():
            # Save the log (no image saved in DB)
            visitor_log = form.save(commit=False)
            visitor_log.save()
            form.save_m2m()

            # Receive but discard image
            received_photo = False

            # Option 1: standard file upload
            file_obj = form.cleaned_data.get("photo")
            if file_obj:
                # Read and discard
                _ = file_obj.read()
                received_photo = True

            # Option 2: base64 captured data from camera
            data_url = form.cleaned_data.get("photo_data")
            if data_url and data_url.startswith("data:image"):
                try:
                    _, b64 = data_url.split(",", 1)
                    _ = base64.b64decode(b64)  # decode then discard
                    received_photo = True
                except Exception:
                    pass

            messages.success(
                request,
                "Thanks! Your visit has been logged. " + ("Photo received." if received_photo else "No photo received.")
            )
            return redirect("visitor_app")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = VisitorLogForm()

    return render(request, "plant/visitor_app.html", {"form": form})
