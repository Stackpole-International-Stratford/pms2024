import json
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse

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
    """
    GET:  render the form shell, embedding downtime_codes + prod_lines as JSON
    POST: echo back submitted values
    """
    if request.method == 'POST':
        machine     = request.POST.get('machine')
        category    = request.POST.get('category')
        subcategory = request.POST.get('subcategory')
        description = request.POST.get('description')

        # for now, just print what was submitted
        return HttpResponse(f"""
            <h1>Submission Received</h1>
            <p><strong>Machine:</strong> {machine}</p>
            <p><strong>Category:</strong> {category}</p>
            <p><strong>Sub-category:</strong> {subcategory}</p>
            <p><strong>Description:</strong> {description}</p>
            <p><a href="">Log another downtime</a></p>
        """)

    # GET: embed module-level DOWNTIME_CODES
    context = {
        'message': 'Hello, world! This is the maintenance form.',
        'downtime_codes_json': mark_safe(json.dumps(DOWNTIME_CODES)),
        'lines_json':           mark_safe(json.dumps(prod_lines)),
    }
    return render(request, 'plant/maintenance_form.html', context)
