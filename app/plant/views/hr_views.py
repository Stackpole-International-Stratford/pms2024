# views.py

from datetime import datetime, timedelta, time
from django.shortcuts import render
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models.functions import TruncDate
import pandas as pd
from ..models.absentee_models import AbsenteeReport
from django.db import transaction


@login_required(login_url='/login/')
def absentee_forms(request):
    """
    - Only users in 'hr_managers' can access.
    - On every request, compute the last 5 distinct upload-DATES (not minutes).
    - On POST with 'delete_time', delete all AbsenteeReport rows whose uploaded_at
      falls within that chosen DAY (UTC-converted).
    - On POST with an Excel file, bulk-insert new rows and stamp each row’s uploaded_at
      with the user’s chosen date (in UTC).
    """
    # ----- Guard: group membership -----
    if not request.user.groups.filter(name="hr_managers").exists():
        return HttpResponseForbidden(
            "You are not authorized to view this page. "
            "If you need access, please contact site administrators to be added to the HR Managers group."
        )

    context = {}

    # ----- Last 5 distinct upload DAYS -----
    recent_days = (
        AbsenteeReport.objects
        .annotate(trunc_day=TruncDate('uploaded_at'))
        .values_list('trunc_day', flat=True)
        .order_by('-trunc_day')
        .distinct()[:5]
    )
    context['last_uploads'] = recent_days

    # Default value for <input type="date">
    context['today'] = timezone.localdate().isoformat()

    # ---------- Helpers ----------
    def to_clean_str(v) -> str:
        """Return a trimmed string; treat None/NaN/<NA> as empty string."""
        try:
            if pd.isna(v):
                return ""
        except Exception:
            if v is None:
                return ""
        return str(v).strip()

    def parse_local_midnight_to_utc(day_iso: str):
        """Parse 'YYYY-MM-DD' at local midnight; return (start_utc, end_utc, local_midnight_dt)."""
        dt_naive = datetime.fromisoformat(day_iso)  # 00:00 local, naive
        local_tz = timezone.get_current_timezone()
        dt_local_midnight = timezone.make_aware(dt_naive, local_tz)
        start_utc = dt_local_midnight.astimezone(timezone.utc)
        end_utc = start_utc + timedelta(days=1)
        return start_utc, end_utc, dt_local_midnight

    # ---------- POST ----------
    if request.method == "POST":
        # 3a) Delete a whole day's uploads
        if 'delete_time' in request.POST:
            raw_day_iso = (request.POST.get('delete_time') or "").strip()
            try:
                start_utc, end_utc, dt_local_midnight = parse_local_midnight_to_utc(raw_day_iso)
                deleted_count, _ = AbsenteeReport.objects.filter(
                    uploaded_at__gte=start_utc,
                    uploaded_at__lt=end_utc
                ).delete()
                context['success'] = (
                    f"Deleted {deleted_count} record(s) from upload date "
                    f"{dt_local_midnight.strftime('%Y-%m-%d')}."
                )
            except Exception:
                context['error'] = "Invalid upload-date selected for deletion."

            # refresh last_uploads
            context['last_uploads'] = (
                AbsenteeReport.objects
                .annotate(trunc_day=TruncDate('uploaded_at'))
                .values_list('trunc_day', flat=True)
                .order_by('-trunc_day')
                .distinct()[:5]
            )
            return render(request, "plant/absentee.html", context)

        # 3b) New Excel upload
        excel_file = request.FILES.get("excel_file")
        if not excel_file:
            context["error"] = "No file was uploaded."
            return render(request, "plant/absentee.html", context)

        # 3b.1) Read Excel
        try:
            df = pd.read_excel(excel_file)
        except Exception as e:
            print(f"Error reading Excel file: {e}")
            context["error"] = "Could not read the uploaded file. Make sure it’s a valid .xls/.xlsx."
            return render(request, "plant/absentee.html", context)

        # 3b.1a) Normalize headers
        df.columns = [str(c).strip() for c in df.columns]

        # 3b.1b) Pre-clean text columns to GUARANTEE strings (no .strip() on floats)
        TEXT_COLS = [
            "Employee Name", "Job", "Pay Code", "Pay Category",
            "Pay Group Name", "Shift Rotation Description"
        ]
        for col in TEXT_COLS:
            if col in df.columns:
                df[col] = df[col].apply(to_clean_str)

        # 3b.1c) Hours → numeric (bad/missing -> 0)
        if "Hours" in df.columns:
            df["Hours"] = pd.to_numeric(df["Hours"], errors="coerce").fillna(0)
        else:
            df["Hours"] = 0

        # 3b.2) Parse chosen upload date (stamp as UTC)
        raw_date_str = (request.POST.get("upload_date") or "").strip()
        try:
            dt_naive = datetime.fromisoformat(raw_date_str)
            local_tz = timezone.get_current_timezone()
            dt_local_midnight = timezone.make_aware(dt_naive, local_tz)
            chosen_upload_utc = dt_local_midnight.astimezone(timezone.utc)
        except Exception:
            chosen_upload_utc = timezone.now()

        # 3b.3) Build model instances safely
        objs_to_create = []
        for idx, row in df.iterrows():
            # Pay Date can be Excel serial, datetime, or string; coerce robustly
            pay_dt = pd.to_datetime(row.get("Pay Date"), errors="coerce")
            if pd.isna(pay_dt):
                # Skip rows that don't have a valid date
                continue
            pay_date = pay_dt.date()

            report = AbsenteeReport(
                employee_name=              to_clean_str(row.get("Employee Name")),
                job=                        to_clean_str(row.get("Job")),
                pay_date=                   pay_date,
                pay_code=                   to_clean_str(row.get("Pay Code")),
                pay_category=               to_clean_str(row.get("Pay Category")),  # e.g. "Hol1.0" preserved
                hours=                      float(row.get("Hours", 0)) if not pd.isna(row.get("Hours", 0)) else 0.0,
                pay_group_name=             to_clean_str(row.get("Pay Group Name")),
                shift_rotation_description= to_clean_str(row.get("Shift Rotation Description")),
                uploaded_at=                chosen_upload_utc,
            )
            objs_to_create.append(report)

        # 3b.4) Bulk insert atomically
        if objs_to_create:
            with transaction.atomic():
                AbsenteeReport.objects.bulk_create(objs_to_create, ignore_conflicts=False)
            local_tz = timezone.get_current_timezone()
            context["success"] = (
                f"Inserted {len(objs_to_create)} row(s) into AbsenteeReport "
                f"with upload date {chosen_upload_utc.astimezone(local_tz).strftime('%Y-%m-%d')}."
            )
        else:
            context["error"] = "No valid rows found to insert."

        # 3b.5) Refresh last_uploads
        context['last_uploads'] = (
            AbsenteeReport.objects
            .annotate(trunc_day=TruncDate('uploaded_at'))
            .values_list('trunc_day', flat=True)
            .order_by('-trunc_day')
            .distinct()[:5]
        )
        return render(request, "plant/absentee.html", context)

    # ---------- GET ----------
    return render(request, "plant/absentee.html", context)