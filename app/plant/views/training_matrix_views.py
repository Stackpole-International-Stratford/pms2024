
from django.shortcuts import render
import pandas as pd

def training_matrix(request):
    """
    Temporary view to render the training_matrix template.
    """
    return render(request, 'plant/training_matrix.html')





def manage_employees(request):
    columns = []
    rows = []

    if request.method == 'POST' and request.FILES.get('file'):
        excel_file = request.FILES['file']
        df = pd.read_excel(excel_file, engine='openpyxl')
        # simple list of column names
        columns = df.columns.tolist()
        # list-of-lists of each row’s values
        rows = df.values.tolist()

    return render(request, 'plant/manage_employees.html', {
        'columns': columns,
        'rows': rows,
    })
