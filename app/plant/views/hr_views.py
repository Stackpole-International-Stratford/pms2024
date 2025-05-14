import pandas as pd
from django.shortcuts import render
from django.http import HttpResponse

def absentee_forms(request):
    print("⚠️ Absentee forms view hit!")
    table_html = None

    if request.method == "POST" and request.FILES.get("excel_file"):
        excel_file = request.FILES["excel_file"]
        # read into DataFrame
        try:
            df = pd.read_excel(excel_file)
            # convert to HTML table (you can style with CSS classes)
            table_html = df.to_html(classes="table table-striped", index=False)
        except Exception as e:
            return HttpResponse(f"Error reading Excel file: {e}", status=400)

    return render(request, 'plant/absentee.html', {
        'table_html': table_html
    })
