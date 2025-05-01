import json
from django.shortcuts import render, redirect
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse
from datetime import datetime
from ..models.maintenance_models import MachineDowntimeEvent
from django.http import JsonResponse
from django.utils import timezone
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST



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

def maintenance_entries(request: HttpRequest) -> JsonResponse:
    """
    AJAX endpoint: returns the next page of downtime entries in JSON.
    Querystring:
      ?offset=N   — zero-based index to start at
    """
    offset    = int(request.GET.get('offset', 0))
    page_size = 100

    # ← only non-deleted
    qs      = MachineDowntimeEvent.objects.filter(is_deleted=False).order_by('-start_epoch')
    total   = qs.count()
    batch   = list(qs[offset : offset + page_size])

    entries = [
        {
            'start_at':    e.start_at.strftime('%Y-%m-%d %H:%M:%S'),
            'line':        e.line,
            'machine':     e.machine,
            'category':    e.category,
            'subcategory': e.subcategory,
            'code':        e.code,
            'comment':     e.comment,
        }
        for e in batch
    ]
    has_more = (offset + page_size) < total

    return JsonResponse({'entries': entries, 'has_more': has_more})


def maintenance_form(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        # 1) grab the raw codes from the form
        line        = request.POST['line']
        machine     = request.POST['machine']
        cat_code    = request.POST['category']
        sub_code    = request.POST['subcategory']
        start_date  = request.POST['start_date']   # "YYYY-MM-DD"
        start_time  = request.POST['start_time']   # "HH:MM"
        description = request.POST['description']

        # 2) look up the display names
        cat_obj = next((c for c in DOWNTIME_CODES if c['code'] == cat_code), None)
        category_name    = cat_obj['name'] if cat_obj else cat_code

        sub_obj = None
        if cat_obj:
            sub_obj = next((s for s in cat_obj['subcategories'] if s['code'] == sub_code), None)
        subcategory_name = sub_obj['name'] if sub_obj else sub_code

        # 3) parse epoch
        dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
        epoch_ts = int(dt.timestamp())

        # 4) save
        MachineDowntimeEvent.objects.create(
            line        = line,
            machine     = machine,
            category    = category_name,
            subcategory = subcategory_name,
            code        = sub_code,
            start_epoch = epoch_ts,
            comment     = description,
            # is_deleted and deleted_at default to False / None
        )

        # preserve offset so page doesn’t jump back
        return redirect(request.get_full_path())

    # ─── GET ────────────────────────────────────────────────────────────────
    offset    = int(request.GET.get('offset', 0))
    page_size = 100

    # ← only non-deleted
    qs        = MachineDowntimeEvent.objects.filter(is_deleted=False).order_by('-start_epoch')
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