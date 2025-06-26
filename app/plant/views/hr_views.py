# views.py

from datetime import datetime, timedelta, time
from django.shortcuts import render
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models.functions import TruncDate
import pandas as pd
from ..models.absentee_models import AbsenteeReport

@login_required(login_url='/login/')
def absentee_forms(request):
    """
    Display and manage absentee report uploads for HR managers.

    This view supports:
      - GET: Render the absentee upload page with:
        • `last_uploads`: the five most recent distinct upload dates (YYYY-MM-DD).
        • `today`: the server’s local date (YYYY-MM-DD) for default form input.
      - POST with `delete_time`: Delete all AbsenteeReport records whose
        `uploaded_at` timestamp falls on the specified date (UTC-converted),
        then re-render with an updated `last_uploads` list and a success or error message.
      - POST with an Excel file (`excel_file`) and `upload_date`: Parse the file
        into AbsenteeReport rows, assign each row’s `uploaded_at` to the chosen
        date (midnight local→UTC), bulk-insert valid rows, then re-render with
        updated `last_uploads` and a success or error message.

    Access Control
    --------------
    Only users in the “hr_managers” group may access this view;
    others receive HTTP 403 Forbidden.

    Parameters
    ----------
    request : django.http.HttpRequest
        The HTTP request object. For POST, may include:
          - `delete_time` (str): ISO date "YYYY-MM-DD" for deletion.
          - `excel_file` (UploadedFile): Excel workbook of absentee data.
          - `upload_date` (str): ISO date "YYYY-MM-DD" to stamp new rows.

    Returns
    -------
    django.http.HttpResponse
        Renders "plant/absentee.html" with context keys:
          - `last_uploads`: list of up to five date objects.
          - `today`: string default date for file uploads.
          - `success` or `error`: feedback messages on POST operations.
    """
    """
    - Only users in 'hr_managers' can access.
    - On every request, compute the last 5 distinct upload‐DATES (not minutes).
    - On POST with 'delete_time', delete all AbsenteeReport rows whose uploaded_at
      falls within that chosen DAY (UTC‐converted).
    - On POST with an Excel file, bulk‐insert new rows and stamp each row’s uploaded_at
      with the user’s chosen date (in UTC).
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
        .annotate(trunc_day=TruncDate('uploaded_at'))
        .values_list('trunc_day', flat=True)    # yields Python date objects
        .order_by('-trunc_day')                  # newest date first
        .distinct()                              # collapse duplicates at day level
        [:5]
    )
    context['last_uploads'] = recent_days

    # 2a) Provide “today” (in YYYY-MM-DD) so the template’s <input type="date"> can default
    today_local_date = timezone.localdate()       # e.g. date(2025, 6, 4) in America/Toronto
    context['today'] = today_local_date.isoformat()  # e.g. "2025-06-04"

    if request.method == "POST":
        # —— 3a) If delete_time is posted, delete that entire day’s records —— #
        if 'delete_time' in request.POST:
            raw_day_iso = request.POST.get('delete_time', '')  # e.g. "2025-06-03"
            try:
                # 3a.1) Parse "YYYY-MM-DD" into naive midnight
                dt_naive = datetime.fromisoformat(raw_day_iso)  # 2025-06-03 00:00:00

                # 3a.2) Localize to the server’s timezone (America/Toronto)
                local_tz = timezone.get_current_timezone()
                dt_local_midnight = timezone.make_aware(dt_naive, local_tz)

                # 3a.3) Convert local midnight → UTC
                start_utc = dt_local_midnight.astimezone(timezone.utc)

                # 3a.4) Build a 24-hour window in UTC
                end_utc = start_utc + timedelta(days=1)

                # 3a.5) Delete all rows whose uploaded_at falls in [start_utc, end_utc)
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

            # 3a.6) Refresh the “last_uploads” list
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

        # 3b.1) Try reading the Excel
        try:
            df = pd.read_excel(excel_file)
        except Exception as e:
            print(f"Error reading Excel file: {e}")
            context["error"] = "Could not read the uploaded file. Make sure it’s a valid .xls/.xlsx."
            return render(request, "plant/absentee.html", context)

        # 3b.2) Read and parse the “upload_date” from the form
        raw_date_str = request.POST.get("upload_date", "")
        try:
            # Parse "YYYY-MM-DD" → naive datetime at midnight
            dt_naive = datetime.fromisoformat(raw_date_str)  # e.g. 2025-06-04 00:00:00 (naive)
            local_tz = timezone.get_current_timezone()
            dt_local_midnight = timezone.make_aware(dt_naive, local_tz)
            # Convert that local midnight to UTC
            chosen_upload_utc = dt_local_midnight.astimezone(timezone.utc)
        except Exception:
            # If they typed an invalid date, fallback to “now”
            chosen_upload_utc = timezone.now()

        # 3b.3) Build AbsenteeReport objects, assigning uploaded_at = chosen_upload_utc
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
                uploaded_at=                chosen_upload_utc,    # ← assign the chosen date/time in UTC
            )
            objs_to_create.append(report)

        # 3b.4) Bulk‐insert
        if objs_to_create:
            AbsenteeReport.objects.bulk_create(objs_to_create)
            context["success"] = (
                f"Inserted {len(objs_to_create)} row(s) into AbsenteeReport "
                f"with upload date {chosen_upload_utc.astimezone(timezone.get_current_timezone()).strftime('%Y-%m-%d')}."
            )
        else:
            context["error"] = "No valid rows found to insert."

        # 3b.5) Refresh the “last_uploads” list after insertion
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

    # —— 4) GET: just render with last_uploads + today —— #
    return render(request, "plant/absentee.html", context)
