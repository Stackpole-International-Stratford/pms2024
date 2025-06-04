# views.py
import pandas as pd
from datetime import timedelta, datetime
from django.shortcuts import render
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models.functions import TruncMinute

from ..models.absentee_models import AbsenteeReport

@login_required(login_url='/login/')
def absentee_forms(request):
    """
    Only users in the 'hr_managers' group can access this page. Others get a 403‐Forbidden.

    - On every request (GET or POST) we compute the last 5 distinct upload‐times TO THE MINUTE.
    - On POST with 'delete_time', we delete all AbsenteeReport rows whose uploaded_at falls
      within that chosen minute (UTC‐converted).
    - On POST with an Excel file, we bulk‐insert new rows. Because this example still uses
      auto_now_add on uploaded_at, each new row has full‐precision. But our Recent Upload Times
      list is based on a TruncMinute() annotation, so they will collapse into one minute‐level value.
    """

    # 1) Ensure user is in the hr_managers group
    if not request.user.groups.filter(name="hr_managers").exists():
        return HttpResponseForbidden(
            "You are not authorized to view this page. "
            "If you need access, please contact site administrators to be added to the HR Managers group."
        )

    context = {}

    # 2) Compute the last 5 distinct upload‐times truncated to the minute.
    recent_minutes = (
        AbsenteeReport.objects
        .annotate(trunc_min=TruncMinute('uploaded_at'))  # add a field that is uploaded_at truncated to minute
        .values_list('trunc_min', flat=True)             # pull out just that truncated‐to‐minute timestamp
        .order_by('-trunc_min')                           # sort descending, newest minute first
        .distinct()                                       # collapse duplicates at the minute level
        [:5]                                              # take the first 5 distinct minute values
    )
    context['last_uploads'] = recent_minutes

    if request.method == "POST":
        # —— 3a) Handle “Delete by minute” if delete_time is provided —— #
        if 'delete_time' in request.POST:
            raw_minute_iso = request.POST.get('delete_time', '')
            try:
                # Parse the ISO‐8601 string (e.g. "2025-06-04T12:10:00-04:00")
                dt_local_minute = datetime.fromisoformat(raw_minute_iso)
                # Convert that local (EDT/EST) minute timestamp back to UTC
                dt_utc_minute = dt_local_minute.astimezone(timezone.utc)

                # Build a one‐minute window in UTC:
                start_utc = dt_utc_minute.replace(second=0, microsecond=0)
                end_utc = start_utc + timedelta(minutes=1)

                # Delete everything with uploaded_at in [start_utc, end_utc)
                deleted_count, _ = AbsenteeReport.objects.filter(
                    uploaded_at__gte=start_utc,
                    uploaded_at__lt=end_utc
                ).delete()

                context['success'] = (
                    f"Deleted {deleted_count} record(s) from upload minute "
                    f"{dt_local_minute.strftime('%Y-%m-%d %H:%M %Z')}."
                )
            except Exception:
                context['error'] = "Invalid upload‐time selected for deletion."

            # Refresh the “last_uploads” list after deletion:
            recent_minutes = (
                AbsenteeReport.objects
                .annotate(trunc_min=TruncMinute('uploaded_at'))
                .values_list('trunc_min', flat=True)
                .order_by('-trunc_min')
                .distinct()
                [:5]
            )
            context['last_uploads'] = recent_minutes

            return render(request, "plant/absentee.html", context)

        # —— 3b) Otherwise, handle a new Excel‐file upload —— #
        excel_file = request.FILES.get("excel_file")
        if not excel_file:
            context["error"] = "No file was uploaded."
            # Re‐render with the same recent_minutes
            return render(request, "plant/absentee.html", context)

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
                continue  # skip rows without a valid Pay Date

            try:
                pay_date = pd.to_datetime(raw_pay_date).date()
            except Exception:
                print(f"Skipping row {idx}: invalid Pay Date → {raw_pay_date}")
                continue

            # Build a new AbsenteeReport instance. Because `auto_now_add=True` on uploaded_at,
            # Django will stamp each instance with the precise UTC now‐timestamp when saving.
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
            context["success"] = f"Inserted {len(objs_to_create)} row(s) into AbsenteeReport."
        else:
            context["error"] = "No valid rows found to insert."

        # Refresh the “recent_minutes” after insertion:
        recent_minutes = (
            AbsenteeReport.objects
            .annotate(trunc_min=TruncMinute('uploaded_at'))
            .values_list('trunc_min', flat=True)
            .order_by('-trunc_min')
            .distinct()
            [:5]
        )
        context['last_uploads'] = recent_minutes

        return render(request, "plant/absentee.html", context)

    # —— 4) For GET: simply render with the computed last_uploads —— #
    return render(request, "plant/absentee.html", context)
