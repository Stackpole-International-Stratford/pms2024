import json
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse, HttpResponseRedirect
from datetime import datetime
from ..models.maintenance_models import MachineDowntimeEventTEST, LinePriority, DowntimeParticipation, DowntimeCode, DowntimeMachine
from django.http import JsonResponse
from django.utils import timezone
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.db import transaction
from django.db.models import OuterRef, Subquery, IntegerField, Value
from django.db.models.functions import Coalesce
import time
from django.contrib import messages
from requests.exceptions import Timeout, RequestException
from django.contrib.auth.models import Group
from django.utils.crypto import get_random_string
from django.conf import settings
from django.http        import HttpResponseForbidden
import math
from django.utils.timezone import is_naive, make_aware, get_default_timezone, utc, localtime
from django.db.models import Exists, OuterRef
from django.db.models import Q
# import your lines structure
from prod_query.views import lines as prod_lines_initial
from django.views.decorators.csrf import csrf_exempt  # or use @ensure_csrf_cookie / csrf_protect
from django.template.loader import render_to_string
from django.db.models import Exists, OuterRef, Case, When, Value, BooleanField
import copy
import csv
from django.utils.encoding import smart_str
from collections import OrderedDict
from django.contrib.auth.decorators import user_passes_test
from django.utils.dateparse import parse_datetime
import re
import requests


# ============================================================================
# ============================================================================
# ============================================================================
# ============================================================================
'''
You may wonder what this is. It's fetching all the lines and operations and machines from the table and stuffing it into prod_lines so the rest of the code views/functions
can use it. Before we had this, we had it in 2 separate json objects, which was not sustainable so now in a table we can CRUD machines from the admin panel no problem.
'''

def get_prod_lines():
    """
    Return a list of { line, scrap_line, operations:[ { op, machines:[{number,target}] } ] }
    built fresh from the DowntimeMachine table.
    """
    _by_name = {}

    for dm in DowntimeMachine.objects.all():
        # 1) ensure the line‐block
        blk = _by_name.setdefault(
            dm.line,
            {
                'line':       dm.line,
                'scrap_line': dm.line,
                'operations': []
            }
        )

        # 2) find or create this op
        ops = blk['operations']
        op_entry = next((o for o in ops if o['op'] == dm.operation), None)
        machine_dict = {
            'number': dm.machine_number,
            'target': None    # or dm.target if you’ve extended the model
        }

        if op_entry:
            op_entry['machines'].append(machine_dict)
        else:
            ops.append({
                'op':       dm.operation,
                'machines': [machine_dict]
            })

    return list(_by_name.values())


# ============================================================================
# ============================================================================
# ============================================================================
# ============================================================================


@require_POST
def delete_downtime_entry(request):
    try:
        payload = json.loads(request.body)
        entry_id = payload['entry_id']
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    # fetch only non-deleted events
    try:
        e = MachineDowntimeEventTEST.objects.get(pk=entry_id, is_deleted=False)
    except MachineDowntimeEventTEST.DoesNotExist:
        return HttpResponseBadRequest("Entry not found")

    # ✏️ NEW: ensure no open participants
    if DowntimeParticipation.objects.filter(event=e, leave_epoch__isnull=True).exists():
        return HttpResponseForbidden("Cannot delete until all participants have left.")

    # soft-delete
    e.is_deleted = True
    e.deleted_at = timezone.now()
    e.save(update_fields=['is_deleted', 'deleted_at'])

    return JsonResponse({'status': 'ok'})




@require_POST
def closeout_downtime_entry(request):
    """
    Close out a downtime event *only* when every participant has already left.
    Expects JSON body:
      {
        "entry_id":         <int>,
        "closeout":         "YYYY-MM-DD HH:MM",
        "closeout_comment": <string>
      }
    """
    # 1) payload
    try:
        p             = json.loads(request.body)
        entry_id      = p["entry_id"]
        naive_dt      = datetime.strptime(p["closeout"], "%Y-%m-%d %H:%M")
        close_comment = p["closeout_comment"].strip()
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    # 2) fetch event
    event = get_object_or_404(
        MachineDowntimeEventTEST,
        pk=entry_id,
        is_deleted=False,
        closeout_epoch__isnull=True
    )

    # 3) ensure no open participants
    if DowntimeParticipation.objects.filter(event=event, leave_epoch__isnull=True).exists():
        return HttpResponseForbidden("Cannot close out until all participants have left.")

    # 4) localize and convert to UTC epoch
    local_tz    = timezone.get_current_timezone()  # America/Toronto
    aware_local = timezone.make_aware(naive_dt, local_tz)
    epoch_ts    = int(aware_local.astimezone(timezone.utc).timestamp())

    # 5) sanity check: must be after the start
    if epoch_ts <= event.start_epoch:
        return HttpResponseBadRequest("Close-out time must be after the start time.")

    # 6) save
    event.closeout_epoch   = epoch_ts
    event.closeout_comment = close_comment
    event.save(update_fields=["closeout_epoch", "closeout_comment"])

    return JsonResponse({"status": "ok", "closed_at_epoch": epoch_ts})





def maintenance_entries(request: HttpRequest) -> JsonResponse:
    """
    Returns a page of open MachineDowntimeEventTEST entries plus:
      - has_more: whether there are more to load
      - is_guest: true if the user is anonymous (not logged in)
    """
    # paging params
    offset    = int(request.GET.get('offset', 0))
    page_size = 300

    # only live, un‐closed events
    qs = MachineDowntimeEventTEST.objects.filter(
        is_deleted=False,
        closeout_epoch__isnull=True
    ).order_by('-start_epoch')

    total = qs.count()
    batch = qs[offset: offset + page_size]

    entries = [
        {
            'id'               : e.id,
            'start_at'         : e.start_at.strftime('%Y-%m-%d %H:%M'),
            'line'             : e.line,
            'machine'          : e.machine,
            'category'         : e.category,
            'subcategory'      : e.subcategory,
            'code'             : e.code,
            'category_code'    : e.code.split('-', 1)[0],
            'subcategory_code' : e.code,
            'comment'          : e.comment,
            'labour_types'      : e.labour_types,
            'employee_id'      : e.employee_id,         # ← optional, if you ever need it

        }
        for e in batch
    ]
    has_more = (offset + page_size) < total
    is_guest = request.user.is_anonymous

    return JsonResponse({
        'entries' : entries,
        'has_more': has_more,
        'is_guest': is_guest,
    })








# ==================================================================================
# ==================================================================================
# =============================== Maintenance App ==================================
# ==================================================================================
# ==================================================================================


def maintenance_form(request):
    """
    Downtime‐entry form: CATEGORY is required; SUBCATEGORY + code are optional.
    """

    prod_lines = get_prod_lines()

    offset    = int(request.GET.get('offset', 0))
    page_size = 300

    if request.method == "POST":
        # Pull form data
        entry_id   = request.POST.get('entry_id')   # None for new
        line       = request.POST.get('line', '').strip()
        machine    = request.POST.get('machine', '').strip()
        raw_cat    = request.POST.get('category', '').strip()
        raw_sub    = request.POST.get('subcategory', '').strip()
        start_date = request.POST.get('start_date', '')   # "YYYY-MM-DD"
        start_time = request.POST.get('start_time', '')   # "HH:MM"
        comment    = request.POST.get('description', '').strip()
        emp_id     = request.POST.get('employee_id', '').strip()
        raw_labour = request.POST.get('labour_types', '[]')

        # Parse labour JSON
        try:
            labour_list = json.loads(raw_labour)
            if not isinstance(labour_list, list):
                labour_list = []
        except json.JSONDecodeError:
            labour_list = []

        # Validate category
        if not raw_cat:
            return HttpResponseBadRequest("You must choose a category.")
        cat_obj = DowntimeCode.objects.filter(code__startswith=raw_cat + "-").first()
        if not cat_obj:
            return HttpResponseBadRequest("Invalid category code.")
        category_name = cat_obj.category

        # Validate subcategory
        if raw_sub:
            try:
                sub_obj = DowntimeCode.objects.get(code=raw_sub)
            except DowntimeCode.DoesNotExist:
                return HttpResponseBadRequest("Invalid subcategory code.")
            subcategory_name = sub_obj.subcategory
            code_value       = raw_sub
        else:
            subcategory_name = "NOTSELECTED"
            code_value       = "NOTSELECTED"

        # Build epoch timestamp (localize to America/Toronto then UTC)
        try:
            dt_naive = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            return HttpResponseBadRequest("Bad date/time format.")
        local_tz    = timezone.get_current_timezone()  # America/Toronto
        aware_local = timezone.make_aware(dt_naive, local_tz)
        epoch_ts    = int(aware_local.astimezone(timezone.utc).timestamp())

        # Create or update
        if entry_id:
            e = get_object_or_404(MachineDowntimeEventTEST, pk=entry_id, is_deleted=False)
            e.line         = line
            e.machine      = machine
            e.category     = category_name
            e.subcategory  = subcategory_name
            e.code         = code_value
            e.start_epoch  = epoch_ts
            e.comment      = comment
            e.labour_types = labour_list
            e.employee_id  = emp_id or None
            e.save(update_fields=[
                'line','machine','category','subcategory',
                'code','start_epoch','comment',
                'labour_types','employee_id'
            ])
        else:
            MachineDowntimeEventTEST.objects.create(
                line         = line,
                machine      = machine,
                category     = category_name,
                subcategory  = subcategory_name,
                code         = code_value,
                start_epoch  = epoch_ts,
                comment      = comment,
                labour_types = labour_list,
                employee_id  = emp_id or None,
            )

        # Redirect back, preserving offset
        return redirect(request.get_full_path())

    # GET: render form
    qs = MachineDowntimeEventTEST.objects.filter(
        is_deleted=False,
        closeout_epoch__isnull=True
    ).annotate(
        has_electrician=Exists(
            DowntimeParticipation.objects.filter(
                event=OuterRef('pk'),
                leave_epoch__isnull=True,
                user__groups__name='maintenance_electrician'
            )
        ),
        has_millwright=Exists(
            DowntimeParticipation.objects.filter(
                event=OuterRef('pk'),
                leave_epoch__isnull=True,
                user__groups__name='maintenance_millwright'
            )
        ),
        has_tech=Exists(
            DowntimeParticipation.objects.filter(
                event=OuterRef('pk'),
                leave_epoch__isnull=True,
                user__groups__name='maintenance_tech'
            )
        ),
        has_operator=Case(
            When(labour_types__contains=['OPERATOR'], then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
        has_plctech=Exists(
            DowntimeParticipation.objects.filter(
                event=OuterRef('pk'),
                leave_epoch__isnull=True,
                user__groups__name='maintenance_plctech'
            )
        ),
        has_imt=Exists(
            DowntimeParticipation.objects.filter(
                event=OuterRef('pk'),
                leave_epoch__isnull=True,
                user__groups__name='maintenance_imt'
            )
        ),
         has_plumber=Exists(
            DowntimeParticipation.objects.filter(
                event=OuterRef('pk'),
                leave_epoch__isnull=True,
                user__groups__name='maintenance_plumber'
            )
        ),
    ).order_by('-start_epoch')

    total    = qs.count()
    entries  = list(qs[offset: offset + page_size])
    has_more = (offset + page_size) < total

    # Build downtime_codes_list and prod_lines JSON...
    downtime_codes = DowntimeCode.objects.all().order_by('category','subcategory','code')
    structured = {}
    for c in downtime_codes:
        cat = c.code.split('-',1)[0]
        structured.setdefault(cat, {
            'name': c.category,
            'code': cat,
            'subcategories': []
        })['subcategories'].append({'code': c.code, 'name': c.subcategory})
    downtime_codes_list = list(structured.values())

    # default date/time for form (America/Toronto)
    _now_local   = timezone.localtime()
    _default_date = _now_local.date().isoformat()
    _default_time = _now_local.strftime("%H:%M")


    return render(request, 'plant/maintenance_form.html', {
        'entries':             entries,
        'offset':              offset,
        'page_size':           page_size,
        'has_more':            has_more,
        'downtime_codes_json': json.dumps(downtime_codes_list),
        'lines_json':          json.dumps(prod_lines),
        'default_date':        _default_date,
        'default_time':        _default_time,
    })






# ================================================================
# ================================================================
# ======================= Labour Dashboard =======================
# ================================================================
# ================================================================

# how many at a time
PAGE_SIZE = 500


# group names you consider “maintenance”
MAINT_GROUPS = {
    "maintenance_managers",
    "maintenance_electrician",
    "maintenance_millwright",
    "maintenance_tech",
    "maintenance_supervisors",

    "maintenance_plctech",
    "maintenance_imt",
    "maintenance_plumber",
}

def user_has_maintenance_access(user) -> bool:
    """True if the user may enter the maintenance dashboard."""
    return (
        user.is_active
        and (
            user.is_superuser
            or user.groups.filter(name__in=MAINT_GROUPS).exists()
        )
    )


def annotate_being_worked_on(qs):
    """
    Takes a MachineDowntimeEventTEST queryset `qs` and returns it
    annotated with a boolean `being_worked_on` that’s True
    if any DowntimeParticipation for that event has no leave_epoch.
    """
    return qs.annotate(
        being_worked_on=Exists(
            DowntimeParticipation.objects
              .filter(event_id=OuterRef('pk'), leave_epoch__isnull=True)
        )
    )



@login_required
@require_POST
def bulk_toggle_active(request):
    if not user_has_maintenance_access(request.user):
        return HttpResponseForbidden("Not authorized")

    try:
        data       = json.loads(request.body)
        activate   = set(data.get("activate", []))
        deactivate = set(data.get("deactivate", []))
    except (ValueError, TypeError):
        return HttpResponseBadRequest("Bad JSON payload")

    # avoid dupes
    deactivate -= activate

    User = get_user_model()
    grp, _ = Group.objects.get_or_create(name="maintenance_active")

    # Activate
    for u in User.objects.filter(username__in=activate):
        u.groups.add(grp)

    # Deactivate
    for u in User.objects.filter(username__in=deactivate):
        u.groups.remove(grp)

    return JsonResponse({
        "status": "ok",
        "activated"  : list(activate),
        "deactivated": list(deactivate),
    })





from django.db.models import Q

# --------------------------- rewritten view ---------------------------------- #

def filter_out_operator_only_events(qs):
    """
    Given a MachineDowntimeEventTEST queryset, return a new queryset
    with all events whose labour_types == ["OPERATOR"] OR ["NA"] removed.
    """
    # Exclude any event whose labour_types exactly equals ["OPERATOR"] or ["NA"]
    return qs.exclude(
        Q(labour_types=["OPERATOR"])
    )


# Define the order in which roles should appear
ROLE_ORDER = ["electrician", "millwright", "tech", "plctech", "imt", "plumber"]


def group_by_role(workers):
    """
    Given a list of worker-dicts (with 'roles' and 'username', 'name', etc.),
    bucket them by their first-listed role, in the order of ROLE_ORDER.
    """
    buckets = OrderedDict((r, []) for r in ROLE_ORDER)
    buckets["other"] = []
    for w in workers:
        primary = w["roles"][0].lower() if w["roles"] else "other"
        if primary in buckets:
            buckets[primary].append(w)
        else:
            buckets["other"].append(w)
    return buckets


@login_required(login_url="login")
def list_all_downtime_entries(request):

    prod_lines = get_prod_lines()
    # 1) Access control
    if not user_has_maintenance_access(request.user):
        return HttpResponseForbidden("Not authorized; please ask a manager.")

    # 2) Fetch & annotate live events
    priority_sq = (
        LinePriority.objects
        .filter(line=OuterRef("line"))
        .values("priority")[:1]
    )
    base_qs = (
        MachineDowntimeEventTEST.objects
        .filter(is_deleted=False, closeout_epoch__isnull=True)
        .annotate(
            line_priority=Coalesce(
                Subquery(priority_sq, output_field=IntegerField()),
                Value(999),
                output_field=IntegerField()
            )
        )
        .order_by("line_priority", "-start_epoch")
        .prefetch_related("participants__user")
    )
    qs = annotate_being_worked_on(base_qs)
    qs = filter_out_operator_only_events(qs)

    # 3) Paginate + format “entries” for the table
    entries = list(qs[:PAGE_SIZE])
    today   = timezone.localdate()
    tz      = get_default_timezone()

    for e in entries:
        # — display timestamp as “HH:MM” if today, else “MM/DD”
        dt = e.start_at
        if is_naive(dt):
            dt = make_aware(dt, tz)
        local_dt = localtime(dt)
        e.start_display = (
            local_dt.strftime("%H:%M")
            if local_dt.date() == today
            else local_dt.strftime("%m/%d")
        )

        # — flag if *this user* is currently on the job
        e.user_has_open = e.participants.filter(
            user=request.user,
            leave_epoch__isnull=True
        ).exists()

        # ── NEW ── determine exactly which maintenance-roles are active on this event
        open_parts   = [p for p in e.participants.all() if p.leave_epoch is None]
        active_roles = set()
        for p in open_parts:
            user_groups = set(p.user.groups.values_list("name", flat=True))
            for role, grp_name in ROLE_TO_GROUP.items():
                if grp_name in user_groups:
                    active_roles.add(role)
        e.current_worker_roles = active_roles

        # ── NEW ── record the usernames who are currently joined
        e.current_usernames = [p.user.username for p in open_parts]

    # 4) Collect all maintenance‐role users
    User            = get_user_model()
    maint_groups    = list(ROLE_TO_GROUP.values())
    all_maint_users = (
        User.objects
        .filter(groups__name__in=maint_groups, is_active=True)
        .distinct()
        .order_by("username")
    )
    active_group, _    = Group.objects.get_or_create(name="maintenance_active")
    active_users       = all_maint_users.filter(groups=active_group)
    inactive_users     = all_maint_users.exclude(groups=active_group)

    # 5) Build per‐user dicts (with their open jobs)
    machine_priority_map = get_machine_priority_map()
    def build_worker_list(user_qs):
        lst = []
        for u in user_qs:
            name        = u.get_full_name() or u.username
            user_groups = set(u.groups.values_list("name", flat=True))
            roles       = [
                r for r, grp in ROLE_TO_GROUP.items() if grp in user_groups
            ]
            parts = DowntimeParticipation.objects.filter(
                user=u,
                leave_epoch__isnull=True,
                event__closeout_epoch__isnull=True
            ).select_related("event")
            jobs = [
                {
                    "machine":     p.event.machine,
                    "subcategory": p.event.subcategory,
                    "priority":    machine_priority_map.get(p.event.machine, "—"),
                }
                for p in parts
            ]
            lst.append({
                "username": u.username,
                "name":     name,
                "roles":    roles,
                "jobs":     jobs,
            })
        return sorted(lst, key=lambda w: w["name"])

    active_workers   = build_worker_list(active_users)
    inactive_workers = build_worker_list(inactive_users)

    # 6) Bucket by role
    active_by_role   = group_by_role(active_workers)
    inactive_by_role = group_by_role(inactive_workers)

    # 7) Determine current‐user flags
    user_grps     = set(request.user.groups.values_list("name", flat=True))
    is_manager    = "maintenance_managers" in user_grps
    is_supervisor = "maintenance_supervisors" in user_grps

    # 8) Build the labour_choices list
    full_choices = MachineDowntimeEventTEST.LABOUR_CHOICES
    allowed_groups = {
        ROLE_TO_GROUP["electrician"],
        ROLE_TO_GROUP["millwright"],
        ROLE_TO_GROUP["plctech"],
        ROLE_TO_GROUP["plumber"],
        "maintenance_supervisors",
        "maintenance_managers",
        "maintenance_tech",
    }
    if user_grps & allowed_groups:
        labour_choices = list(full_choices)
    else:
        labour_choices = [
            (code, label)
            for code, label in full_choices
            if code not in ("PLCTECH", "IMT")
        ]

    # 9) Downtime‐codes JSON for the modal
    downtime_codes = DowntimeCode.objects.all().order_by(
        "category", "subcategory", "code"
    )
    structured = {}
    for c in downtime_codes:
        cat = c.code.split("-", 1)[0]
        structured.setdefault(cat, {
            "name":          cat,
            "code":          cat,
            "subcategories": []
        })["subcategories"].append({
            "code": c.code,
            "name": c.subcategory
        })


    # ← NEW: which groups count as “EAM”?
    eam_group_names = {
        ROLE_TO_GROUP["plctech"],     # e.g. "maintenance_plctech"
        ROLE_TO_GROUP["millwright"],  # e.g. "maintenance_millwright"
        ROLE_TO_GROUP["electrician"], # e.g. "maintenance_electrician"
        ROLE_TO_GROUP["imt"], # e.g. "maintenance_imt"
    }
    is_eam = bool(user_grps & eam_group_names)

    # 10) Final render
    return render(request, "plant/maintenance_all_entries.html", {
        "entries":                  entries,
        "page_size":                PAGE_SIZE,
        "line_priorities":          LinePriority.objects.all(),
        "is_manager":               is_manager,
        "is_supervisor":            is_supervisor,
        "is_eam":                   is_eam,
        "labour_choices":           labour_choices,
        "active_workers_by_role":   active_by_role,
        "inactive_workers_by_role": inactive_by_role,
        "downtime_codes_json":      mark_safe(json.dumps(list(structured.values()))),
        "lines_json":               mark_safe(json.dumps(prod_lines)),
    })



@login_required
def load_more_downtime_entries(request):
    # parse offset
    try:
        offset = int(request.GET.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0

    # base queryset
    base_qs = (
        MachineDowntimeEventTEST.objects
        .filter(is_deleted=False, closeout_epoch__isnull=True)
        .order_by("-start_epoch")
        .prefetch_related("participants__user")
    )
    # annotate working-on flag
    qs = annotate_being_worked_on(base_qs)

    total = qs.count()
    batch = qs[offset:offset + PAGE_SIZE]

    today = timezone.localdate()
    default_tz = get_default_timezone()

    data = []
    for e in batch:
        # timezone-aware start_at
        dt = e.start_at
        if is_naive(dt):
            dt = make_aware(dt, default_tz)
        local_dt = timezone.localtime(dt)

        start_display = (
            local_dt.strftime('%H:%M')
            if local_dt.date() == today
            else local_dt.strftime('%m/%d')
        )

        # gather open participants
        open_parts = e.participants.filter(leave_epoch__isnull=True)
        users = [p.user.username for p in open_parts]

        data.append({
            'id':                e.id,
            'start_at':          e.start_at.strftime('%Y-%m-%d %H:%M'),
            'start_display':     start_display,
            'closeout_at':       (
                                    e.closeout_epoch and
                                    datetime.fromtimestamp(e.closeout_epoch)
                                            .strftime('%Y-%m-%d %H:%M')
                                  ) or None,
            'line':              e.line,
            'machine':           e.machine,
            'category':          e.category,
            'subcategory':       e.subcategory,
            'labour_types':      e.labour_types,
            'assigned_to':       users,
            'being_worked_on':   e.being_worked_on,
            'comment':           e.comment,
        })

    return JsonResponse({
        'entries':  data,
        'has_more': total > offset + PAGE_SIZE,
    })


@login_required
def downtime_history(request, event_id):
    """
    Return the complete labour-history JSON for one downtime event,
    PLUS the event’s own opening and close-out comments.
    """
    # 1) validate event
    event = get_object_or_404(
        MachineDowntimeEventTEST,
        pk=event_id,
        is_deleted=False
    )

    # 2) collect participations
    parts = (
        DowntimeParticipation.objects
        .filter(event=event)
        .order_by('join_epoch')
        .select_related('user')
    )

    # 3) serialise
    tz       = get_default_timezone()
    history  = []
    for p in parts:
        # join time
        jdt = datetime.fromtimestamp(p.join_epoch)
        if is_naive(jdt):
            jdt = make_aware(jdt, tz)
        jdt = localtime(jdt)
        join_at = jdt.strftime('%Y-%m-%d %H:%M')

        # leave time (may be null)
        if p.leave_epoch:
            ldt = datetime.fromtimestamp(p.leave_epoch)
            if is_naive(ldt):
                ldt = make_aware(ldt, tz)
            ldt = localtime(ldt)
            leave_at = ldt.strftime('%Y-%m-%d %H:%M')
        else:
            leave_at = None

        # roles
        user_group_names = set(
            p.user.groups.values_list('name', flat=True)
        )
        roles = [
            role
            for role, group_name in ROLE_TO_GROUP.items()
            if group_name in user_group_names
        ]

        history.append({
            "id"            : p.id,
            "user"          : p.user.username,
            "roles"         : roles,
            "join_at"       : join_at,
            "join_comment"  : p.join_comment,
            "leave_at"      : leave_at or "",
            "leave_comment" : p.leave_comment or "",
            "total_minutes" : p.total_minutes or 0,
        })

    return JsonResponse({
        "history"         : history,
        "event_comment"   : event.comment,
        "closeout_comment": event.closeout_comment or "",
    })

@require_POST
@login_required
def join_downtime_event(request):
    try:
        payload      = json.loads(request.body)
        event_id     = payload['event_id']
        comment      = payload.get('join_comment', '').strip()
        dt_str       = payload['join_datetime']       # e.g. "2025-05-06T14:30"
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    # fetch the event…
    event = MachineDowntimeEventTEST.objects.filter(pk=event_id, is_deleted=False).first()
    if not event:
        return HttpResponseBadRequest("Event not found")

    # parse the local-time string into a timezone-aware UTC datetime
    try:
        naive_dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M")
    except ValueError:
        return HttpResponseBadRequest("Bad datetime format")
    local_tz = get_default_timezone()   # should be America/Toronto
    aware_dt = make_aware(naive_dt, local_tz)
    utc_dt   = aware_dt.astimezone(utc)
    epoch_ts = int(utc_dt.timestamp())

    participation = DowntimeParticipation.objects.create(
        event        = event,
        user         = request.user,
        join_epoch   = epoch_ts,
        join_comment = comment
    )
    return JsonResponse({
        'status':           'ok',
        'participation_id': participation.id,
        'join_epoch':       epoch_ts,
    })


@require_POST
@login_required
def leave_downtime_event(request):
    try:
        payload       = json.loads(request.body)
        event_id      = payload['event_id']
        comment       = payload.get('leave_comment', '').strip()
        dt_str        = payload['leave_datetime']
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    # find the open participation…
    part = (DowntimeParticipation.objects
            .filter(event__pk=event_id, user=request.user, leave_epoch__isnull=True)
            .order_by('-join_epoch')
            .first())
    if not part:
        return HttpResponseBadRequest("No active participation to leave")

    # parse and convert to UTC epoch
    try:
        naive_dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M")
    except ValueError:
        return HttpResponseBadRequest("Bad datetime format")
    local_tz = get_default_timezone()
    aware_dt = make_aware(naive_dt, local_tz)
    utc_dt   = aware_dt.astimezone(utc)
    now_ts   = int(utc_dt.timestamp())

    # compute minutes
    import math
    delta_s = now_ts - part.join_epoch
    part.leave_epoch   = now_ts
    part.leave_comment = comment
    part.total_minutes = math.ceil(delta_s / 60)
    part.save(update_fields=['leave_epoch', 'leave_comment', 'total_minutes'])

    return JsonResponse({
        'status'       : 'ok',
        'leave_epoch'  : now_ts,
        'total_minutes': part.total_minutes,
    })


def get_machine_priority_map():
    prod_lines = get_prod_lines()
    """
    Returns a dict: { machine_number (str) → priority (int) } by
    walking prod_lines and the LinePriority table.
    """
    # grab all line→priority pairs in one query
    line_prios = {
        lp.line: lp.priority
        for lp in LinePriority.objects.all()
    }

    mp = {}
    # for each line in our merged prod_lines, pull its machines
    for line_block in prod_lines:
        prio = line_prios.get(line_block['line'], None)
        for op in line_block['operations']:
            for m in op['machines']:
                mp[m['number']] = prio
    return mp



@login_required
@require_POST
def move_line_priority(request, pk, direction):
    """
    Swap the priority of LinePriority(pk) with its neighbor:
    - direction='up'   → swap with the next-higher-urgency (lower number)
    - direction='down' → swap with the next-lower-urgency (higher number)
    """
    if direction not in ('up', 'down'):
        return HttpResponseBadRequest("Invalid move direction.")

    current = get_object_or_404(LinePriority, pk=pk)

    # find the neighbor to swap with
    if direction == 'up':
        neighbor = (
            LinePriority.objects
            .filter(priority__lt=current.priority)
            .order_by('-priority')
            .first()
        )
    else:  # down
        neighbor = (
            LinePriority.objects
            .filter(priority__gt=current.priority)
            .order_by('priority')
            .first()
        )

    if neighbor:
        # atomic swap
        with transaction.atomic():
            current.priority, neighbor.priority = neighbor.priority, current.priority
            current.save(update_fields=['priority'])
            neighbor.save(update_fields=['priority'])

    # If AJAX, return new values; otherwise redirect back
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'ok',
            'id': current.pk,
            'new_priority': current.priority,
            'swapped_with': neighbor.pk if neighbor else None,
        })

    # fallback: redirect back to referring page (or a named view)
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return HttpResponseRedirect(referer)
    return redirect(reverse('list_all_downtime_entries'))





# ====================================================================
# ====================================================================
# ====================== New Employee ================================
# ====================================================================
# ====================================================================


# role → group name mapping (change here if you rename groups later)
ROLE_TO_GROUP = {
    "electrician": "maintenance_electrician",
    "millwright":  "maintenance_millwright",
    "tech":        "maintenance_tech",

    "plctech":      "maintenance_plctech",
    "imt":          "maintenance_imt",
    "plumber":      "maintenance_plumber",
}

@require_POST
def add_employee(request):
    """
    Create or update a (real or preload) user and sync them to the
    correct maintenance_* groups, based on the manager’s selections.
    """
    first = request.POST.get("first_name", "").strip().lower()
    last  = request.POST.get("last_name",  "").strip().lower()
    roles = [r.strip().lower() for r in request.POST.getlist("roles")]   # list[]

    if not first or not last:
        messages.error(request, "First and last name are required.")
        return redirect(request.META.get("HTTP_REFERER", "index"))

    base_username = f"{first}.{last}"            # e.g. tyler.careless
    preload_un    = f"{base_username}@preload"   # e.g. tyler.careless@preload
    User = get_user_model()

    # 1️⃣ does a real account already exist?
    user = User.objects.filter(username=base_username).first()

    # 2️⃣ else: is there a preload account?
    if user is None:
        user = User.objects.filter(username=preload_un).first()

    # 3️⃣ else: create a fresh preload account
    if user is None:
        dummy_pw = get_random_string(20)
        user = User.objects.create_user(
            username=preload_un,
            password=dummy_pw,
            is_staff=True  # keep admin access consistent with your backend
        )
        created = True
    else:
        created = False

    # ------------------------------------------------------------------ #
    # Sync their group memberships
    # ------------------------------------------------------------------ #
    desired_group_names = {
        ROLE_TO_GROUP[r] for r in roles if r in ROLE_TO_GROUP
    }

    for role, group_name in ROLE_TO_GROUP.items():
        grp, _ = Group.objects.get_or_create(name=group_name)

        if group_name in desired_group_names:
            user.groups.add(grp)
        else:
            user.groups.remove(grp)

    user.save()

    # ------------------------------------------------------------------ #
    # Friendly feedback
    # ------------------------------------------------------------------ #
    if created:
        messages.success(
            request,
            f"Pre‑load account “{user.username}” created with roles: "
            f"{', '.join(roles) if roles else 'none'}."
        )
    else:
        messages.success(
            request,
            f"Updated {user.username}: now in groups "
            f"{', '.join(sorted(desired_group_names)) or 'none'}."
        )

    # [DEBUG] console output, as you requested earlier
    print(f"[DEBUG] New/updated employee → {first} {last}, roles: {roles}")

    return redirect(request.META.get("HTTP_REFERER", "index"))










# =============================================================
# =============================================================
# ================== One modal to rule them all ===============
# =============================================================
# =============================================================


@require_POST
def maintenance_edit(request):
    prod_lines = get_prod_lines()
    """
    Return a JSON blob with:
      - entry_id, line, machine, category_code, subcategory_code,
        start_date, start_time, comment
      - flat lists: lines[], machines[], categories[{code,name}], subcategories[{code,name,parent}]
      - and the full lines_data for dependent dropdowns
    """
    try:
        payload = json.loads(request.body)
        entry_id = payload['entry_id']
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid JSON or missing 'entry_id'")

    # Fetch the downtime event
    try:
        e = MachineDowntimeEventTEST.objects.get(pk=entry_id, is_deleted=False)
    except MachineDowntimeEventTEST.DoesNotExist:
        return HttpResponseBadRequest("Entry not found")

    # Convert epoch to human-readable local datetime
    dt = datetime.fromtimestamp(e.start_epoch)
    if is_naive(dt):
        dt = make_aware(dt, get_default_timezone())
    local = localtime(dt)

    # Generate flat machine list
    machines = sorted({
        m['number']
        for line in prod_lines
        for op in line['operations']
        for m in op['machines']
    })

    # Fetch all downtime codes from the database
    downtime_codes = DowntimeCode.objects.all().order_by('category', 'subcategory', 'code')

    # Structure categories and subcategories
    categories_dict = {}
    for code_obj in downtime_codes:
        # Extract category code (assuming it's the prefix before the first '-')
        cat_code = code_obj.code.split('-', 1)[0]
        if cat_code not in categories_dict:
            categories_dict[cat_code] = {
                'code': cat_code,
                'name': code_obj.category,
            }
    # Remove duplicates while preserving order
    unique_categories = list(categories_dict.values())

    # Structure subcategories with parent links
    subcategories = [
        {
            'code': code_obj.code,
            'name': code_obj.subcategory,
            'parent': code_obj.code.split('-', 1)[0]  # Assuming parent is category code
        }
        for code_obj in downtime_codes
    ]

    return JsonResponse({
        'status':           'ok',
        'entry_id':         e.pk,
        'line':             e.line,
        'machine':          e.machine,
        'category_code':    e.code.split('-', 1)[0],  # Assuming category code is prefix before '-'
        'category_name':    e.category,         # ← the display name
        'subcategory_code': e.code,
        'start_date':       local.strftime('%Y-%m-%d'),
        'start_time':       local.strftime('%H:%M'),
        'comment':          e.comment,
        'labour_types':     e.labour_types,  # ← added
        'employee_id':      e.employee_id, 
        'lines':            [l['line'] for l in prod_lines],
        'machines':         machines,
        'categories':       unique_categories,
        'subcategories':    subcategories,
        'lines_data':       prod_lines,
    })



@require_POST
def maintenance_update_event(request):
    """
    Receive edited fields and update the downtime event in the DB.
    """
    try:
        payload = json.loads(request.body)
        entry_id = payload['entry_id']
        line = payload['line']
        machine = payload['machine']
        category_code = payload['category']      # e.g. "MECH"
        subcategory_code = payload['subcategory']  # e.g. "MECH-TOOL"
        start_at_str = payload['start_at']        # "YYYY-MM-DD HH:MM"
        comment = payload['comment']
        labour_list = payload.get('labour_types', [])
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid JSON or missing fields")

    # 1) Lookup the event
    try:
        event = MachineDowntimeEventTEST.objects.get(pk=entry_id, is_deleted=False)
    except MachineDowntimeEventTEST.DoesNotExist:
        return HttpResponseBadRequest("Entry not found")

    # 2) Derive display names from DowntimeCode model
    try:
        # Fetch the DowntimeCode instance for subcategory
        sub_code_obj = DowntimeCode.objects.get(code=subcategory_code)
        category_name = sub_code_obj.category
        subcategory_name = sub_code_obj.subcategory
    except DowntimeCode.DoesNotExist:
        return HttpResponseBadRequest("Invalid category or subcategory code")

    # 3) Parse start_at into an epoch
    try:
        # Assume local date/time in the project's default timezone
        dt_naive = datetime.strptime(start_at_str, "%Y-%m-%d %H:%M")
    except ValueError:
        return HttpResponseBadRequest("Bad start_at format")

    local_tz = get_default_timezone()
    dt_aware = make_aware(dt_naive, local_tz) if is_naive(dt_naive) else dt_naive
    epoch_ts = int(dt_aware.timestamp())

    # 4) Apply updates
    event.line = line
    event.machine = machine
    event.category = category_name
    event.subcategory = subcategory_name
    event.code = subcategory_code
    event.start_epoch = epoch_ts
    event.comment = comment
    event.labour_types = labour_list
    event.save(update_fields=[
        'line', 'machine', 'category', 'subcategory',
        'code', 'start_epoch', 'comment', 'labour_types',
    ])

    print(f"[DEBUG] Updated downtime {entry_id}")
    return JsonResponse({'status': 'ok'})














# ====================================================================
# ====================================================================
# =================== Downtime Category Crud =========================
# ====================================================================
# ====================================================================




def downtime_codes_list(request):
    # Handle creation
    if request.method == 'POST':
        code       = request.POST.get('code')
        category   = request.POST.get('category')
        subcategory= request.POST.get('subcategory')
        if code and category and subcategory:
            DowntimeCode.objects.create(
                code=code,
                category=category,
                subcategory=subcategory
            )
        return redirect('downtime_codes_list')

    # For GET: list all codes and supply existing cats/subcats
    codes = DowntimeCode.objects.all()
    categories   = (DowntimeCode.objects
                    .order_by('category')
                    .values_list('category', flat=True)
                    .distinct())
    subcategories= (DowntimeCode.objects
                    .order_by('subcategory')
                    .values_list('subcategory', flat=True)
                    .distinct())

    return render(request, 'plant/downtime_codes_list.html', {
        'codes': codes,
        'categories': categories,
        'subcategories': subcategories,
    })





@require_POST
def downtime_codes_create(request):
    """AJAX: create a new code"""
    code       = request.POST.get('code', '').strip()
    category   = request.POST.get('category', '').strip()
    subcat     = request.POST.get('subcategory', '').strip()

    if not all([code, category, subcat]):
        return JsonResponse({'error': 'All fields are required.'}, status=400)

    if DowntimeCode.objects.filter(code=code).exists():
        return JsonResponse({'error': f'Code "{code}" already exists.'}, status=400)

    obj = DowntimeCode.objects.create(
        code=code, category=category, subcategory=subcat
    )
    data = {
        'id': obj.id,
        'code': obj.code,
        'category': obj.category,
        'subcategory': obj.subcategory,
        'updated_at': obj.updated_at.strftime('%Y-%m-%d %H:%M'),
    }
    return JsonResponse(data, status=201)


@require_POST
def downtime_codes_edit(request, pk):
    """AJAX: update an existing code"""
    obj = get_object_or_404(DowntimeCode, pk=pk)
    code     = request.POST.get('code', '').strip()
    category = request.POST.get('category', '').strip()
    subcat   = request.POST.get('subcategory', '').strip()

    if not all([code, category, subcat]):
        return JsonResponse({'error': 'All fields are required.'}, status=400)

    # if they changed the code, ensure uniqueness
    if obj.code != code and DowntimeCode.objects.filter(code=code).exists():
        return JsonResponse({'error': f'Code "{code}" already exists.'}, status=400)

    obj.code = code
    obj.category = category
    obj.subcategory = subcat
    obj.save()

    data = {
        'id': obj.id,
        'code': obj.code,
        'category': obj.category,
        'subcategory': obj.subcategory,
        'updated_at': obj.updated_at.strftime('%Y-%m-%d %H:%M'),
    }
    return JsonResponse(data)


@require_POST
def downtime_codes_delete(request, pk):
    """AJAX: delete a code"""
    obj = get_object_or_404(DowntimeCode, pk=pk)
    obj.delete()
    return JsonResponse({'success': True})











# ====================================================================
# ====================================================================
# ====================== Downtime History ============================
# ====================================================================
# ====================================================================



@require_POST
@csrf_exempt
def machine_history(request):
    machine = request.POST.get("machine", "").strip()
    if not machine:
        return JsonResponse({"error": "Machine parameter is required."}, status=400)

    events = (
        MachineDowntimeEventTEST.objects
        .filter(machine=machine, is_deleted=False)
        .order_by("-start_epoch")[:500]
    )

    payload = []
    for e in events:
        parts = []
        for p in e.participants.all().order_by("join_epoch"):
            # build a python datetime (in local time) from your epoch seconds
            join_dt = datetime.fromtimestamp(p.join_epoch, tz=timezone.get_current_timezone())
            leave_dt = (
                datetime.fromtimestamp(p.leave_epoch, tz=timezone.get_current_timezone())
                if p.leave_epoch
                else None
            )

            parts.append({
                "user": p.user.get_full_name() or p.user.username,
                "join_epoch": p.join_epoch,
                "join_display": join_dt.strftime("%B %d, %Y %I:%M %p"),
                "leave_epoch": p.leave_epoch,
                "leave_display": leave_dt.strftime("%B %d, %Y %I:%M %p") if leave_dt else None,
                "join_comment": p.join_comment,
                "leave_comment": p.leave_comment,
                "total_minutes": p.total_minutes,
            })

        payload.append({
            "id": e.id,
            "start_epoch": e.start_epoch,
            "start_display": e.start_at.strftime("%Y-%m-%d %H:%M"),
            "closeout_epoch": e.closeout_epoch,
            "closeout_display": e.closeout_at.strftime("%Y-%m-%d %H:%M") if e.closeout_at else None,
            "category": e.category,
            "subcategory": e.subcategory,
            "code": e.code,
            "comment": e.comment,
            "closeout_comment": e.closeout_comment,
            "participations": parts,
        })

    return JsonResponse({"events": payload})


@login_required
def employee_login_status(request):
    # ── access control ──
    if not user_has_maintenance_access(request.user):
        return HttpResponseForbidden("Not authorized; please ask a manager.")

    User = get_user_model()
    group_names = set(ROLE_TO_GROUP.values())
    qs = (
        User.objects
            .filter(groups__name__in=group_names)
            .distinct()
            .order_by('last_name', 'first_name')
    )

    # initialize summary counters
    summary = { role: {'real': 0, 'preload': 0}
                for role in ROLE_TO_GROUP.keys() }

    users_status = []
    for u in qs:
        # raw roles & display string
        roles_raw = [
            role
            for role, grp in ROLE_TO_GROUP.items()
            if u.groups.filter(name=grp).exists()
        ]
        roles_display = ", ".join(r.capitalize() for r in roles_raw)

        # account type
        is_preload = u.username.endswith('@preload')
        account_type = 'Preload' if is_preload else 'Real'

        # last_login formatted
        if u.last_login:
            last_login_str = u.last_login.strftime('%Y-%m-%d %H:%M')
            logged_in = 'Yes'
        else:
            last_login_str = ''
            logged_in = 'No'

        # increment summary for each role they occupy
        for r in roles_raw:
            key = 'preload' if is_preload else 'real'
            summary[r][key] += 1

        users_status.append({
            'name':       u.get_full_name() or u.username,
            'username':   u.username,
            'roles':      roles_display,
            'roles_raw':  roles_raw,
            'account':    account_type,
            'last_login': last_login_str,
            'logged_in':  logged_in,
        })

    # build a simple list for the template
    summary_list = [
        {
            'role': role.capitalize(),
            'real': summary[role]['real'],
            'preload': summary[role]['preload'],
        }
        for role in ROLE_TO_GROUP.keys()
    ]

    # ── CSV export? ──
    if request.GET.get('format') == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="maintenance_login_status.csv"'
        writer = csv.writer(resp)
        writer.writerow([
            smart_str("Name"),
            smart_str("Username"),
            smart_str("Role(s)"),
            smart_str("Account Type"),
            smart_str("Last Login"),
            smart_str("Logged In?"),
        ])
        for u in users_status:
            writer.writerow([
                smart_str(u['name']),
                smart_str(u['username']),
                smart_str(u['roles']),
                smart_str(u['account']),
                smart_str(u['last_login']),
                smart_str(u['logged_in']),
            ])
        return resp

    # ── otherwise render HTML ──
    return render(request, 'plant/employee_login_status.html', {
        'users':   users_status,
        'summary': summary_list,
    })







# ========================================================================
# ========================================================================
# ==================== Phase 2 Maintenance App Updates ===================
# ========================================================================
# ========================================================================




def target_lines(request):
    prod_lines = get_prod_lines()
    if request.method == 'GET':
        # extract just the line names
        line_names = [blk['line'] for blk in prod_lines]
        return JsonResponse({'lines': line_names})
    return HttpResponse(status=405)










# ========================================================================
# ========================================================================
# =========== Forceleave Feature for Supervisors and Managers ============
# ========================================================================
# ========================================================================


def user_is_supervisor_or_manager(user):
    return user.groups.filter(
        name__in={"maintenance_supervisors", "maintenance_managers"}
    ).exists()

@login_required
@require_POST
@user_passes_test(user_is_supervisor_or_manager)      # <--- permission gate
def force_leave_participation(request, pk):
    """
    Managers/supervisors can finish someone else’s open participation,
    supplying a mandatory comment and an optional leave_datetime.
    """
    try:
        payload = json.loads(request.body)
        comment = payload["leave_comment"].strip()
        if not comment:
            raise KeyError
    except (ValueError, KeyError):
        return HttpResponseBadRequest("leave_comment is required")

    # ---------- pull & parse leave_datetime -----------------
    leave_dt_str = payload.get("leave_datetime")         # "2025-06-12T14:35"
    tz           = get_default_timezone()                # America/Toronto
    try:
        if leave_dt_str:
            naive = parse_datetime(leave_dt_str)         # → naive DT
            if naive is None:
                raise ValueError
            aware_local = make_aware(naive, timezone=tz) # → aware local
            aware_utc   = aware_local.astimezone(timezone.utc)
            leave_ts    = int(aware_utc.timestamp())
        else:
            leave_ts = int(time.time())                  # fallback to “now”
    except Exception:
        return HttpResponseBadRequest("Bad leave_datetime")
    # -------------------------------------------------------

    part = get_object_or_404(
        DowntimeParticipation,
        pk=pk,
        leave_epoch__isnull=True,
        event__is_deleted=False,
        event__closeout_epoch__isnull=True,
    )

    if leave_ts <= part.join_epoch:
        return HttpResponseBadRequest("Leave time must be after join time.")

    delta_s = leave_ts - part.join_epoch
    part.leave_epoch   = leave_ts
    part.leave_comment = comment
    part.total_minutes = math.ceil(delta_s / 60)
    part.save(update_fields=["leave_epoch", "leave_comment", "total_minutes"])

    return JsonResponse({
        "status"       : "ok",
        "leave_epoch"  : leave_ts,
        "total_minutes": part.total_minutes,
    })






# ========================================================================
# ========================================================================
# ================ Bulk Add Machine Downtime Events  =====================
# ========================================================================
# ========================================================================

@login_required(login_url="login")
def maintenance_bulk_form(request):
    prod_lines = get_prod_lines()
    """
    Bulk‐add downtime entries: pick one line, one or more machines,
    same category/subcategory/comment for all, plus labour.
    """
    if request.method == "POST":
        line        = request.POST.get('line', '').strip()
        machines    = request.POST.getlist('machines')
        raw_cat     = request.POST.get('category', '').strip()
        raw_sub     = request.POST.get('subcategory', '').strip()
        start_date  = request.POST.get('start_date', '')
        start_time  = request.POST.get('start_time', '')
        comment     = request.POST.get('description', '').strip()
        emp_id      = request.POST.get('employee_id', '').strip()
        raw_labour  = request.POST.get('labour_types', '[]')

        # --- validations ---
        if not machines:
            return HttpResponseBadRequest("You must select at least one machine.")
        if not raw_cat:
            return HttpResponseBadRequest("You must choose a category.")
        cat_obj = DowntimeCode.objects.filter(code__startswith=raw_cat + "-").first()
        if not cat_obj:
            return HttpResponseBadRequest("Invalid category code.")
        category_name = cat_obj.category

        if raw_sub:
            try:
                sub_obj = DowntimeCode.objects.get(code=raw_sub)
            except DowntimeCode.DoesNotExist:
                return HttpResponseBadRequest("Invalid subcategory code.")
            subcategory_name = sub_obj.subcategory
            code_value       = raw_sub
        else:
            subcategory_name = "NOTSELECTED"
            code_value       = "NOTSELECTED"

        # parse labour JSON
        try:
            labour_list = json.loads(raw_labour)
            if not isinstance(labour_list, list):
                labour_list = []
        except json.JSONDecodeError:
            labour_list = []


        # parse & localize datetime
        try:
            dt_naive    = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
        except ValueError:

            return HttpResponseBadRequest("Bad date/time format.")
        local_tz    = timezone.get_current_timezone()  # America/Toronto
        aware_local = timezone.make_aware(dt_naive, local_tz)
        epoch_ts    = int(aware_local.astimezone(timezone.utc).timestamp())


        # create one event per machine
        for machine in machines:
            MachineDowntimeEventTEST.objects.create(
                line         = line,
                machine      = machine,
                category     = category_name,
                subcategory  = subcategory_name,
                code         = code_value,
                start_epoch  = epoch_ts,
                comment      = comment,
                labour_types = labour_list,
                employee_id  = emp_id or None,
            )

        return redirect('maintenance_all')

    # GET → build JSON for selects
    downtime_codes = DowntimeCode.objects.all().order_by('category','subcategory','code')
    structured = {}
    for c in downtime_codes:
        cat = c.code.split('-',1)[0]
        structured.setdefault(cat, {
            'name': c.category,
            'code': cat,
            'subcategories': []
        })['subcategories'].append({'code': c.code, 'name': c.subcategory})
    downtime_codes_list = list(structured.values())

    # default date/time for form (America/Toronto)
    _now_local   = timezone.localtime()
    _default_date = _now_local.date().isoformat()
    _default_time = _now_local.strftime("%H:%M")

    return render(request, 'plant/maintenance_bulk_form.html', {
        'lines_json':           json.dumps(prod_lines),
        'downtime_codes_json':  json.dumps(downtime_codes_list),
        'default_date':         _default_date,
        'default_time':         _default_time,
    })




# ========================================================================
# ========================================================================
# ================ Quickadd Feature for supervisors  =====================
# ========================================================================
# ========================================================================

@login_required(login_url="login")
def quick_add(request):
    prod_lines = get_prod_lines()
    """
    Add a single downtime entry: pick one line, one machine,
    same category/subcategory/comment, plus labour.
    """
    if request.method == "POST":
        line        = request.POST.get('line', '').strip()
        machine     = request.POST.get('machine', '').strip()
        raw_cat     = request.POST.get('category', '').strip()
        raw_sub     = request.POST.get('subcategory', '').strip()
        start_date  = request.POST.get('start_date', '')
        start_time  = request.POST.get('start_time', '')
        comment     = request.POST.get('description', '').strip()
        emp_id      = request.POST.get('employee_id', '').strip()
        raw_labour  = request.POST.get('labour_types', '[]')

        # --- validations ---
        if not machine:
            return HttpResponseBadRequest("You must select a machine.")
        if not raw_cat:
            return HttpResponseBadRequest("You must choose a category.")
        cat_obj = DowntimeCode.objects.filter(code__startswith=raw_cat + "-").first()
        if not cat_obj:
            return HttpResponseBadRequest("Invalid category code.")
        category_name = cat_obj.category

        if raw_sub:
            try:
                sub_obj = DowntimeCode.objects.get(code=raw_sub)
                subcategory_name = sub_obj.subcategory
                code_value       = raw_sub
            except DowntimeCode.DoesNotExist:
                return HttpResponseBadRequest("Invalid subcategory code.")
        else:
            subcategory_name = "NOTSELECTED"
            code_value       = "NOTSELECTED"

        # parse labour JSON
        try:
            labour_list = json.loads(raw_labour)
            if not isinstance(labour_list, list):
                labour_list = []
        except json.JSONDecodeError:
            labour_list = []

        # parse & localize datetime
        try:
            dt_naive    = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            return HttpResponseBadRequest("Bad date/time format.")
        local_tz    = timezone.get_current_timezone()  # America/Toronto
        aware_local = timezone.make_aware(dt_naive, local_tz)
        epoch_ts    = int(aware_local.astimezone(timezone.utc).timestamp())

        # --- single event create ---
        MachineDowntimeEventTEST.objects.create(
            line         = line,
            machine      = machine,
            category     = category_name,
            subcategory  = subcategory_name,
            code         = code_value,
            start_epoch  = epoch_ts,
            comment      = comment,
            labour_types = labour_list,
            employee_id  = emp_id or None,
        )

        # just redirect to your “all downtime entries” page:
        return redirect('maintenance_all')

    # GET → build JSON for selects (unchanged)
    downtime_codes = DowntimeCode.objects.all().order_by('category','subcategory','code')
    structured = {}
    for c in downtime_codes:
        cat = c.code.split('-',1)[0]
        structured.setdefault(cat, {
            'name': c.category,
            'code': cat,
            'subcategories': []
        })['subcategories'].append({'code': c.code, 'name': c.subcategory})
    downtime_codes_list = list(structured.values())


    # default date/time for form (America/Toronto)
    _now_local   = timezone.localtime()
    _default_date = _now_local.date().isoformat()
    _default_time = _now_local.strftime("%H:%M")

    return render(request, 'plant/quick_add.html', {
        'lines_json':           json.dumps(prod_lines),
        'downtime_codes_json':  json.dumps(downtime_codes_list),
        'labour_choices':      MachineDowntimeEventTEST.LABOUR_CHOICES,
    })







# ====================================================================================
# ====================================================================================
# ======================== Phase 4 Generating Work Orders ============================
# ====================================================================================
# ====================================================================================


LITMUS_API_URL = settings.LITMUS_API_URL
LITMUS_API_KEY = settings.LITMUS_API_KEY

# Role → Trade
TRADE_BY_ROLE = {
    "electrician": "ELA",
    "millwright":  "MI",
    "plctech":     "EMTR",
    "imt":       "IMT",
}

# Event.labour_types (UPPERCASE) → Trade
TRADE_BY_EVENT_CODE = {
    "ELECTRICIAN": "ELA",
    "MILLWRIGHT":  "MI",
    "PLCTECH":     "EMTR",
    "IMT":       "IMT",
}

# Trade → Django group name (direct mapping)
GROUP_BY_TRADE = {
    "ELA":  "maintenance_electrician",
    "MI":   "maintenance_millwright",
    "EMTR": "maintenance_plctech",
    "IMT":  "maintenance_imt",
}

# Preferred priority when multiple apply
TRADE_PRIORITY_TRADES = ["EMTR", "IMT", "MI", "ELA",]  # electrician > plc tech > millwright

# Standard WO template to use per trade
STANDARD_WO_BY_TRADE = {
    "ELA":  "PMS BREAKDOWN (ELA)",
    "EMTR": "PMS BREAKDOWN (EMTR)",
    "MI":   "PMS BREAKDOWN (MI)",
    "IMT":  "PMS BREAKDOWN (IMT)",
}

# --- Helpers --------------------------------------------------------


def _build_wo_title(category: str, subcategory: str, comment: str) -> str:
    """'Category - Subcategory - Comment' capped at 80 chars with ellipsis."""
    parts = [p for p in [category, subcategory or "", comment or ""] if p]
    full = " - ".join(parts)
    return (full[:77] + "...") if len(full) > 80 else full


def _resolve_trade_for_user(user, event) -> str:
    """
    Choose Trade code:
      1) Based on the logged-in user's maintenance_* group(s)
      2) Else infer from event.labour_types
      3) Else default to MI
    """
    user_groups = set(user.groups.values_list("name", flat=True))

    # 1) direct group → trade, in priority order
    for trade in TRADE_PRIORITY_TRADES:
        grp = GROUP_BY_TRADE.get(trade)
        if grp and grp in user_groups:
            return trade

    # 2) infer from event.labour_types (e.g., ["PLCTECH","ELECTRICIAN"])
    if isinstance(event.labour_types, list):
        for trade in TRADE_PRIORITY_TRADES:
            want_codes = [k for k, v in TRADE_BY_EVENT_CODE.items() if v == trade]
            if any(str(code).upper() in want_codes for code in event.labour_types):
                return trade

    # 3) fallback
    return "MI"


def _extract_message_from_body(body):
    if isinstance(body, dict):
        if "Message" in body:
            return body.get("Message")
        if "result" in body and isinstance(body["result"], dict):
            return body["result"].get("Message")
    return None


def _extract_wo_id_from_text(text: str):
    m = re.search(r"WO\s*#\s*(\d+)", text or "", flags=re.I)
    return int(m.group(1)) if m else None


def _is_equipment_not_found(msg: str, status_code: int) -> bool:
    """Heuristic: detect when EAM rejected the Equipment number."""
    if status_code in (400, 404):
        return True
    if not msg:
        return False
    # common phrasings we might see
    needles = ["equipment", "asset", "machine"]
    return (
        any(n in msg.lower() for n in needles) and
        any(w in msg.lower() for w in ["not found", "invalid", "doesn't exist", "does not exist", "unknown"])
    )


def _candidate_alt_equipment(equipment: str):
    """
    If equipment ends with a single letter (e.g., '1806L' or '1806R'),
    return the numeric part as a fallback candidate. Otherwise None.
    """
    if not equipment:
        return None
    m = re.fullmatch(r"\s*(\d+)[A-Za-z]\s*", str(equipment))
    return m.group(1) if m else None


def _post_to_litmus(equipment: str, payload_base: dict, headers: dict, *, timeout: int):
    """POST once and parse the response into a small normalized dict."""
    payload = {**payload_base, "Equipment": str(equipment)}
    try:
        resp = requests.post(LITMUS_API_URL, json=payload, headers=headers, timeout=timeout)
    except Timeout:
        return {"ok": False, "status_code": 0, "message": "Timed out contacting EAM. Please try again."}
    except RequestException as e:
        return {"ok": False, "status_code": 0, "message": f"Network error contacting EAM: {e}"}

    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text}

    msg = _extract_message_from_body(body) or (resp.text if isinstance(body, dict) and "raw" in body else str(body))
    wo_id = _extract_wo_id_from_text(msg)

    if resp.ok and wo_id:
        return {"ok": True, "status_code": resp.status_code, "message": msg, "wo_id": wo_id}

    # Friendly HTTP hints
    if resp.status_code in (401, 403):
        hint = "Authorization error from EAM (check API key or permissions)."
    elif resp.status_code >= 500:
        hint = "EAM is having an issue (server error). Please try again shortly."
    else:
        hint = None

    return {
        "ok": False,
        "status_code": resp.status_code,
        "message": f"{msg}" + (f"  {hint}" if hint else ""),
        "wo_id": None,
    }


def _create_workorder_for_event(event, user, *, timeout: int = 30):
    """
    Create a work order for the given MachineDowntimeEventTEST instance by
    calling the Litmus API. Saves event.work_order_id on success.
    Returns a dict with ok/message/work_order_id/status_code.
    """
    # idempotent
    if event.work_order_id:
        return {
            "ok": True,
            "message": f"Work order already exists: #{event.work_order_id}.",
            "work_order_id": event.work_order_id,
            "status_code": 200,
        }

    wo_title   = _build_wo_title(event.category, event.subcategory, event.comment)
    trade_code = _resolve_trade_for_user(user, event)
    standard_wo = STANDARD_WO_BY_TRADE.get(trade_code, f"PMS BREAKDOWN ({trade_code})")

    headers = {
        "X-Api-Key":    LITMUS_API_KEY,
        "Content-Type": "application/json",
    }
    payload_base = {
        "WO":             wo_title,
        "Org":            "PMDS",
        "Type":           "BRKD",
        "Priority":       "2",
        "Dept":           "MAINT",
        "WOStatus":       "R",
        "EstTradeDT":     1,
        "Trade":          trade_code,
        "EstTradeHours":  1,
        "PeopleRequired": 1,
        "RespDept":       "MT",
        "StandardWO":     standard_wo,
    }

    original_equipment = str(event.machine).strip()

    # 1) Try with the machine as-is
    first = _post_to_litmus(original_equipment, payload_base, headers, timeout=timeout)
    if first["ok"]:
        event.work_order_id = first["wo_id"]
        event.save(update_fields=["work_order_id", "updated_at_UTC"])
        return {
            "ok": True,
            "message": f"Work order #{first['wo_id']} created (Trade {trade_code}, StandardWO '{standard_wo}').",
            "work_order_id": first["wo_id"],
            "status_code": first["status_code"],
        }

    # 2) If equipment looks like 1806L/1806R/etc and error suggests "not found", try stripping suffix letter
    alt_equipment = _candidate_alt_equipment(original_equipment)
    if alt_equipment and _is_equipment_not_found(first.get("message"), first.get("status_code", 0)):
        second = _post_to_litmus(alt_equipment, payload_base, headers, timeout=timeout)
        if second["ok"]:
            event.work_order_id = second["wo_id"]
            event.save(update_fields=["work_order_id", "updated_at_UTC"])
            return {
                "ok": True,
                "message": (
                    f"Work order #{second['wo_id']} created (Trade {trade_code}, StandardWO '{standard_wo}'). "
                    f"Note: '{original_equipment}' not found in EAM; succeeded using '{alt_equipment}'."
                ),
                "work_order_id": second["wo_id"],
                "status_code": second["status_code"],
            }
        # Both attempts failed – tailor message for equipment not found
        if _is_equipment_not_found(second.get("message"), second.get("status_code", 0)):
            return {
                "ok": False,
                "message": (
                    f"EAM could not find equipment '{original_equipment}' "
                    f"(also tried '{alt_equipment}'). Please verify the machine number in EAM "
                    f"or remove the trailing letter if not used there."
                ),
                "status_code": second["status_code"] or first["status_code"] or 400,
            }

    # 3) General failure fallback with a helpful message
    return {
        "ok": False,
        "message": (
            first["message"] or
            "Could not create the work order. Please try again, and if the problem persists contact maintenance."
        ),
        "status_code": first.get("status_code", 400),
    }


# --- View -----------------------------------------------------------
@login_required
@require_POST
def generate_workorder(request, entry_id):
    event = get_object_or_404(MachineDowntimeEventTEST, pk=entry_id, is_deleted=False)
    result = _create_workorder_for_event(event, request.user)

    status = 200 if result.get("ok") else 400
    return JsonResponse(
        {
            "ok": result.get("ok", False),
            "message": result.get("message", "Unknown result."),
            "work_order_id": result.get("work_order_id"),
        },
        status=status
    )