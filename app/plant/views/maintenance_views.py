import json
from django.shortcuts import render, redirect
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse
from datetime import datetime


# import your lines structure
from prod_query.views import lines as prod_lines

# ——— module-wide downtime codes ———
DOWNTIME_CODES = [
    {
        'name': 'Mechanical / Equipment Failure',
        'code': 'MECH',
        'subcategories': [
            {'name': 'Tooling Failure',         'code': 'MECH-TOOL'},
            {'name': 'Breakdown',               'code': 'MECH-BRK'},
            {'name': 'Unplanned Maintenance',   'code': 'MECH-MNT'},
            {'name': 'Starved (No Material)',   'code': 'MECH-STAR'},
            {'name': 'Blocked (Downstream)',    'code': 'MECH-BLKD'},
            {'name': 'Tool Wear',               'code': 'MECH-TWR'},
            {'name': 'Poor Lubrication',         'code': 'MECH-LUB'},
            {'name': 'Environmental Issue',     'code': 'MECH-ENV'},
        ],
    },
        {
        'name': 'Other',
        'code': 'OTHER',
        'subcategories': [
            {'name': 'Other',         'code': 'OTHER-OTHER'},

        ],
    },
    {
        'name': 'Electrical Failure',
        'code': 'ELEC',
        'subcategories': [
            {'name': 'Sensor Blocked / Misaligned', 'code': 'ELEC-SENS'},
            {'name': 'Obstructed Flow (Electrical)', 'code': 'ELEC-FLOW'},
            {'name': 'Startup/Shut-down Slow (Electrical)', 'code': 'ELEC-SS'},
            {'name': 'Power Loss / Electrical Fault', 'code': 'ELEC-POW'},
        ],
    },
    {
        'name': 'Setup and Adjustments',
        'code': 'SETUP',
        'subcategories': [
            {'name': 'Changeover',              'code': 'SETUP-CHG'},
            {'name': 'Major Adjustment',        'code': 'SETUP-ADJ'},
            {'name': 'Tooling Adjustment',      'code': 'SETUP-TOOL'},
            {'name': 'Cleaning / Warm-up',      'code': 'SETUP-CLEAN'},
            {'name': 'Planned Maintenance',     'code': 'SETUP-MNT'},
            {'name': 'Quality Inspection',      'code': 'SETUP-INSP'},
        ],
    },
    {
        'name': 'Material or Supply Issues',
        'code': 'MAT',
        'subcategories': [
            {'name': 'Misfeed / Material Jam',  'code': 'MAT-JAM'},
            {'name': 'Material Quality Issue',  'code': 'MAT-QUAL'},
            {'name': 'Material Defect',          'code': 'MAT-DEF'},
            {'name': 'Starved (No Material)',   'code': 'MAT-STAR'},  # Also fits here
        ],
    },
    {
        'name': 'Operator / Staffing Issues',
        'code': 'OPR',
        'subcategories': [
            {'name': 'Quick Clean / Operator Fix', 'code': 'OPR-QCLN'},
            {'name': 'Operator Handling Error',    'code': 'OPR-ERR'},
            {'name': 'Incorrect Settings',         'code': 'OPR-SET'},
            {'name': 'Dimensional Out-of-Spec',     'code': 'OPR-SPEC'},
            {'name': 'Startup Scrap',               'code': 'OPR-STR'},
            {'name': 'Warm-up Scrap',                'code': 'OPR-WUP'},
            {'name': 'Changeover Scrap',             'code': 'OPR-CO'},
        ],
    },
]



def maintenance_form(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        # grab your fields
        line        = request.POST.get('line')
        machine     = request.POST.get('machine')
        category    = request.POST.get('category')
        subcategory = request.POST.get('subcategory')
        start_date  = request.POST.get('start_date')   # e.g. "2025-05-01"
        start_time  = request.POST.get('start_time')   # e.g. "14:30"
        description = request.POST.get('description')

        # combine date + time, parse to datetime
        dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
        epoch_ts = int(dt.timestamp())

        # log it however you like:
        # -- simple print:
        print(
            f"Downtime logged → "
            f"line={line}, machine={machine}, "
            f"category={category}, subcategory={subcategory}, "
            f"start_epoch={epoch_ts}, comment={description}"
        )


        # then just redirect back (or send a minimal response)
        return redirect(request.path)

    # GET: render the form as before
    context = {
        'downtime_codes_json': mark_safe(json.dumps(DOWNTIME_CODES)),
        'lines_json':          mark_safe(json.dumps(prod_lines)),
    }
    return render(request, 'plant/maintenance_form.html', context)