import json
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse, HttpResponseRedirect
from datetime import datetime
from ..models.maintenance_models import MachineDowntimeEvent, LinePriority, DowntimeParticipation
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
# views/employee_views.py
from django.contrib import messages
from django.contrib.auth.models import Group
from django.utils.crypto import get_random_string
from django.http        import HttpResponseForbidden




# import your lines structure
from prod_query.views import lines as prod_lines

# ——— module-wide downtime codes ———
DOWNTIME_CODES = [
    {
        'name': 'Mechanical / Equipment Failure',
        'code': 'MECH',
        'subcategories': [
            {'name': 'Tooling Failure',             'code': 'MECH-TOOL'},
            {'name': 'Breakdown / Seized Component','code': 'MECH-BRK'},
            {'name': 'Unplanned Maintenance',       'code': 'MECH-MNT'},
            {'name': 'Starved (No Material)',       'code': 'MECH-STAR'},
            {'name': 'Blocked (Downstream)',        'code': 'MECH-BLKD'},
            {'name': 'Tool Wear / Degradation',     'code': 'MECH-TWR'},
            {'name': 'Poor Lubrication / Oil Issue','code': 'MECH-LUB'},
            {'name': 'Hydraulic Failure',           'code': 'MECH-HYD'},
            {'name': 'Pneumatic Failure',           'code': 'MECH-PNEU'},
            {'name': 'Environmental Mechanical Issue','code': 'MECH-ENV'},
            {'name': 'Loose / Missing Components',  'code': 'MECH-LOOSE'},
        ],
    },
    {
        'name': 'Electrical Failure',
        'code': 'ELEC',
        'subcategories': [
            {'name': 'Sensor Misaligned / Blocked', 'code': 'ELEC-SENS'},
            {'name': 'Faulty Wiring / Connections', 'code': 'ELEC-WIRE'},
            {'name': 'Power Loss / Electrical Fault','code': 'ELEC-POW'},
            {'name': 'Control System Fault',        'code': 'ELEC-CONT'},
            {'name': 'Circuit Breaker Tripped',     'code': 'ELEC-BRK'},
            {'name': 'Startup or Shutdown Delay',   'code': 'ELEC-SS'},
            {'name': 'Motor / Drive Fault',         'code': 'ELEC-MOT'},
        ],
    },
    {
        'name': 'Automation / Robotics',
        'code': 'AUTO',
        'subcategories': [
            {'name': 'Robot Fault',                 'code': 'AUTO-RBT'},
            {'name': 'Gripper / End Effector Issue','code': 'AUTO-GRP'},
            {'name': 'Sensor Feedback Issue',       'code': 'AUTO-SENS'},
            {'name': 'Sequence Logic / Program Issue','code': 'AUTO-PROG'},
            {'name': 'Tool Arm Jam / Error',        'code': 'AUTO-ARM'},
            {'name': 'Camera / Vision Fault',       'code': 'AUTO-CAM'},
        ],
    },
    {
        'name': 'Temperature / Environmental',
        'code': 'TEMP',
        'subcategories': [
            {'name': 'Overtemperature (Machine)',   'code': 'TEMP-OVR'},
            {'name': 'Control Cabinet Overheat',    'code': 'TEMP-CAB'},
            {'name': 'Ambient Environmental Issue', 'code': 'TEMP-ENV'},
            {'name': 'Cooling System Failure',      'code': 'TEMP-COOL'},
        ],
    },
    {
        'name': 'Setup / Changeover / Adjustments',
        'code': 'SETUP',
        'subcategories': [
            {'name': 'Changeover',                  'code': 'SETUP-CHG'},
            {'name': 'Major Adjustment / Re-tool', 'code': 'SETUP-ADJ'},
            {'name': 'Tooling / Calibration Change','code': 'SETUP-TOOL'},
            {'name': 'Planned Cleaning / Warm-up', 'code': 'SETUP-CLEAN'},
            {'name': 'Planned Maintenance',         'code': 'SETUP-MNT'},
            {'name': 'Quality Check / In-process',  'code': 'SETUP-INSP'},
        ],
    },
    {
        'name': 'Material or Supply Issues',
        'code': 'MAT',
        'subcategories': [
            {'name': 'Misfeed / Jammed Material',   'code': 'MAT-JAM'},
            {'name': 'Poor Quality / Out-of-Spec',  'code': 'MAT-QUAL'},
            {'name': 'Damaged / Defective Material','code': 'MAT-DEF'},
            {'name': 'No Material / Starved',       'code': 'MAT-STAR'},
            {'name': 'Waiting for Material Delivery','code': 'MAT-WAIT'},
        ],
    },
    {
        'name': 'Operator / Staffing Issues',
        'code': 'OPR',
        'subcategories': [
            {'name': 'Quick Operator Fix',          'code': 'OPR-QCLN'},
            {'name': 'Operator Error',              'code': 'OPR-ERR'},
            {'name': 'Incorrect Settings',          'code': 'OPR-SET'},
            {'name': 'Out-of-Spec Output',          'code': 'OPR-SPEC'},
            {'name': 'Startup Scrap',               'code': 'OPR-STR'},
            {'name': 'Warm-up Scrap',               'code': 'OPR-WUP'},
            {'name': 'Changeover Scrap',            'code': 'OPR-CO'},
            {'name': 'Operator Not Available',      'code': 'OPR-ABS'},
        ],
    },
    {
        'name': 'Project / Engineering / Trials',
        'code': 'PROJ',
        'subcategories': [
            {'name': 'Fixture / Rig Modification',  'code': 'PROJ-FIX'},
            {'name': 'Special Engineering Task',    'code': 'PROJ-ENG'},
            {'name': 'Planned Downtime for Project','code': 'PROJ-PLAN'},
            {'name': 'Testing / Validation Work',   'code': 'PROJ-TEST'},
            {'name': 'Waiting for Engineering Input','code': 'PROJ-WAIT'},
        ],
    },
    {
        'name': 'Parts / Support Delay',
        'code': 'SUPP',
        'subcategories': [
            {'name': 'Waiting for Spare Parts',     'code': 'SUPP-WAIT'},
            {'name': 'Maintenance Unavailable',     'code': 'SUPP-MAINT'},
            {'name': 'Tool / Component Ordered',    'code': 'SUPP-ORD'},
        ],
    },
    {
        'name': 'Other / Unclassified',
        'code': 'OTHER',
        'subcategories': [
            {'name': 'No Cause Found / Unknown',    'code': 'OTHER-UNK'},
            {'name': 'Miscommunication / Delay',    'code': 'OTHER-MISC'},
            {'name': 'Other',                        'code': 'OTHER-OTHER'},
        ],
    },
]



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
    try:
        payload        = json.loads(request.body)
        entry_id       = payload['entry_id']
        close_str      = payload['closeout']           # e.g. "2025-05-01 18:08"
        closeout_comment = payload['closeout_comment'] # NEW
        # parse into a naive datetime in server local time
        close_dt       = datetime.strptime(close_str, "%Y-%m-%d %H:%M")
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    try:
        e = MachineDowntimeEvent.objects.get(pk=entry_id, is_deleted=False)
    except MachineDowntimeEvent.DoesNotExist:
        return HttpResponseBadRequest("Entry not found")

    # compute epoch exactly like you do for start_epoch
    epoch_ts = int(close_dt.timestamp())

    # save the epoch and the comment
    e.closeout_epoch     = epoch_ts
    e.closeout_comment   = closeout_comment  # NEW
    e.save(update_fields=['closeout_epoch', 'closeout_comment'])

    # return the epoch back to the JS caller
    return JsonResponse({
        'status':          'ok',
        'closed_at_epoch': epoch_ts,
    })





def maintenance_entries(request: HttpRequest) -> JsonResponse:
    offset    = int(request.GET.get('offset', 0))
    # page_size = 100
    page_size = 300

    qs = MachineDowntimeEvent.objects.filter(
        is_deleted=False,
        closeout_epoch__isnull=True
    ).order_by('-start_epoch')

    total = qs.count()
    batch = list(qs[offset: offset + page_size])

    entries = [
        {
            'start_at'        : e.start_at.strftime('%Y-%m-%d %H:%M:%S'),
            'line'            : e.line,
            'machine'         : e.machine,
            'category'        : e.category,
            'subcategory'     : e.subcategory,
            'code'            : e.code,
            'category_code'   : e.code.split('-')[0],
            'subcategory_code': e.code,
            'comment'         : e.comment,
            'labour_type':     e.labour_type,
        }
        for e in batch
    ]
    has_more = (offset + page_size) < total

    return JsonResponse({'entries': entries, 'has_more': has_more})




def maintenance_form(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        # ——— pull form data ———
        entry_id    = request.POST.get('entry_id')      # None for “Add”
        line        = request.POST.get('line', '').strip()
        machine     = request.POST.get('machine', '').strip()
        cat_code    = request.POST.get('category', '').strip()
        sub_code    = request.POST.get('subcategory', '').strip()
        start_date  = request.POST.get('start_date', '') # "YYYY-MM-DD"
        start_time  = request.POST.get('start_time', '') # "HH:MM"
        description = request.POST.get('description', '').strip()

        # ——— parse out the list of labour codes ———
        raw_labour = request.POST.get('labour_types', '[]')
        try:
            labour_list = json.loads(raw_labour)
            if not isinstance(labour_list, list):
                labour_list = []
        except json.JSONDecodeError:
            labour_list = []

        # ——— lookup display names from your DOWNTIME_CODES ———
        cat_obj = next((c for c in DOWNTIME_CODES if c['code'] == cat_code), None)
        category_name = cat_obj['name'] if cat_obj else cat_code

        sub_obj = None
        if cat_obj:
            sub_obj = next((s for s in cat_obj['subcategories']
                            if s['code'] == sub_code), None)
        subcategory_name = sub_obj['name'] if sub_obj else sub_code

        # ——— build epoch timestamp ———
        try:
            dt = datetime.strptime(f"{start_date} {start_time}",
                                   "%Y-%m-%d %H:%M")
        except ValueError:
            return HttpResponseBadRequest("Invalid date/time")
        epoch_ts = int(dt.timestamp())

        # ——— create or update ———
        if entry_id:
            # update existing
            e = get_object_or_404(MachineDowntimeEvent,
                                  pk=entry_id,
                                  is_deleted=False)
            e.line           = line
            e.machine        = machine
            e.category       = category_name
            e.subcategory    = subcategory_name
            e.code           = sub_code
            e.start_epoch    = epoch_ts
            e.comment        = description
            e.labour_types   = labour_list
            e.save(update_fields=[
                'line', 'machine', 'category', 'subcategory',
                'code', 'start_epoch', 'comment', 'labour_types'
            ])
        else:
            # create new
            MachineDowntimeEvent.objects.create(
                line          = line,
                machine       = machine,
                category      = category_name,
                subcategory   = subcategory_name,
                code          = sub_code,
                start_epoch   = epoch_ts,
                comment       = description,
                labour_types  = labour_list,
            )

        # stay on same page (preserve ?offset=…)
        return redirect(request.get_full_path())

    # ——— GET: render form + list of open entries ———
    offset    = int(request.GET.get('offset', 0))
    page_size = 300

    qs = MachineDowntimeEvent.objects.filter(
        is_deleted        = False,
        closeout_epoch__isnull = True
    ).order_by('-start_epoch')

    total     = qs.count()
    page_objs = list(qs[offset: offset + page_size])
    has_more  = (offset + page_size) < total

    context = {
        'downtime_codes_json': mark_safe(json.dumps(DOWNTIME_CODES)),
        'lines_json':          mark_safe(json.dumps(prod_lines)),
        'entries':             page_objs,
        'offset':              offset,
        'page_size':           page_size,
        'has_more':            has_more,
        # you can also pass your labour-choices to the template if needed:
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

# --------------------------- rewritten view ---------------------------------- #
@login_required(login_url='login')
def list_all_downtime_entries(request):
    # ── 0)  ACCESS GATE ────────────────────────────────────────────────────────
    if not user_has_maintenance_access(request.user):
        return HttpResponseForbidden("You are not authorized to view this page. Ask the Maintenance Manager to add your profile " \
        "to its appropriate group(s) (electrician / tech / millwright)")

    # ── 1)  Base queryset of open downtimes ───────────────────────────────────
    base_qs = MachineDowntimeEvent.objects.filter(
        is_deleted=False,
        closeout_epoch__isnull=True,
    )

    # ── 2)  Subquery to pull each line’s priority (default 999) ───────────────
    priority_sq = (
        LinePriority.objects
        .filter(line=OuterRef("line"))
        .values("priority")[:1]
    )

    # ── 3)  Annotate + order by priority, then most‑recent start ──────────────
    qs = (
        base_qs
        .annotate(
            line_priority=Coalesce(
                Subquery(priority_sq, output_field=IntegerField()),
                Value(999),
                output_field=IntegerField(),
            )
        )
        .order_by("line_priority", "-start_epoch")
        .prefetch_related("participants")
    )

    # ── 4)  First PAGE_SIZE rows as a list (so we can mutate attrs) ───────────
    entries = list(qs[:PAGE_SIZE])

    # ── 5)  Mark whether *this* user already has an open participation ────────
    for e in entries:
        e.user_has_open = e.participants.filter(
            user=request.user, leave_epoch__isnull=True
        ).exists()

    # ── 6)  Figure out roles & manager flag for the template ──────────────────
    user_group_names = set(request.user.groups.values_list("name", flat=True))
    user_roles = [
        role for role, grp in ROLE_TO_GROUP.items() if grp in user_group_names
    ]  # e.g. ['electrician', 'tech']

    context = {
        "entries":         entries,
        "page_size":       PAGE_SIZE,
        "line_priorities": LinePriority.objects.all(),
        "is_manager":      "maintenance_managers" in user_group_names,
        "labour_choices":  MachineDowntimeEvent.LABOUR_CHOICES,
        "user_roles":      user_roles,
    }
    return render(request, "plant/maintenance_all_entries.html", context)

@login_required
def load_more_downtime_entries(request):
    """
    AJAX endpoint: GET /plant/downtime/load-more/?offset=N
    → returns JSON {
         "entries": [ {id, start_at, closeout_at, …}, … ],
         "has_more": bool
       }
    """
    # 1) parse offset
    try:
        offset = int(request.GET.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0

    # 2) grab open downtimes, newest first, prefetch participants & users
    qs = (
        MachineDowntimeEvent.objects
        .filter(is_deleted=False, closeout_epoch__isnull=True)
        .order_by('-start_epoch')
        .prefetch_related('participants__user')
    )

    total_count = qs.count()
    batch = qs[offset:offset + PAGE_SIZE]

    # 3) build JSON payload
    entries = []
    for e in batch:
        # find all users who have joined but not yet left
        open_parts = e.participants.filter(leave_epoch__isnull=True)
        assigned_usernames = [p.user.username for p in open_parts]

        entries.append({
            'id':            e.id,
            'start_at':      e.start_at.strftime('%Y-%m-%d %H:%M'),
            'closeout_at':   (
                                e.closeout_epoch and
                                datetime.fromtimestamp(e.closeout_epoch)
                                          .strftime('%Y-%m-%d %H:%M')
                             ) or None,
            'line':          e.line,
            'machine':       e.machine,
            'category':      e.category,
            'subcategory':   e.subcategory,
            'labour_types':  e.labour_types,
            'assigned_to':   assigned_usernames,
            'comment':       e.comment,
        })

    # 4) tell client if there’s more to load
    has_more = total_count > offset + PAGE_SIZE

    return JsonResponse({
        'entries':  entries,
        'has_more': has_more,
    })


@require_POST
@login_required
def join_downtime_event(request):
    """
    Called when a user clicks “Join”.  Creates a new participation row.
    """
    try:
        payload = json.loads(request.body)
        event_id = payload['event_id']
        comment  = payload.get('join_comment', '').strip()
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    event = MachineDowntimeEvent.objects.filter(
        pk=event_id,
        is_deleted=False
    ).first()
    if not event:
        return HttpResponseBadRequest("Event not found")

    now = int(time.time())
    participation = DowntimeParticipation.objects.create(
        event        = event,
        user         = request.user,
        join_epoch   = now,
        join_comment = comment
    )

    return JsonResponse({
        'status':           'ok',
        'participation_id': participation.id,
        'join_epoch':       now,
    })


@require_POST
@login_required
def leave_downtime_event(request):
    try:
        payload   = json.loads(request.body)
        event_id  = payload['event_id']
        comment   = payload.get('leave_comment', '').strip()
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    part = (DowntimeParticipation.objects
            .filter(event__pk=event_id,
                    user=request.user,
                    leave_epoch__isnull=True)
            .order_by('-join_epoch')
            .first())

    if not part:
        return HttpResponseBadRequest("No active participation to leave")

    now   = int(time.time())
    delta = now - part.join_epoch          # seconds

    import math
    part.leave_epoch   = now
    part.leave_comment = comment
    part.total_minutes = math.ceil(delta / 60)   # ⬅ round‑up
    part.save(update_fields=['leave_epoch', 'leave_comment', 'total_minutes'])

    return JsonResponse({
        'status'       : 'ok',
        'leave_epoch'  : now,
        'total_minutes': part.total_minutes,
    })




@require_POST
def closeout_assigned_downtime_entry(request):
    """
    Close out only entries assigned to the current user.
    """
    try:
        payload = json.loads(request.body)
        entry_id       = payload['entry_id']
        close_str      = payload['closeout']           # "YYYY-MM-DD HH:MM"
        close_comment  = payload['closeout_comment']
        close_dt       = datetime.strptime(close_str, "%Y-%m-%d %H:%M")
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    try:
        e = MachineDowntimeEvent.objects.get(
            pk=entry_id,
            is_deleted=False
        )
    except MachineDowntimeEvent.DoesNotExist:
        return HttpResponseBadRequest("Entry not found")

    # Only the assignee may close it out
    if e.assigned_to != request.user.username:
        return HttpResponseBadRequest("Not your assignment")

    # compute & save
    epoch_ts = int(close_dt.timestamp())
    e.closeout_epoch   = epoch_ts
    e.closeout_comment = close_comment
    e.save(update_fields=['closeout_epoch', 'closeout_comment'])

    return JsonResponse({'status':'ok', 'closed_at_epoch': epoch_ts})



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