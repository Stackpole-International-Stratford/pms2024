import json
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse, HttpResponseRedirect
from datetime import datetime
from ..models.maintenance_models import MachineDowntimeEvent, LinePriority
from django.http import JsonResponse
from django.utils import timezone
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.db import transaction





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
        entry_id    = request.POST.get('entry_id')     # this will be None for “Add” form
        line        = request.POST['line']
        machine     = request.POST['machine']
        cat_code    = request.POST['category']
        sub_code    = request.POST['subcategory']
        start_date  = request.POST['start_date']       # "YYYY-MM-DD"
        start_time  = request.POST['start_time']       # "HH:MM"
        description = request.POST['description']
        labour_type = request.POST.get('labour_type', 'OPERATOR')

        # look up display names
        cat_obj = next((c for c in DOWNTIME_CODES if c['code'] == cat_code), None)
        category_name = cat_obj['name'] if cat_obj else cat_code

        sub_obj = None
        if cat_obj:
            sub_obj = next((s for s in cat_obj['subcategories'] if s['code'] == sub_code), None)
        subcategory_name = sub_obj['name'] if sub_obj else sub_code

        # parse into epoch
        dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
        epoch_ts = int(dt.timestamp())

        if entry_id:
            # ——— update existing record ———
            try:
                e = MachineDowntimeEvent.objects.get(pk=entry_id, is_deleted=False)
            except MachineDowntimeEvent.DoesNotExist:
                return HttpResponseBadRequest("Entry not found")
            e.line        = line
            e.machine     = machine
            e.category    = category_name
            e.subcategory = subcategory_name
            e.code        = sub_code
            e.start_epoch = epoch_ts
            e.comment     = description
            e.labour_type = labour_type
            e.save(update_fields=[
                'line', 'machine', 'category', 'subcategory',
                'code', 'start_epoch', 'comment', 'labour_type'
            ])
        else:
            # ——— create new record ———
            MachineDowntimeEvent.objects.create(
                line        = line,
                machine     = machine,
                category    = category_name,
                subcategory = subcategory_name,
                code        = sub_code,
                start_epoch = epoch_ts,
                comment     = description,
                labour_type = labour_type,
            )

        # preserve any ?offset=… in the URL so the user stays on the same page
        return redirect(request.get_full_path())

    # ─── GET ───────────────────────────────────────────────────────────────
    offset    = int(request.GET.get('offset', 0))
    page_size = 300

    qs = MachineDowntimeEvent.objects.filter(
        is_deleted=False,
        closeout_epoch__isnull=True
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
    }
    return render(request, 'plant/maintenance_form.html', context)













# ================================================================
# ================================================================
# ======================= Labour Dashboard =======================
# ================================================================
# ================================================================

# how many at a time
PAGE_SIZE = 500

@login_required(login_url='login')
def list_all_downtime_entries(request):
    # your existing downtime query
    qs = MachineDowntimeEvent.objects.filter(
        is_deleted=False,
        closeout_epoch__isnull=True,
    ).order_by('-start_epoch')

    entries = qs[:PAGE_SIZE]

    # grab all lines in priority order
    line_priorities = LinePriority.objects.all()

    # check group membership
    is_manager = request.user.groups.filter(
        name='maintenance_managers'
    ).exists()

    return render(request, 'plant/maintenance_all_entries.html', {
        'entries':         entries,
        'page_size':       PAGE_SIZE,
        'line_priorities': line_priorities,
        'is_manager':      is_manager,    # ← new
    })


def load_more_downtime_entries(request):
    """
    AJAX endpoint: GET /plant/downtime/load-more/?offset=N
    → returns JSON {
         "entries": [ {id, start_at, closeout_at, …}, … ],
         "has_more": bool
       }
    """
    try:
        offset = int(request.GET.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0

    qs = MachineDowntimeEvent.objects.filter(
        is_deleted=False,
        closeout_epoch__isnull=True,
    ).order_by('-start_epoch')

    batch = qs[offset:offset + PAGE_SIZE]
    entries = []
    for e in batch:
        entries.append({
            'id':            e.id,
            'start_at':      e.start_at.strftime('%Y-%m-%d %H:%M'),
            # use Python None, not `null`
            'closeout_at':   e.closeout_epoch.strftime('%Y-%m-%d %H:%M')
                              if e.closeout_epoch else None,
            'line':          e.line,
            'machine':       e.machine,
            'category':      e.category,
            'subcategory':   e.subcategory,
            'labour_type':   e.labour_type,
            'assigned_to':   e.assigned_to,
            'comment':       e.comment,
        })

    has_more = qs.count() > offset + PAGE_SIZE

    return JsonResponse({
        'entries':  entries,
        'has_more': has_more,
    })



@require_POST
def assign_downtime_entry(request):
    try:
        payload  = json.loads(request.body)
        entry_id = payload['entry_id']
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    try:
        e = MachineDowntimeEvent.objects.get(pk=entry_id, is_deleted=False)
    except MachineDowntimeEvent.DoesNotExist:
        return HttpResponseBadRequest("Entry not found")

    e.assigned_to = request.user.username
    e.save(update_fields=['assigned_to'])

    return JsonResponse({
        'status':      'ok',
        'assigned_to': request.user.username,
    })


@require_POST
def unassign_downtime_entry(request):
    try:
        payload  = json.loads(request.body)
        entry_id = payload['entry_id']
    except (ValueError, KeyError):
        return HttpResponseBadRequest("Invalid payload")

    try:
        e = MachineDowntimeEvent.objects.get(pk=entry_id, is_deleted=False)
    except MachineDowntimeEvent.DoesNotExist:
        return HttpResponseBadRequest("Entry not found")

    # only let the current assignee clear it
    if e.assigned_to != request.user.username:
        return HttpResponseBadRequest("Not your assignment")

    e.assigned_to = ''
    e.save(update_fields=['assigned_to'])

    return JsonResponse({'status': 'ok'})



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