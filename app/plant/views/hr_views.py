# plant/views/hr_views.py
from datetime import datetime, timedelta

import pandas as pd
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models.functions import TruncDate
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone

# IMPORTANT: import both models
from ..models.absentee_models import *


def _norm_code(val) -> str:
    """
    Normalize a pay code for matching:
    - None / NaN / '' -> ''
    - strip whitespace
    - uppercase
    - collapse internal whitespace (optional, helps with weird exports)
    """
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except Exception:
        pass
    s = str(val).strip()
    if not s:
        return ""
    # If you want to preserve internal spaces, remove the next line.
    s = " ".join(s.split())
    return s.upper()


@login_required(login_url='/login/')
def absentee_forms(request):
    """
    - Only users in 'hr_managers' can access.
    - Always compute the last 5 distinct upload DATES (day-level).
    - POST with 'delete_time': delete all AbsenteeReport rows uploaded on that local day (converted to UTC bounds).
    - POST with Excel file: bulk-insert rows, stamping uploaded_at with the user-chosen local date (stored as UTC).
    - Pay Code → (pay_group, is_scheduled) via PayCodeGroup (case-insensitive, trimmed).
    - Shift Rotation Description → shift via ShiftRotationMap (case-insensitive, trimmed).
      Leave derived fields blank/NULL when there is no mapping.
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
        """Return trimmed string; treat None/NaN/<NA> as empty string."""
        try:
            if pd.isna(v):
                return ""
        except Exception:
            if v is None:
                return ""
        return str(v).strip()

    def parse_local_midnight_to_utc(day_iso: str):
        """
        Parse 'YYYY-MM-DD' at local midnight and return:
        (start_utc, end_utc, local_midnight_dt)
        """
        dt_naive = datetime.fromisoformat(day_iso)  # 00:00 local, naive
        local_tz = timezone.get_current_timezone()
        dt_local_midnight = timezone.make_aware(dt_naive, local_tz)
        start_utc = dt_local_midnight.astimezone(timezone.utc)
        end_utc = start_utc + timedelta(days=1)
        return start_utc, end_utc, dt_local_midnight

    def refresh_recent_days():
        return (
            AbsenteeReport.objects
            .annotate(trunc_day=TruncDate('uploaded_at'))
            .values_list('trunc_day', flat=True)
            .order_by('-trunc_day')
            .distinct()[:5]
        )

    # ---------- POST ----------
    if request.method == "POST":

        # 1) Delete a whole day's uploads
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

            context['last_uploads'] = refresh_recent_days()
            return render(request, "plant/absentee.html", context)

        # 2) New Excel upload
        excel_file = request.FILES.get("excel_file")
        if not excel_file:
            context["error"] = "No file was uploaded."
            return render(request, "plant/absentee.html", context)

        # 2a) Read Excel → DataFrame
        try:
            df = pd.read_excel(excel_file)
        except Exception as e:
            print(f"Error reading Excel file: {e}")
            context["error"] = "Could not read the uploaded file. Make sure it’s a valid .xls/.xlsx."
            return render(request, "plant/absentee.html", context)

        # Normalize headers
        df.columns = [str(c).strip() for c in df.columns]

        # Pre-clean text columns so we can safely .strip()
        TEXT_COLS = [
            "Employee Name", "Job", "Pay Code", "Pay Category",
            "Pay Group Name", "Shift Rotation Description"
        ]
        for col in TEXT_COLS:
            if col in df.columns:
                df[col] = df[col].apply(to_clean_str)

        # Hours → numeric (bad/missing -> 0)
        if "Hours" in df.columns:
            df["Hours"] = pd.to_numeric(df["Hours"], errors="coerce").fillna(0)
        else:
            df["Hours"] = 0

        # 2b) Parse chosen upload date (stamp as UTC)
        raw_date_str = (request.POST.get("upload_date") or "").strip()
        try:
            dt_naive = datetime.fromisoformat(raw_date_str)
            local_tz = timezone.get_current_timezone()
            dt_local_midnight = timezone.make_aware(dt_naive, local_tz)
            chosen_upload_utc = dt_local_midnight.astimezone(timezone.utc)
        except Exception:
            chosen_upload_utc = timezone.now()

        # 2c) Build in-memory mapping dicts (normalized keys)
        # Pay Code → (group_name, is_scheduled)
        code_map = {
            _norm_code(code): (grp, is_sched)
            for code, grp, is_sched in PayCodeGroup.objects.values_list(
                "pay_code", "group_name", "is_scheduled"
            )
        }

        # Shift Rotation Description → shift
        # NOTE: import ShiftRotationMap at top of file:
        # from ..models import ShiftRotationMap
        try:
            shift_map = {
                _norm_code(rotation_text): shift
                for rotation_text, shift in ShiftRotationMap.objects.values_list("rotation_text", "shift")
            }
        except NameError:
            # If ShiftRotationMap hasn't been imported or created yet, fall back gracefully.
            shift_map = {}

        # 2d) Build model instances
        objs_to_create = []
        for _, row in df.iterrows():
            # Pay Date can be Excel serial, datetime, or string; coerce robustly
            pay_dt = pd.to_datetime(row.get("Pay Date"), errors="coerce")
            if pd.isna(pay_dt):
                # Skip rows that don't have a valid date
                continue
            pay_date = pay_dt.date()

            # Pay code mapping
            raw_code = to_clean_str(row.get("Pay Code"))
            norm_code = _norm_code(raw_code)
            code_mapping = code_map.get(norm_code)  # None if not found

            # Shift rotation mapping
            raw_rotation = to_clean_str(row.get("Shift Rotation Description"))
            norm_rotation = _norm_code(raw_rotation)
            mapped_shift = shift_map.get(norm_rotation)  # None if not found

            report = AbsenteeReport(
                employee_name=              to_clean_str(row.get("Employee Name")),
                job=                        to_clean_str(row.get("Job")),
                pay_date=                   pay_date,
                pay_code=                   raw_code,
                pay_category=               to_clean_str(row.get("Pay Category")),
                hours=                      float(row.get("Hours", 0)) if not pd.isna(row.get("Hours", 0)) else 0.0,
                pay_group_name=             to_clean_str(row.get("Pay Group Name")),
                shift_rotation_description= raw_rotation,
                uploaded_at=                chosen_upload_utc,

                # Derived from PayCodeGroup (if present)
                pay_group=                  code_mapping[0] if code_mapping else None,
                is_scheduled=               code_mapping[1] if code_mapping else None,

                # Derived from ShiftRotationMap (if present)
                shift=                      mapped_shift if mapped_shift else None,
            )
            objs_to_create.append(report)

        # 2e) Bulk insert atomically
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

        # Refresh day list after changes
        context['last_uploads'] = refresh_recent_days()
        return render(request, "plant/absentee.html", context)

    # ---------- GET ----------
    return render(request, "plant/absentee.html", context)
