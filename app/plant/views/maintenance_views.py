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
from django.contrib import messages
from django.contrib.auth.models import Group
from django.utils.crypto import get_random_string
from django.http        import HttpResponseForbidden
import math
from django.utils.timezone import is_naive, make_aware, get_default_timezone, utc, localtime
from django.db.models import Exists, OuterRef





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



# --------------------------- rewritten view ---------------------------------- #

@login_required(login_url='login')
def list_all_downtime_entries(request):
    # ── access control
    if not user_has_maintenance_access(request.user):
        return HttpResponseForbidden(
            "You are not authorized to view this page. "
            "Ask your Maintenance Manager to add you to the appropriate group."
        )

    # ── build base queryset with line priority
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

    # ── annotate whether anybody is still working
    qs = annotate_being_worked_on(base_qs)

    entries = list(qs[:PAGE_SIZE])
    today = timezone.localdate()
    default_tz = get_default_timezone()

    for e in entries:
        # make e.start_at timezone-aware if necessary
        dt = e.start_at
        if is_naive(dt):
            dt = make_aware(dt, default_tz)
        local_dt = timezone.localtime(dt)

        # format display
        e.start_display = (
            local_dt.strftime('%H:%M')
            if local_dt.date() == today
            else local_dt.strftime('%m/%d')
        )

        # flag whether current user already joined (for your own logic)
        e.user_has_open = e.participants.filter(
            user=request.user, leave_epoch__isnull=True
        ).exists()

    user_groups = set(request.user.groups.values_list("name", flat=True))
    roles = [r for r, g in ROLE_TO_GROUP.items() if g in user_groups]

    return render(request, "plant/maintenance_all_entries.html", {
        "entries":         entries,
        "page_size":       PAGE_SIZE,
        "line_priorities": LinePriority.objects.all(),
        "is_manager":      "maintenance_managers" in user_groups,
        "labour_choices":  MachineDowntimeEvent.LABOUR_CHOICES,
        "user_roles":      roles,
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
















@require_POST
@login_required
def edit_downtime_entry(request):
    try:
        payload       = json.loads(request.body)
        entry_id      = payload['entry_id']
        sd, st        = payload['start_date'], payload['start_time']
        line          = payload['line']
        machine       = payload['machine']
        category      = payload['category']
        subcategory   = payload['subcategory']
        comment       = payload['comment']
    except (KeyError, ValueError):
        return HttpResponseBadRequest("Invalid payload")

    # parse and compute epoch
    try:
        dt = datetime.strptime(f"{sd} {st}", "%Y-%m-%d %H:%M")
    except ValueError:
        return HttpResponseBadRequest("Bad date/time")

    event = get_object_or_404(MachineDowntimeEvent, pk=entry_id, is_deleted=False)
    event.start_epoch = int(dt.timestamp())
    event.line        = line
    event.machine     = machine
    event.category    = category
    event.subcategory = subcategory
    event.comment     = comment
    event.save(update_fields=[
      'start_epoch','line','machine','category','subcategory','comment'
    ])

    # compute the new display string
    local_dt = timezone.localtime(timezone.make_aware(dt, timezone.get_default_timezone()))
    today    = timezone.localdate()
    start_display = (
      local_dt.strftime('%H:%M')
      if local_dt.date() == today
      else local_dt.strftime('%m/%d')
    )

    return JsonResponse({
      'id':             event.id,
      'start_display':  start_display,
      'line':           event.line,
      'machine':        event.machine,
      'category':       event.category,
      'subcategory':    event.subcategory,
      'comment':        event.comment,
    })