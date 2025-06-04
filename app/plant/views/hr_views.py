# views.py
import pandas as pd
from django.shortcuts import render
from ..models.absentee_models import AbsenteeReport

def absentee_forms(request):
    """
    Handle the upload of an Excel file containing absentee data.
    On POST: read the file, parse each row, and bulk‐insert into AbsenteeReport.
    On GET: simply render the upload form.
    """
    context = {}

    if request.method == "POST":
        excel_file = request.FILES.get("excel_file")
        if not excel_file:
            context["error"] = "No file was uploaded."
            return render(request, "plant/absentee.html", context)

        # Attempt to read the Excel file into a DataFrame
        try:
            df = pd.read_excel(excel_file)
        except Exception as e:
            print(f"Error reading Excel file: {e}")
            context["error"] = "Could not read the uploaded file. Make sure it’s a valid .xls/.xlsx."
            return render(request, "plant/absentee.html", context)

        objs_to_create = []
        for idx, row in df.iterrows():
            raw_pay_date = row.get("Pay Date")
            if pd.isna(raw_pay_date):
                continue  # Skip rows without a valid Pay Date

            try:
                pay_date = pd.to_datetime(raw_pay_date).date()
            except Exception:
                print(f"Skipping row {idx}: invalid Pay Date → {raw_pay_date}")
                continue

            # Build a new AbsenteeReport instance. uploaded_at will be auto‐set.
            report = AbsenteeReport(
                employee_name=              (row.get("Employee Name") or "").strip(),
                job=                        (row.get("Job") or "").strip(),
                pay_date=                   pay_date,
                pay_code=                   (row.get("Pay Code") or "").strip(),
                pay_category=               (row.get("Pay Category") or "").strip(),
                hours=                      row.get("Hours") if not pd.isna(row.get("Hours")) else 0,
                pay_group_name=             (row.get("Pay Group Name") or "").strip(),
                shift_rotation_description= (row.get("Shift Rotation Description") or "").strip(),
            )
            objs_to_create.append(report)

        if objs_to_create:
            AbsenteeReport.objects.bulk_create(objs_to_create)
            context["success"] = f"Inserted {len(objs_to_create)} rows into AbsenteeReport."
        else:
            context["error"] = "No valid rows found to insert."

        return render(request, "plant/absentee.html", context)

    # For GET requests, just render the upload form
    return render(request, "plant/absentee.html")
