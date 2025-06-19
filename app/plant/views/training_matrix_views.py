
from django.shortcuts import render
import pandas as pd

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
    """
    Temporary view to render the manage_jobs template.
    """
    return render(request, 'plant/manage_jobs.html')