
from django.shortcuts import render, redirect
import pandas as pd
from django.shortcuts import get_object_or_404
from ..models.training_matrix_models import *
from django.views.decorators.http import require_POST
from django.http import JsonResponse

def training_matrix(request):
    """
    Temporary view to render the training_matrix template.
    """
    return render(request, 'plant/training_matrix.html')




def manage_employees(request):
    # your four hard-coded headers
    columns = ["Employee", "Department", "Status", "Shift Rotation Name"]
    rows    = []

    if request.method == 'POST' and request.FILES.get('file'):
        f = request.FILES['file']

        # 1) Read columns A–D with no header detection
        df = pd.read_excel(
            f,
            engine='openpyxl',
            header=None,
            usecols=[0, 1, 2, 3],
        )

        # 2) Drop any rows where *all* values are NaN
        df = df.dropna(how='all').reset_index(drop=True)

        # 3) If the first non-blank row matches your headers, drop it
        first = df.iloc[0].astype(str).tolist()
        if first == columns:
            df = df.iloc[1:].reset_index(drop=True)

        # 4) Turn what's left into a list-of-lists for the template
        rows = df.values.tolist()

    return render(request, 'plant/manage_employees.html', {
        'columns': columns,
        'rows':    rows,
    })





def training_jobs(request):
    jobs = TrainingJob.objects.all().order_by('area', 'line', 'operation')
    # pull the AREA_CHOICES into context
    area_choices = TrainingJob.AREA_CHOICES
    return render(request, 'plant/manage_jobs.html', {
        'jobs': jobs,
        'area_choices': area_choices,
    })



@require_POST
def add_job(request):
    # grab fields manually from POST
    area        = request.POST.get("area")
    line        = request.POST.get("line")
    operation   = request.POST.get("operation")
    description = request.POST.get("description")

    # basic validation
    if not all([area, line, operation, description]):
        return JsonResponse({
            "success": False,
            "errors": "All fields (area, line, operation, description) are required."
        }, status=400)

    # create the job
    job = TrainingJob.objects.create(
        area=area,
        line=line,
        operation=operation,
        description=description,
    )

    # return the minimal data we need to render a new row
    return JsonResponse({
        "success": True,
        "job": {
            "id":            job.id,
            "area_display":  job.get_area_display(),
            "line":          job.line,
            "operation":     job.operation,
            "description":   job.description,
            "created_at":    job.created_at.strftime("%Y-%m-%d %H:%M"),
            "updated_at":    job.updated_at.strftime("%Y-%m-%d %H:%M"),
        }
    })




@require_POST
def edit_job(request, job_id):
    job = get_object_or_404(TrainingJob, id=job_id)
    # grab fields
    area        = request.POST.get("area")
    line        = request.POST.get("line")
    operation   = request.POST.get("operation")
    description = request.POST.get("description")
    # simple validation (you can expand this)
    if not all([area, line, operation, description]):
        return JsonResponse({"success": False, "errors": "All fields required."}, status=400)
    # update + save
    job.area        = area
    job.line        = line
    job.operation   = operation
    job.description = description
    job.save()
    # return updated row data
    return JsonResponse({
        "success": True,
        "job": {
            "id":            job.id,
            "area_display":  job.get_area_display(),
            "line":          job.line,
            "operation":     job.operation,
            "description":   job.description,
            "updated_at":    job.updated_at.strftime("%Y-%m-%d %H:%M"),
        }
    })