import json
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse, HttpResponseRedirect
from datetime import datetime
from ..models.maintenance_models import MachineDowntimeEvent, LinePriority, DowntimeParticipation, DowntimeCode
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
from prod_query.views import lines as prod_lines_initial, lines_untracked as prod_lines_untracked
from django.views.decorators.csrf import csrf_exempt  # or use @ensure_csrf_cookie / csrf_protect
from django.template.loader import render_to_string


# ============================================================================
# ============================================================================
# ============================================================================
# ============================================================================
'''
You may wonder what this is. I did this to silently merge the untracked lines object into the lines object so it doesn't affect any OEE calculations 
but reflects the needs of the maintenance app that still has machines that go down even machines that are not being tracked
'''
# build a map by line name
_by_name = { L['line']: L.copy() for L in prod_lines_initial }

for un in prod_lines_untracked:
    name = un['line']
    if name in _by_name:
        # for each op in the untracked block, try to find the same op code
        for un_op in un['operations']:
            # look for a matching op in the tracked block
            match = next((op for op in _by_name[name]['operations']
                          if op['op'] == un_op['op']), None)
            if match:
                match['machines'].extend(un_op['machines'])
            else:
                # if it’s a brand-new op, just append it
                _by_name[name]['operations'].append(un_op)
    else:
        # brand-new line entirely
        _by_name[name] = un

# finally, your merged list:
prod_lines = list(_by_name.values())

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
    Close out a downtime event and auto-leave all participants.
    Expects JSON body:
      {
        "entry_id":           <int>,
        "closeout":           "YYYY-MM-DD HH:MM",
        "closeout_comment":   <string>
      }
    """
    # ── 1) parse payload ───────────────────────────────────────────────────────
    try:
        payload          = json.loads(request.body)
        entry_id         = payload['entry_id']
        close_str        = payload['closeout']            # e.g. "2025-05-01 18:08"
        closeout_comment = payload['closeout_comment']
        close_dt         = datetime.strptime(close_str, "%Y-%m-%d %H:%M")
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    # ── 2) fetch event ─────────────────────────────────────────────────────────
    try:
        event = MachineDowntimeEvent.objects.get(pk=entry_id, is_deleted=False)
    except MachineDowntimeEvent.DoesNotExist:
        return HttpResponseBadRequest("Entry not found")

    # ── 3) compute epoch ───────────────────────────────────────────────────────
    epoch_ts = int(close_dt.timestamp())

    # ── 4) perform updates atomically ─────────────────────────────────────────
    with transaction.atomic():
        # 4a) close out the event itself
        event.closeout_epoch   = epoch_ts
        event.closeout_comment = closeout_comment
        event.save(update_fields=['closeout_epoch', 'closeout_comment'])

        # 4b) find all still-joined participations
        open_parts = DowntimeParticipation.objects.filter(
            event=event,
            leave_epoch__isnull=True
        )

        # 4c) mark each one as left at the same epoch
        for part in open_parts:
            part.leave_epoch   = epoch_ts
            part.leave_comment = f"Job is finished: {closeout_comment}"
            # round up to whole minutes
            part.total_minutes = math.ceil((epoch_ts - part.join_epoch) / 60)
            part.save(update_fields=['leave_epoch', 'leave_comment', 'total_minutes'])

    # ── 5) respond to caller ───────────────────────────────────────────────────
    return JsonResponse({
        'status':          'ok',
        'closed_at_epoch': epoch_ts,
    })





def maintenance_entries(request: HttpRequest) -> JsonResponse:
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





def maintenance_form(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        # ——— Pull Form Data ———
        entry_id    = request.POST.get('entry_id')      # None for “Add”
        line        = request.POST.get('line', '').strip()
        machine     = request.POST.get('machine', '').strip()
        cat_code    = request.POST.get('category', '').strip()
        sub_code    = request.POST.get('subcategory', '').strip()
        start_date  = request.POST.get('start_date', '') # "YYYY-MM-DD"
        start_time  = request.POST.get('start_time', '') # "HH:MM"
        description = request.POST.get('description', '').strip()
        employee_id = request.POST.get('employee_id', '').strip()  # Pull the employee_id from the form

        # ——— Parse Out the List of Labour Codes ———
        raw_labour = request.POST.get('labour_types', '[]')
        try:
            labour_list = json.loads(raw_labour)
            if not isinstance(labour_list, list):
                labour_list = []
        except json.JSONDecodeError:
            labour_list = []

        # ——— Lookup Display Names from DowntimeCode Model ———
        try:
            # Fetch the subcategory DowntimeCode instance
            sub_code_obj = DowntimeCode.objects.get(code=sub_code)
            category_name = sub_code_obj.category
            subcategory_name = sub_code_obj.subcategory
        except DowntimeCode.DoesNotExist:
            return HttpResponseBadRequest("Invalid category or subcategory code")

        # ——— Build Epoch Timestamp ———
        try:
            dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
            # Make timezone-aware based on your project's settings
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_default_timezone())
        except ValueError:
            return HttpResponseBadRequest("Invalid date/time format")
        epoch_ts = int(dt.timestamp())

        # ——— Create or Update Maintenance Downtime Event ———
        if entry_id:
            # Update Existing
            e = get_object_or_404(MachineDowntimeEvent, pk=entry_id, is_deleted=False)
            e.line           = line
            e.machine        = machine
            e.category       = category_name
            e.subcategory    = subcategory_name
            e.code           = sub_code
            e.start_epoch    = epoch_ts
            e.comment        = description
            e.labour_types   = labour_list
            e.employee_id    = employee_id     # Set employee_id
            e.save(update_fields=[
                'line', 'machine', 'category', 'subcategory',
                'code', 'start_epoch', 'comment', 'labour_types', 'employee_id'
            ])
        else:
            # Create New
            MachineDowntimeEvent.objects.create(
                line           = line,
                machine        = machine,
                category       = category_name,
                subcategory    = subcategory_name,
                code           = sub_code,
                start_epoch    = epoch_ts,
                comment        = description,
                labour_types   = labour_list,
                employee_id    = employee_id      # Set employee_id
            )

        # ——— Redirect to Same Page (Preserve ?offset=…) ———
        return redirect(request.get_full_path())

    # ——— GET: Render Form + List of Open Entries ———
    offset    = int(request.GET.get('offset', 0))
    page_size = 300
    qs = MachineDowntimeEvent.objects.filter(
        is_deleted=False,
        closeout_epoch__isnull=True
    ).order_by('-start_epoch')
    total     = qs.count()
    page_objs = list(qs[offset: offset + page_size])
    has_more  = (offset + page_size) < total

    # ——— Fetch All Downtime Codes and Structure Them ———
    downtime_codes = DowntimeCode.objects.all().order_by('category', 'subcategory', 'code')
    structured_codes = {}
    for code_obj in downtime_codes:
        cat_code = code_obj.code.split('-', 1)[0]  # Assumes category code is the prefix before '-'
        if cat_code not in structured_codes:
            structured_codes[cat_code] = {
                'name': code_obj.category,
                'code': cat_code,
                'subcategories': []
            }
        structured_codes[cat_code]['subcategories'].append({
            'name': code_obj.subcategory,
            'code': code_obj.code
        })

    # Convert the structured dictionary to a list
    downtime_codes_list = list(structured_codes.values())

    # ——— Prepare Context ———
    context = {
        'downtime_codes_json': mark_safe(json.dumps(downtime_codes_list)),
        'lines_json':          mark_safe(json.dumps(prod_lines)),
        'entries':             page_objs,
        'offset':              offset,
        'page_size':           page_size,
        'has_more':            has_more,
        # You can also pass your labour-choices to the template if needed:
        # 'labour_choices': MachineDowntimeEvent.LABOUR_CHOICES,
    }

    return render(request, 'plant/maintenance_form.html', context)











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
def toggle_active(request):
    # only managers may do this
    if not user_has_maintenance_access(request.user):
        return HttpResponseForbidden("Not authorized")

    # use FormData in JS so request.POST is populated
    username = request.POST.get("username")
    action   = request.POST.get("action")  # "activate" or "deactivate"
    if not username or action not in ("activate", "deactivate"):
        return HttpResponseBadRequest("Invalid parameters")

    User = get_user_model()
    user = get_object_or_404(User, username=username)
    grp, _ = Group.objects.get_or_create(name="maintenance_active")

    if action == "activate":
        user.groups.add(grp)
    else:
        user.groups.remove(grp)

    return JsonResponse({"status": "ok", "action": action, "username": username})








# --------------------------- rewritten view ---------------------------------- #

def filter_out_operator_only_events(qs):
    """
    Given a MachineDowntimeEvent queryset, return a new queryset
    with all events whose labour_types == ["OPERATOR"] removed.
    """
    # Find IDs of operator‑only events
    operator_only_ids = list(
        qs
        .filter(labour_types=["OPERATOR"])   # If your JSONField supports direct list lookups
        .values_list("id", flat=True)
    )
    if operator_only_ids:
        print(f"Excluding operator‑only event IDs: {operator_only_ids}")
    # Return qs without those IDs
    return qs.exclude(id__in=operator_only_ids)




@login_required(login_url='login')
def list_all_downtime_entries(request):
    # ── 1) Access Control ───────────────────────────────────────────────
    if not user_has_maintenance_access(request.user):
        return HttpResponseForbidden("Not authorized; please ask a manager.")

    # ── 2) Build & Annotate Open-Events Queryset ─────────────────────────
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
                output_field=IntegerField(),
            )
        )
        .order_by("line_priority", "-start_epoch")
        .prefetch_related("participants__user")
    )
    qs = annotate_being_worked_on(base_qs)

    # ── 2b) Strip Out Operator-Only Events ─────────────────────────────
    qs = filter_out_operator_only_events(qs)

    # ── 3) Format First PAGE_SIZE Entries for Left Table ────────────────
    entries = list(qs[:PAGE_SIZE])
    today   = timezone.localdate()
    tz      = get_default_timezone()
    for e in entries:
        dt = e.start_at
        if is_naive(dt):
            dt = make_aware(dt, tz)
        local_dt = localtime(dt)
        e.start_display = (
            local_dt.strftime('%H:%M')
            if local_dt.date() == today
            else local_dt.strftime('%m/%d')
        )
        e.user_has_open = e.participants.filter(
            user=request.user, leave_epoch__isnull=True
        ).exists()

    # ── 4) Gather All Maintenance-Role Users ────────────────────────────
    User = get_user_model()
    maintenance_group_names = set(ROLE_TO_GROUP.values())
    users = (
        User.objects
        .filter(groups__name__in=maintenance_group_names, is_active=True)
        .distinct()
        .order_by('username')
    )

    # ── 5) Partition into Active vs Inactive Based on maintenance_active Group ─
    active_grp, _   = Group.objects.get_or_create(name="maintenance_active")
    active_qs       = users.filter(groups=active_grp)
    inactive_qs     = users.exclude(groups=active_grp)

    def build_worker_list(qs):
        lst = []
        for u in qs:
            name = u.get_full_name() or u.username
            user_groups = set(u.groups.values_list("name", flat=True))
            roles = [
                role for role, grp in ROLE_TO_GROUP.items()
                if grp in user_groups
            ]
            parts = DowntimeParticipation.objects.filter(
                user=u,
                leave_epoch__isnull=True,
                event__closeout_epoch__isnull=True
            ).select_related('event')
            jobs = [
                {"machine": p.event.machine, "subcategory": p.event.subcategory}
                for p in parts
            ]
            lst.append({
                "username": u.username,
                "name":     name,
                "roles":    roles,
                "jobs":     jobs,
            })
        return sorted(lst, key=lambda w: w["name"])

    active_workers   = build_worker_list(active_qs)
    inactive_workers = build_worker_list(inactive_qs)

    # ── 6) Determine Manager Flag & Roles for Current User ───────────────
    user_groups   = set(request.user.groups.values_list("name", flat=True))
    is_manager    = "maintenance_managers" in user_groups
    is_supervisor = "maintenance_supervisors" in user_groups
    user_roles    = [
        r for r, grp in ROLE_TO_GROUP.items()
        if grp in user_groups
    ]

    # ── 7) Fetch and Structure Downtime Codes from Database ──────────────
    downtime_codes = DowntimeCode.objects.all().order_by('category', 'subcategory', 'code')
    structured_codes = {}
    for code_obj in downtime_codes:
        # Extract the category code (assumes it's the prefix before the first '-')
        cat_code = code_obj.code.split('-', 1)[0]  
        if cat_code not in structured_codes:
            structured_codes[cat_code] = {
                'name': code_obj.category,
                'code': cat_code,
                'subcategories': []
            }
        structured_codes[cat_code]['subcategories'].append({
            'name': code_obj.subcategory,
            'code': code_obj.code
        })

    # Convert the structured dictionary to a list for JSON serialization
    downtime_codes_list = list(structured_codes.values())

    # ── 8) Render ─────────────────────────────────────────────────────────
    return render(request, "plant/maintenance_all_entries.html", {
        "entries":             entries,
        "page_size":           PAGE_SIZE,
        "line_priorities":     LinePriority.objects.all(),
        "is_manager":          is_manager,
        "is_supervisor":       is_supervisor,
        "labour_choices":      MachineDowntimeEvent.LABOUR_CHOICES,
        "user_roles":          user_roles,
        "active_workers":      active_workers,
        "inactive_workers":    inactive_workers,
        'downtime_codes_json': mark_safe(json.dumps(downtime_codes_list)),
        'lines_json':          mark_safe(json.dumps(prod_lines)),
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
    # 1) ensure the event exists
    event = get_object_or_404(
        MachineDowntimeEvent,
        pk=event_id,
        is_deleted=False
    )

    # 2) pull all participations for that event, in chronological order
    parts = (
        DowntimeParticipation.objects
        .filter(event=event)
        .order_by('join_epoch')
        .select_related('user')
    )

    # 3) serialize them
    tz = get_default_timezone()
    history = []
    for p in parts:
        # — join time
        jdt = datetime.fromtimestamp(p.join_epoch)
        if is_naive(jdt):
            jdt = make_aware(jdt, tz)
        jdt = localtime(jdt)
        join_at = jdt.strftime('%Y-%m-%d %H:%M')

        # — leave time (may be null)
        if p.leave_epoch:
            ldt = datetime.fromtimestamp(p.leave_epoch)
            if is_naive(ldt):
                ldt = make_aware(ldt, tz)
            ldt = localtime(ldt)
            leave_at = ldt.strftime('%Y-%m-%d %H:%M')
        else:
            leave_at = None

        # — compute this user’s maintenance roles
        user_group_names = set(
            p.user.groups.values_list('name', flat=True)
        )
        roles = [
            role
            for role, group_name in ROLE_TO_GROUP.items()
            if group_name in user_group_names
        ]

        history.append({
            'user'          : p.user.username,
            'roles'         : roles,
            'join_at'       : join_at,
            'join_comment'  : p.join_comment,
            'leave_at'      : leave_at or '',
            'leave_comment' : p.leave_comment or '',
            'total_minutes': p.total_minutes or 0,
        })

    return JsonResponse({'history': history})


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
        'subcategory_code': e.code,
        'start_date':       local.strftime('%Y-%m-%d'),
        'start_time':       local.strftime('%H:%M'),
        'comment':          e.comment,
        'labour_types':     e.labour_types,  # ← added
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
    """
    AJAX endpoint: receives {"machine": "..."} and returns
    a rendered HTML accordion of that machine’s last 5000 downtime events.
    """
    try:
        payload = json.loads(request.body.decode())
        machine = payload.get('machine')
        # fetch up to 500 events, oldest first, excluding soft‐deleted
        events = (MachineDowntimeEvent.objects
                  .filter(machine=machine, is_deleted=False)
                  .order_by('-start_epoch')[:500]
                  .prefetch_related('participants__user'))
        html = render_to_string(
            'maintenance/snippets/machine_history.html',
            {'events': events},
            request=request
        )
        return JsonResponse({'status': 'ok', 'html': html})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)