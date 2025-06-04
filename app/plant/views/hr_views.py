# views.py
import pandas as pd
from datetime import timedelta, datetime
from django.shortcuts import render
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models.functions import TruncDate    # ← changed here

from ..models.absentee_models import AbsenteeReport

@login_required(login_url='/login/')
def absentee_forms(request):
    """
    - Only users in 'hr_managers' can access.
    - On every request, compute the last 5 distinct upload‐DATES (not minutes).
    - On POST with 'delete_time', delete all AbsenteeReport rows whose uploaded_at
      falls within that chosen DAY (UTC‐converted).
    - On POST with an Excel file, bulk‐insert new rows (auto_now_add stamps exact UTC timestamp).
    """

    # 1) Ensure user is in the hr_managers group
    if not request.user.groups.filter(name="hr_managers").exists():
        return HttpResponseForbidden(
            "You are not authorized to view this page. "
            "If you need access, please contact site administrators to be added to the HR Managers group."
        )

    context = {}

    # 2) Compute the last 5 distinct upload‐DAYS:
    recent_days = (
        AbsenteeReport.objects
        .annotate(trunc_day=TruncDate('uploaded_at'))   # now truncating to DATE
        .values_list('trunc_day', flat=True)            # this yields Python date objects
        .order_by('-trunc_day')                          # newest date first
        .distinct()                                      # collapse duplicates at the day level
        [:5]
    )
    context['last_uploads'] = recent_days

    if request.method == "POST":
        # —— 3a) Handle “Delete by day” if delete_time is provided —— #
        if 'delete_time' in request.POST:
            raw_day_iso = request.POST.get('delete_time', '')  # e.g. "2025-06-04"
            try:
                # Parse the ISO‐8601 DATE string → naive datetime at local midnight
                dt_naive = datetime.fromisoformat(raw_day_iso)  # 2025-06-04 00:00:00 (naive)

                # Make it timezone‐aware in local zone (America/Toronto)
                local_tz = timezone.get_current_timezone()        # typically Settings.TIME_ZONE
                dt_local_midnight = timezone.make_aware(dt_naive, local_tz)

                # Convert that local midnight to UTC
                start_utc = dt_local_midnight.astimezone(timezone.utc)

                # Build a 24‐hour window in UTC
                end_utc = start_utc + timedelta(days=1)

                # Delete everything with uploaded_at in [start_utc, end_utc)
                deleted_count, _ = AbsenteeReport.objects.filter(
                    uploaded_at__gte=start_utc,
                    uploaded_at__lt =end_utc
                ).delete()

                context['success'] = (
                    f"Deleted {deleted_count} record(s) from upload date "
                    f"{dt_local_midnight.strftime('%Y-%m-%d')}."
                )
            except Exception:
                context['error'] = "Invalid upload‐date selected for deletion."

            # Refresh the “last_uploads” list after deletion:
            recent_days = (
                AbsenteeReport.objects
                .annotate(trunc_day=TruncDate('uploaded_at'))
                .values_list('trunc_day', flat=True)
                .order_by('-trunc_day')
                .distinct()
                [:5]
            )
            context['last_uploads'] = recent_days
            return render(request, "plant/absentee.html", context)

        # —— 3b) Otherwise, handle a new Excel‐file upload —— #
        excel_file = request.FILES.get("excel_file")
        if not excel_file:
            context["error"] = "No file was uploaded."
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

        # Refresh the “recent_days” after insertion:
        recent_days = (
            AbsenteeReport.objects
            .annotate(trunc_day=TruncDate('uploaded_at'))
            .values_list('trunc_day', flat=True)
            .order_by('-trunc_day')
            .distinct()
            [:5]
        )
        context['last_uploads'] = recent_days

        return render(request, "plant/absentee.html", context)

    # —— 4) For GET: simply render with the computed last_uploads —— #
    return render(request, "plant/absentee.html", context)
