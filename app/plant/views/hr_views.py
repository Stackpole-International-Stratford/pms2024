import pandas as pd
from django.shortcuts import render
from ..forms.hr_forms import UploadFileForm

def absentee_forms(request):
    data = None
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = request.FILES['file']
            # Read the first sheet into a DataFrame
            df = pd.read_excel(excel_file)

            # Make sure the column names match exactly; e.g. "Shift"
            # Filter to only rows where Shift is not empty
            df_filtered = df[df['Shift'].notna() & (df['Shift'].astype(str).str.strip() != '')]

            # Convert to a list of dicts so that the template can iterate over it
            data = df_filtered.to_dict(orient='records')
    else:
        form = UploadFileForm()

    return render(request, 'plant/absentee.html', {
        'form': form,
        'data': data
    })
