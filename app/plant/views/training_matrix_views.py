import pandas as pd
from django.shortcuts import render
from django.contrib import messages

def upload_shifts(request):
    if request.method == 'POST':
        uploaded = request.FILES.get('excel_file')
        if not uploaded:
            messages.error(request, "Please select a file.")
        else:
            filename = uploaded.name.lower()
            try:
                if filename.endswith('.csv'):
                    # Specify the encoding that can handle byte 0xA9
                    df = pd.read_csv(uploaded, encoding='latin-1')
                else:
                    # For real Excel files, still use openpyxl
                    df = pd.read_excel(uploaded, engine='openpyxl')
                print(df.to_string())
                messages.success(request, f"Read {len(df)} rows—check console.")
            except Exception as e:
                messages.error(request, f"Failed to read file: {e}")
    return render(request, 'plant/upload.html')
