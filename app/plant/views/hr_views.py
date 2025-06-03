# views.py
import pandas as pd
from django.shortcuts import render
from ..models.absentee_models import AbsenteeReport

def absentee_forms(request):
    if request.method == "POST":
        excel_file = request.FILES.get("excel_file")
        if excel_file:
            try:
                df = pd.read_excel(excel_file)
            except Exception as e:
                print(f"Error reading Excel file: {e}")
                return render(request, "plant/absentee.html", {
                    "error": "Could not read the uploaded file. Make sure it’s a valid .xls/.xlsx."
                })

            # Build a list of AbsenteeReport instances (but don't save yet)
            objs_to_create = []

            for idx, row in df.iterrows():
                # 1) Pull "Pay Date" and coerce to a Python date
                raw_pay_date = row.get("Pay Date")
                if pd.isna(raw_pay_date):
                    # skip any row without a valid Pay Date
                    continue

                try:
                    pay_date = pd.to_datetime(raw_pay_date).date()
                except Exception:
                    print(f"Skipping row {idx}: invalid Pay Date → {raw_pay_date}")
                    continue

                # 2) Build an instance; uploaded_at is auto‐set by auto_now_add
                obj = AbsenteeReport(
                    employee_name=                row.get("Employee Name", "").strip(),
                    job=                          row.get("Job", "").strip(),
                    pay_date=                     pay_date,
                    pay_code=                     row.get("Pay Code", "").strip(),
                    pay_category=                 row.get("Pay Category", "").strip(),
                    hours=                        row.get("Hours") if not pd.isna(row.get("Hours")) else 0,
                    pay_group_name=               row.get("Pay Group Name", "").strip(),
                    shift_rotation_description=   row.get("Shift Rotation Description", "").strip(),
                )

                objs_to_create.append(obj)

            if objs_to_create:
                # Bulk‐insert all rows at once
                AbsenteeReport.objects.bulk_create(objs_to_create)

            return render(request, "plant/absentee.html", {
                "success": f"Inserted {len(objs_to_create)} rows into AbsenteeReport."
            })

    # For GET—or if no file was posted—just render the upload form
    return render(request, "plant/absentee.html")
