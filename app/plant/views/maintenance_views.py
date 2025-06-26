import json
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse, HttpResponseRedirect
from datetime import datetime
from ..models.maintenance_models import MachineDowntimeEvent, LinePriority, DowntimeParticipation, DowntimeCode, DowntimeMachine
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
from django.contrib.auth.models import Group
from django.utils.crypto import get_random_string
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
    Aggregate downtime machine records into structured production line data.

    Queries all DowntimeMachine entries and groups them by `line`, constructing
    a list of dictionaries where each dictionary represents:
      - `line` (str):        The production line identifier.
      - `scrap_line` (str):  Same as `line`, for scrap reporting.
      - `operations` (list): A list of operations on that line, each with:
          - `op` (str):              The operation identifier.
          - `machines` (list):       A list of machines for this operation,
              each being a dict with:
              - `number` (int):       The machine number.
              - `target` (Any):       The target value (None by default).

    Returns
    -------
    list of dict
        A fresh list of production-line entries reflecting the current state
        of the DowntimeMachine table.
    """
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
    """
    Soft-delete a MachineDowntimeEvent based on the provided entry ID.

    Expects a POST request with a JSON body containing:
      - entry_id (int): The primary key of the MachineDowntimeEvent to delete.

    Workflow:
      1. Parse the JSON payload and extract `entry_id`.
      2. Retrieve the non-deleted MachineDowntimeEvent with that ID.
      3. Mark the event as deleted by setting `is_deleted = True`
         and stamping `deleted_at` with the current time.
      4. Save the changes (only `is_deleted` and `deleted_at` fields).
      5. Return a JSON response `{'status': 'ok'}`.

    Error Handling:
      - If the payload is not valid JSON or missing `entry_id`, returns
        HTTP 400 Bad Request with message "Invalid payload".
      - If no matching non-deleted event is found, returns
        HTTP 400 Bad Request with message "Entry not found".

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request, which must be a POST containing JSON.

    Returns
    -------
    django.http.JsonResponse or django.http.HttpResponseBadRequest
        - JsonResponse({'status': 'ok'}) on successful soft-delete.
        - HttpResponseBadRequest on invalid payload or missing entry.
    """
    try:
        payload = json.loads(request.body)
        entry_id = payload['entry_id']
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    try:
        e = MachineDowntimeEvent.objects.get(pk=entry_id, is_deleted=False)
    except MachineDowntimeEvent.DoesNotExist:
        return HttpResponseBadRequest("Entry not found")

    # soft-delete
    e.is_deleted = True
    e.deleted_at = timezone.now()
    e.save(update_fields=['is_deleted', 'deleted_at'])

    return JsonResponse({'status': 'ok'})



@require_POST
def closeout_downtime_entry(request):
    """
    Close out a downtime event only after all participants have left.

    Expects a POST request with a JSON body containing:
      - entry_id (int):           The primary key of the MachineDowntimeEvent.
      - closeout (str):           The close-out timestamp in "YYYY-MM-DD HH:MM" format.
      - closeout_comment (str):   A comment to record at close-out.

    Workflow:
      1. Parse and validate the JSON payload.
      2. Retrieve the non-deleted, not-yet-closed MachineDowntimeEvent or return 404.
      3. Ensure there are no active DowntimeParticipation entries (all participants have left).
      4. Interpret the provided timestamp as local (America/Toronto), convert to a UTC epoch.
      5. Verify the close-out epoch is strictly after the event’s start_epoch.
      6. Save `closeout_epoch` and `closeout_comment` on the event.
      7. Return a JSON response with status "ok" and the epoch timestamp.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP POST request with a JSON body as described above.

    Returns
    -------
    django.http.JsonResponse
        On success: `{"status": "ok", "closed_at_epoch": <int>}`.

    Raises
    ------
    HttpResponseBadRequest
        If the payload is invalid JSON/missing keys, or if the close-out time
        is not after the event’s start time.
    HttpResponseForbidden
        If any DowntimeParticipation for this event remains open.
    Http404
        If the specified event does not exist, is deleted, or is already closed.
    """
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
        MachineDowntimeEvent,
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
    Retrieve a paginated list of active (open and not deleted) machine downtime events.

    The response JSON includes:
      - entries: A list of event dicts, each containing:
          • id (int)
          • start_at (str): formatted "YYYY-MM-DD HH:MM"
          • line (str)
          • machine (str)
          • category (str)
          • subcategory (str)
          • code (str)
          • category_code (str): portion of code before the first hyphen
          • subcategory_code (str): full code
          • comment (str)
          • labour_types (str or list)
          • employee_id (Any): if available
      - has_more (bool): True if additional pages remain beyond this batch.
      - is_guest (bool): True if the requester is not authenticated.

    Pagination
    ----------
    Uses `offset` query parameter (default 0) and a fixed page size of 300:
      - offset (int): zero-based index of the first record in this batch.

    Filtering
    ---------
    Only returns events where:
      - `is_deleted` is False
      - `closeout_epoch` is null (i.e., still open)
    Ordered by newest `start_epoch` first.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request. May include:
          - GET parameter `offset` (optional, defaults to 0).

    Returns
    -------
    django.http.JsonResponse
        JSON object with keys `entries`, `has_more`, and `is_guest`.
    """
    """
    Returns a page of open MachineDowntimeEvent entries plus:
      - has_more: whether there are more to load
      - is_guest: true if the user is anonymous (not logged in)
    """
    # paging params
    offset    = int(request.GET.get('offset', 0))
    page_size = 300

    # only live, un‐closed events
    qs = MachineDowntimeEvent.objects.filter(
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
    Display and process the machine downtime entry form for maintenance staff.

    GET:
      - Renders the downtime entry page with:
        • `prod_lines`: JSON-serializable list of production lines, operations, and machines.
        • `entries`: a page of active (not deleted, not closed) MachineDowntimeEvent objects,
          annotated with flags for open participant roles (electrician, millwright, tech, operator, plc tech, IMT).
        • `offset`, `page_size`, `has_more`: pagination parameters.

    POST:
      - Reads form fields for an existing entry (`entry_id`) or new entry:
          • line, machine, category, subcategory, start_date, start_time,
            description (comment), employee_id, labour_types (JSON list).
      - Validates that `category` is present and corresponds to a known DowntimeCode.
      - Validates optional `subcategory` if provided.
      - Parses and localizes the start datetime (America/Toronto) to a UTC epoch timestamp.
      - Creates a new MachineDowntimeEvent or updates the existing one.
      - Redirects back to the same URL (preserving pagination).

    Parameters
    ----------
    request : django.http.HttpRequest
        The HTTP request object. For GET, may include `offset` as a query parameter.
        For POST, carries form data and optional `entry_id` for updates.

    Returns
    -------
    django.http.HttpResponse
        On GET: renders "plant/maintenance_form.html" with context data.
        On POST: redirects back to the form URL on success, or returns
        HTTP 400 Bad Request for validation errors.
    """
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
            e = get_object_or_404(MachineDowntimeEvent, pk=entry_id, is_deleted=False)
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
            MachineDowntimeEvent.objects.create(
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
    qs = MachineDowntimeEvent.objects.filter(
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

    return render(request, 'plant/maintenance_form.html', {
        'entries':             entries,
        'offset':              offset,
        'page_size':           page_size,
        'has_more':            has_more,
        'downtime_codes_json': json.dumps(downtime_codes_list),
        'lines_json':          json.dumps(prod_lines),
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
    Takes a MachineDowntimeEvent queryset `qs` and returns it
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
    """
    Bulk add or remove users from the "maintenance_active" group.

    Only users with maintenance access may perform this action.

    Expects a POST request with a JSON body containing:
      - "activate":   List of usernames to add to the group.
      - "deactivate": List of usernames to remove from the group.

    Processing:
      1. Parses the JSON payload; returns HTTP 400 on parse errors.
      2. Removes any usernames from `deactivate` that also appear in `activate`.
      3. Ensures the "maintenance_active" group exists.
      4. Adds each user in `activate` to the group.
      5. Removes each user in `deactivate` from the group.
      6. Returns a JSON response with the lists of processed usernames.

    Permissions
    -----------
    - Must be authenticated (`@login_required`).
    - Must satisfy `user_has_maintenance_access(request.user)` or returns HTTP 403.

    Parameters
    ----------
    request : django.http.HttpRequest
        The HTTP POST request with a JSON body.

    Returns
    -------
    django.http.JsonResponse or django.http.HttpResponseBadRequest/HttpResponseForbidden
        - On success: `{"status":"ok","activated": [...],"deactivated":[...]}`.
        - HTTP 400: if the JSON payload is invalid.
        - HTTP 403: if the user lacks maintenance access.
    """
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
    Given a MachineDowntimeEvent queryset, return a new queryset
    with all events whose labour_types == ["OPERATOR"] OR ["NA"] removed.
    """
    # Exclude any event whose labour_types exactly equals ["OPERATOR"] or ["NA"]
    return qs.exclude(
        Q(labour_types=["OPERATOR"])
    )


# Define the order in which roles should appear
ROLE_ORDER = ["electrician", "millwright", "tech", "plctech", "imt"]


def group_by_role(workers):
    """
    Organize a list of worker records into buckets by their primary role.

    Each worker is expected to be a dict containing at least:
      - 'roles':   A list of role strings (may be empty).
      - other keys such as 'username', 'name', etc.

    Workers are assigned to the bucket corresponding to their first-listed role
    (normalized to lowercase) in the predefined ROLE_ORDER sequence. Any worker
    whose primary role is not in ROLE_ORDER—or who has no roles—goes into the
    `"other"` bucket. The order of buckets in the result follows ROLE_ORDER,
    with `"other"` appended at the end.

    Parameters
    ----------
    workers : list of dict
        A list of worker dictionaries, each containing a 'roles' key.

    Returns
    -------
    collections.OrderedDict
        An ordered mapping from role keys (each from ROLE_ORDER plus "other")
        to lists of worker dicts whose primary role matches the key.
    """
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
    """
    Display and manage all live machine downtime events for maintenance staff.

    Access Control
    --------------
    - User must be authenticated.
    - User must satisfy `user_has_maintenance_access(request.user)`, otherwise HTTP 403.

    Data Preparation
    ----------------
    1. Build `prod_lines` via `get_prod_lines()` for line/operation/machine structure.
    2. Query live (not deleted, not closed) MachineDowntimeEvent records:
       - Annotate each with `line_priority` (fallback 999) and fetched participant relations.
       - Apply `annotate_being_worked_on` and `filter_out_operator_only_events`.
       - Order by priority then newest start.
    3. Take up to `PAGE_SIZE` entries, then for each:
       - Compute `start_display`: `"HH:MM"` if today, else `"MM/DD"`.
       - Set `user_has_open` if the current user is still on that event.
       - Build `current_worker_roles`: set of maintenance roles active on the event.
       - Build `current_usernames`: list of usernames currently joined.

    Worker Lists
    ------------
    4. Collect all active maintenance-role users, split into:
       - `active_users`: in “maintenance_active” group.
       - `inactive_users`: not in that group.
    5. For each group, build a list of dicts with:
       - `username`, `name`, `roles` (list), and `jobs` (their open events with machine, subcategory, priority).
    6. Bucket both active and inactive workers by primary role using `group_by_role()`.

    User Flags & Choices
    --------------------
    7. Determine `is_manager` and `is_supervisor` from user’s groups.
    8. Filter `MachineDowntimeEvent.LABOUR_CHOICES` based on user role membership.

    Code & Lines JSON
    -----------------
    9. Build `downtime_codes_json` for the modal, grouping subcategories by category.
   10. Prepare `lines_json` from `prod_lines`.

    Rendering
    ---------
    Renders "plant/maintenance_all_entries.html" with context:
      - entries, page_size, line_priorities
      - is_manager, is_supervisor
      - labour_choices
      - active_workers_by_role, inactive_workers_by_role
      - downtime_codes_json, lines_json

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming request; must be GET.

    Returns
    -------
    django.http.HttpResponse
        The rendered downtime entries page or HTTP 403 if unauthorized.
    """
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
        MachineDowntimeEvent.objects
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
    full_choices = MachineDowntimeEvent.LABOUR_CHOICES
    allowed_groups = {
        ROLE_TO_GROUP["electrician"],
        ROLE_TO_GROUP["millwright"],
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

    # 10) Final render
    return render(request, "plant/maintenance_all_entries.html", {
        "entries":                  entries,
        "page_size":                PAGE_SIZE,
        "line_priorities":          LinePriority.objects.all(),
        "is_manager":               is_manager,
        "is_supervisor":            is_supervisor,
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
        MachineDowntimeEvent.objects
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
    Retrieve the full labour participation history and comments for a specific downtime event.

    Only authenticated users may access this view.

    Workflow:
      1. Fetch the MachineDowntimeEvent by `event_id`, ensuring it exists and is not deleted.
      2. Query all DowntimeParticipation records for that event, ordered by `join_epoch`.
      3. For each participation:
         - Convert `join_epoch` and (if present) `leave_epoch` from epoch→aware local datetime→formatted string.
         - Gather the user’s maintenance roles based on their group memberships.
         - Include any join/leave comments and total minutes.
      4. Return a JSON response containing:
         - `history`: list of participation dicts with keys
             • id, user, roles, join_at, join_comment, leave_at, leave_comment, total_minutes
         - `event_comment`: the event’s opening comment
         - `closeout_comment`: the event’s close-out comment (or empty string)

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming request (must be GET).
    event_id : int
        Primary key of the downtime event to inspect.

    Returns
    -------
    django.http.JsonResponse
        JSON payload as described above, or HTTP 404 if the event is not found.
    """
    """
    Return the complete labour-history JSON for one downtime event,
    PLUS the event’s own opening and close-out comments.
    """
    # 1) validate event
    event = get_object_or_404(
        MachineDowntimeEvent,
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
    """
    Record a user’s participation start in a machine downtime event.

    Expects a POST request with a JSON body containing:
      - event_id (int):         The primary key of the MachineDowntimeEvent.
      - join_datetime (str):    The local join timestamp in ISO format "YYYY-MM-DDTHH:MM".
      - join_comment (str, opt): An optional comment about the join.

    Workflow:
      1. Parse and validate the JSON payload; return HTTP 400 on errors.
      2. Fetch the specified non-deleted downtime event; return HTTP 400 if not found.
      3. Parse the provided local-time string as an aware datetime in the server’s
         timezone (America/Toronto), convert it to UTC, and compute the epoch seconds.
      4. Create a DowntimeParticipation record with `event`, `user`, `join_epoch`, and `join_comment`.
      5. Return a JSON response with status "ok", the new participation ID, and the join epoch.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request carrying a JSON body.

    Returns
    -------
    django.http.JsonResponse or django.http.HttpResponseBadRequest
        - On success: `{"status":"ok","participation_id": <int>, "join_epoch": <int>}`.
        - HTTP 400: if payload is invalid, event not found, or datetime parse fails.
    """
    try:
        payload      = json.loads(request.body)
        event_id     = payload['event_id']
        comment      = payload.get('join_comment', '').strip()
        dt_str       = payload['join_datetime']       # e.g. "2025-05-06T14:30"
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    # fetch the event…
    event = MachineDowntimeEvent.objects.filter(pk=event_id, is_deleted=False).first()
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
    """
    Record a user’s departure from a machine downtime event and calculate duration.

    Expects a POST request with a JSON body containing:
      - event_id (int):          The primary key of the MachineDowntimeEvent.
      - leave_datetime (str):    The local leave timestamp in ISO format "YYYY-MM-DDTHH:MM".
      - leave_comment (str, opt): An optional comment for leaving.

    Workflow:
      1. Parse and validate the JSON payload; return HTTP 400 on parse errors or missing keys.
      2. Retrieve the most recent open DowntimeParticipation for this user and event;
         return HTTP 400 if none exists.
      3. Parse the provided leave timestamp as a naive datetime, localize to the server’s
         timezone (America/Toronto), convert to UTC, and compute the epoch seconds.
      4. Calculate the elapsed time since join (in seconds), round up to minutes, and
         update the participation’s `leave_epoch`, `leave_comment`, and `total_minutes`.
      5. Save the updated fields and return a JSON response with status "ok",
         the leave epoch, and total minutes.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP POST request with a JSON body.

    Returns
    -------
    django.http.JsonResponse
        On success: `{"status":"ok","leave_epoch": <int>, "total_minutes": <int>}`.
    django.http.HttpResponseBadRequest
        If payload is invalid, no open participation is found, or datetime parsing fails.
    """
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
    """
    Build a lookup of machine numbers to their line priority.

    Queries the LinePriority table for all (line → priority) mappings,
    then walks the current production lines (via get_prod_lines()) to
    assign each machine’s number its corresponding line priority.

    If a machine’s line has no priority entry, its value will be None.

    Returns
    -------
    dict[str, int | None]
        A dictionary mapping each machine_number (as used in DowntimeMachine)
        to its line’s priority integer, or None if no priority is defined.
    """
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
    Adjust the ordering of line priorities by swapping one entry with its neighbor.

    Only accepts POST requests from authenticated users.

    Parameters
    ----------
    request : django.http.HttpRequest
        The HTTP request object. If the request is AJAX (XMLHttpRequest), a JSON
        response is returned; otherwise the user is redirected back.
    pk : int
        Primary key of the LinePriority record to move.
    direction : str
        Movement direction:
          - "up":    Swap with the entry having the next higher urgency (lower number).
          - "down":  Swap with the entry having the next lower urgency (higher number).

    Workflow
    --------
    1. Validate `direction`; return HTTP 400 if invalid.
    2. Retrieve the `current` LinePriority by `pk`, 404 if not found.
    3. Find the adjacent `neighbor` based on `direction`.
    4. If a neighbor exists, perform an atomic swap of their `priority` values.
    5. On AJAX requests, return JSON with the moved entry’s new priority and neighbor’s id.
       Otherwise, redirect back to the referring page or the default list view.

    Returns
    -------
    django.http.JsonResponse
        On AJAX: `{"status":"ok","id":<pk>,"new_priority":<int>,"swapped_with":<neighbor_pk>}`
    django.http.HttpResponseRedirect
        On non-AJAX: redirects back to the referer or the downtime entries list.
    django.http.HttpResponseBadRequest
        If `direction` is not "up" or "down".
    """
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
}

@require_POST
def add_employee(request):
    """
    Create or update a user account (real or preload) and synchronize their maintenance role groups.

    Workflow:
      1. Read and normalize `first_name`, `last_name`, and `roles` from POST data.
      2. Validate that both first and last names are provided; on failure, flash an error and redirect back.
      3. Construct a base username (`first.last`) and a preload variant (`first.last@preload`).
      4. Look up an existing real user by base username, then by preload username.
      5. If no user exists, create a new preload account with a random password and staff privileges.
      6. Determine the desired maintenance groups from the submitted roles.
      7. For each role in `ROLE_TO_GROUP`, add or remove the corresponding group membership.
      8. Save the user and flash a success message indicating whether the account was created or updated.

    Parameters
    ----------
    request : django.http.HttpRequest
        A POST request containing form fields:
          - `first_name` (str): Employee’s first name.
          - `last_name` (str): Employee’s last name.
          - `roles` (list of str): Selected maintenance role codes.

    Returns
    -------
    django.http.HttpResponseRedirect
        Redirects back to the referring page (or index) with appropriate Django message(s)
        indicating success or required inputs.
    """
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
    """
    Provide JSON data for editing a machine downtime entry, including the entry’s details
    and all reference lists needed for dependent dropdowns.

    The response JSON contains:
      - status:           "ok" or error
      - entry_id:         The primary key of the downtime event
      - line:             Current line identifier
      - machine:          Current machine number
      - category_code:    The prefix of the downtime code (before the first “–”)
      - category_name:    The human-readable category label
      - subcategory_code: The full downtime code (category + “–” + subcategory)
      - start_date:       Local date portion of the event start ("YYYY-MM-DD")
      - start_time:       Local time portion of the event start ("HH:MM")
      - comment:          The event’s comment
      - labour_types:     The list of labour type codes currently assigned
      - employee_id:      The associated employee identifier (if any)
      - lines:            Flat list of all available line identifiers
      - machines:         Flat, sorted list of all available machine numbers
      - categories:       List of dicts with keys `code` and `name` for each category
      - subcategories:    List of dicts with keys `code`, `name`, and `parent` for each subcategory
      - lines_data:       Full nested structure of lines → operations → machines

    Parameters
    ----------
    request : django.http.HttpRequest
        A POST request with JSON body containing:
          - entry_id (int): ID of the downtime event to edit.

    Returns
    -------
    django.http.JsonResponse
        A JSON object as described above, or HTTP 400 if the payload is invalid
        or the specified entry does not exist.
    """
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
        e = MachineDowntimeEvent.objects.get(pk=entry_id, is_deleted=False)
    except MachineDowntimeEvent.DoesNotExist:
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
    Update an existing machine downtime event with edited details.

    Expects a POST request with a JSON body containing:
      - entry_id (int):         The primary key of the MachineDowntimeEvent.
      - line (str):             The production line identifier.
      - machine (str):          The machine number.
      - category (str):         The category code prefix (e.g. "MECH").
      - subcategory (str):      The full downtime code (e.g. "MECH-TOOL").
      - start_at (str):         The new start timestamp in "YYYY-MM-DD HH:MM" format.
      - comment (str):          The downtime comment/description.
      - labour_types (list):    Optional list of labour type codes.

    Workflow:
      1. Parse and validate the JSON payload; return HTTP 400 if malformed or missing required fields.
      2. Retrieve the non-deleted MachineDowntimeEvent by `entry_id`; return HTTP 400 if not found.
      3. Look up the DowntimeCode for `subcategory` to derive `category` and `subcategory` display names;
         return HTTP 400 if the code is invalid.
      4. Parse `start_at` as a naive datetime, localize to the default timezone, and convert to epoch seconds;
         return HTTP 400 on format errors.
      5. Update the event’s fields (`line`, `machine`, `category`, `subcategory`, `code`,
         `start_epoch`, `comment`, `labour_types`) and save.
      6. Return a JsonResponse `{'status': 'ok'}` on success.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming POST request with the JSON payload.

    Returns
    -------
    django.http.JsonResponse
        `{'status': 'ok'}` on successful update.
    django.http.HttpResponseBadRequest
        If the payload is invalid, the event is not found, the code is invalid,
        or the date format is incorrect.
    """
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
        event = MachineDowntimeEvent.objects.get(pk=entry_id, is_deleted=False)
    except MachineDowntimeEvent.DoesNotExist:
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
    """
    Display and manage the list of downtime codes.

    GET:
      - Retrieves all DowntimeCode records.
      - Builds distinct lists of existing categories and subcategories.
      - Renders the "plant/downtime_codes_list.html" template with context:
          • codes: QuerySet of all DowntimeCode instances.
          • categories: List of unique category strings.
          • subcategories: List of unique subcategory strings.

    POST:
      - Reads `code`, `category`, and `subcategory` from form data.
      - If all are provided, creates a new DowntimeCode record.
      - Redirects back to the same view to display the updated list.

    Parameters
    ----------
    request : django.http.HttpRequest
        The HTTP request object. On POST, carries form-encoded fields
        `code`, `category`, and `subcategory`; on GET, is used to render the page.

    Returns
    -------
    django.http.HttpResponseRedirect
        After successful POST, redirects to 'downtime_codes_list'.
    django.http.HttpResponse
        On GET, renders the downtime codes list page.
    """
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
    """
    AJAX endpoint to create a new DowntimeCode record.

    Expects form-encoded POST parameters:
      - code (str):        The unique downtime code identifier.
      - category (str):    The human-readable category name.
      - subcategory (str): The human-readable subcategory name.

    Responses
    ---------
    - Success (HTTP 201):
        JSON with:
          • id (int):            The new DowntimeCode primary key.
          • code (str)
          • category (str)
          • subcategory (str)
          • updated_at (str):     Timestamp of creation formatted as "YYYY-MM-DD HH:MM".
    - Failure (HTTP 400):
        JSON with:
          • error (str): Description of the validation error.

    Error Conditions
    ----------------
    - Any of `code`, `category`, or `subcategory` is missing or empty.
    - A DowntimeCode with the given `code` already exists.
    """
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
    """
    AJAX endpoint to update an existing DowntimeCode record.

    Expects form-encoded POST parameters:
      - code (str):        The new downtime code identifier.
      - category (str):    The updated category name.
      - subcategory (str): The updated subcategory name.

    Workflow:
      1. Retrieve the DowntimeCode by primary key or return HTTP 404.
      2. Validate that `code`, `category`, and `subcategory` are all provided;
         on missing fields, return HTTP 400 with an error.
      3. If the `code` has changed, ensure no other record uses the same code;
         on conflict, return HTTP 400 with an error.
      4. Update the object’s fields and save.
      5. Return a JSON response including the record’s id, code, category,
         subcategory, and the `updated_at` timestamp formatted as "YYYY-MM-DD HH:MM".

    Responses
    ---------
    - Success (HTTP 200):
        JSON with keys `id`, `code`, `category`, `subcategory`, `updated_at`.
    - Failure (HTTP 400):
        JSON with key `error` describing the issue.
    """
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
    """
    AJAX endpoint to delete a DowntimeCode record.

    Expects
    --------
    pk : int
        The primary key of the DowntimeCode to delete, passed as a URL parameter.

    Workflow
    --------
    1. Retrieve the DowntimeCode object by `pk`, returning HTTP 404 if not found.
    2. Delete the object from the database.
    3. Return a JSON response indicating success.

    Returns
    -------
    django.http.JsonResponse
        On success: `{'success': True}`.
    Raises
    ------
    django.http.Http404
        If no DowntimeCode with the given `pk` exists.
    """
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
    """
    AJAX endpoint to retrieve the downtime and participation history for a given machine.

    Expects form-encoded POST data with:
      - machine (str): The machine identifier to query (required).

    Workflow:
      1. Validate that the `machine` parameter is provided; return HTTP 400 if missing.
      2. Query the 500 most recent non-deleted MachineDowntimeEvent records for that machine,
         ordered by descending start_epoch.
      3. For each event, collect:
         - id, start_epoch, start_display, closeout_epoch, closeout_display
         - category, subcategory, code, comment, closeout_comment
         - participations: a list of dicts for each DowntimeParticipation, containing:
             • user: full name or username
             • join_epoch, join_display
             • leave_epoch, leave_display (or None)
             • join_comment, leave_comment
             • total_minutes
      4. Assemble the data into a JSON object under the `"events"` key.

    Returns
    -------
    django.http.JsonResponse
        - On success: `{"events": [ ... ]}` with the structure described above.
        - HTTP 400: `{"error": "Machine parameter is required."}` if no machine provided.
    """
    machine = request.POST.get("machine", "").strip()
    if not machine:
        return JsonResponse({"error": "Machine parameter is required."}, status=400)

    events = (
        MachineDowntimeEvent.objects
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
    """
    Display and optionally export the login status of maintenance staff accounts.

    Access Control
    --------------
    - User must be authenticated.
    - User must have maintenance access or receives HTTP 403.

    Functionality
    -------------
    1. Retrieves all users belonging to any maintenance role group.
    2. For each user:
       - Gathers their roles, account type (real vs. preload), and last login info.
       - Determines whether they are currently logged in.
       - Tallies counts of real vs. preload accounts per role.
    3. If `?format=csv` is in the query string, returns a CSV download with columns:
       Name, Username, Role(s), Account Type, Last Login, Logged In?
    4. Otherwise, renders the 'plant/employee_login_status.html' template with:
       - `users`: list of user status dicts
       - `summary`: list of per-role real/preload counts

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming GET request; may include `format=csv` for CSV export.

    Returns
    -------
    django.http.HttpResponse
        - CSV file download if requested.
        - HTML page rendering otherwise.
    """
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
    """
    Provide a JSON list of available production line identifiers.

    GET:
      - Calls `get_prod_lines()` to build the nested line/operation/machine structure.
      - Extracts just the `line` names from each block.
      - Returns a JsonResponse with `{"lines": [...]}`.

    Other methods:
      - Returns HTTP 405 Method Not Allowed.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming HTTP request; expected to be a GET.

    Returns
    -------
    django.http.JsonResponse
        On GET: JSON object containing the `lines` list.
    django.http.HttpResponse
        On non-GET: HTTP 405 response with no body.
    """
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
    Allow a supervisor or manager to forcibly close out another user’s open participation.

    Expects a POST request with a JSON body containing:
      - leave_comment (str):  Mandatory non-empty comment explaining the forced leave.
      - leave_datetime (str, optional): ISO local timestamp "YYYY-MM-DDTHH:MM" at which to record the leave;
        if omitted, the current time is used.

    Workflow:
      1. Parse and validate JSON; return HTTP 400 if `leave_comment` is missing or empty.
      2. Parse `leave_datetime` (if provided) into an aware UTC epoch; return HTTP 400 on format errors.
      3. Retrieve the open DowntimeParticipation by `pk`, ensuring the event is live and not closed.
      4. Ensure the leave timestamp is strictly after the original join; return HTTP 400 otherwise.
      5. Compute total minutes (rounding up), set `leave_epoch`, `leave_comment`, and `total_minutes`.
      6. Save the participation and return JSON `{"status":"ok","leave_epoch":<int>,"total_minutes":<int>}`.

    Permissions
    -----------
    - Must be authenticated (`@login_required`).
    - Must pass `user_is_supervisor_or_manager` test or receives HTTP 403.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming POST request carrying a JSON body.
    pk : int
        Primary key of the DowntimeParticipation to force-close.

    Returns
    -------
    django.http.JsonResponse
        On success: `{"status":"ok","leave_epoch": <int>,"total_minutes": <int>}`.
    django.http.HttpResponseBadRequest
        If payload is invalid, comment missing, datetime parse fails, or leave before join.
    django.http.Http404
        If no matching open participation is found.
    """
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
    """
    Bulk-add downtime entries for one production line across multiple machines.

    GET:
      - Builds and renders the bulk-entry form with:
        • prod_lines: nested JSON structure of lines → operations → machines.
        • downtime_codes_json: list of downtime categories and their subcategories.

    POST:
      - Reads form fields:
          • line (str)
          • machines (list of str)
          • category (str)
          • subcategory (str, optional)
          • start_date (str, "YYYY-MM-DD")
          • start_time (str, "HH:MM")
          • description (str)
          • employee_id (str, optional)
          • labour_types (JSON-encoded list)
      - Validates:
          • At least one machine selected.
          • Category is provided and valid.
          • Subcategory (if given) is valid.
          • Date/time is in the correct format.
      - Parses `labour_types` JSON and localizes the start datetime (America/Toronto → UTC epoch).
      - Creates a MachineDowntimeEvent for each selected machine, sharing the same metadata.
      - Redirects to the maintenance list view on success; returns HTTP 400 on any validation error.

    Parameters
    ----------
    request : django.http.HttpRequest
        The HTTP request object. For GET, used to render the form; for POST, carries the bulk-entry data.

    Returns
    -------
    django.http.HttpResponse
        On GET: renders "plant/maintenance_bulk_form.html" with the necessary context.
    django.http.HttpResponseRedirect
        On successful POST: redirects to the "maintenance_all" view.
    django.http.HttpResponseBadRequest
        On POST: if any required field is missing or invalid.
    """
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
            MachineDowntimeEvent.objects.create(
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

    return render(request, 'plant/maintenance_bulk_form.html', {
        'lines_json':           json.dumps(prod_lines),
        'downtime_codes_json':  json.dumps(downtime_codes_list),
    })




# ========================================================================
# ========================================================================
# ================ Quickadd Feature for supervisors  =====================
# ========================================================================
# ========================================================================

@login_required(login_url="login")
def quick_add(request):
    """
    Display a form for, and process, the creation of a single downtime entry.

    GET:
      - Renders the "plant/quick_add.html" template with:
        • `lines_json`: Nested JSON of production lines → operations → machines.
        • `downtime_codes_json`: List of downtime categories and subcategories.
        • `labour_choices`: The available labour type choices.

    POST:
      - Reads form fields:
          • line (str):            Production line identifier.
          • machine (str):         Machine number.
          • category (str):        Category code prefix.
          • subcategory (str):     Full downtime code (optional).
          • start_date (str):      "YYYY-MM-DD".
          • start_time (str):      "HH:MM".
          • description (str):     Comment for the downtime.
          • employee_id (str):     Optional employee identifier.
          • labour_types (JSON):   JSON-encoded list of labour type codes.
      - Validates:
          • A machine is selected.
          • Category is provided and valid.
          • Subcategory (if given) is valid.
          • Date/time format is correct.
      - Parses `labour_types` JSON and localizes the start datetime
        (America/Toronto → UTC epoch).
      - Creates one `MachineDowntimeEvent` with the provided details.
      - Redirects to the maintenance list view on success; returns HTTP 400
        for any validation errors.

    Parameters
    ----------
    request : django.http.HttpRequest
        The incoming request. GET to render the form; POST to submit data.

    Returns
    -------
    django.http.HttpResponse
        - On GET: renders the quick-add form page.
        - On successful POST: redirects to 'maintenance_all'.
    django.http.HttpResponseBadRequest
        - On POST: if any required field is missing or invalid.
    """
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
        MachineDowntimeEvent.objects.create(
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

    return render(request, 'plant/quick_add.html', {
        'lines_json':           json.dumps(prod_lines),
        'downtime_codes_json':  json.dumps(downtime_codes_list),
        'labour_choices':      MachineDowntimeEvent.LABOUR_CHOICES,
    })
