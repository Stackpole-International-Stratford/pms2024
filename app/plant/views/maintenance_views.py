import json
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse

# import your lines structure
from prod_query.views import lines as prod_lines


def maintenance_form(request: HttpRequest) -> HttpResponse:
    """
    GET:  render the form shell, embedding downtime_codes + prod_lines as JSON
    POST: echo back submitted values
    """
    if request.method == 'POST':
        # grab the submitted fields
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

    # GET: build your hierarchies
    downtime_codes = [
        {
            'name': 'Equipment Failure',
            'code': 'EQP',
            'subcategories': [
                {'name': 'Tooling Failure',       'code': 'EQP-TOOL'},
                {'name': 'Breakdown',             'code': 'EQP-BRK'},
                {'name': 'Unplanned Maintenance', 'code': 'EQP-MNT'},
                {'name': 'Starved (No Material)', 'code': 'EQP-STAR'},
                {'name': 'Blocked (Downstream)',  'code': 'EQP-BLKD'},
            ],
        },
        {
            'name': 'Setup & Adjustments',
            'code': 'SET',
            'subcategories': [
                {'name': 'Changeover',           'code': 'SET-CHG'},
                {'name': 'Major Adjustment',     'code': 'SET-ADJ'},
                {'name': 'Tooling Adjustment',   'code': 'SET-TOOL'},
                {'name': 'Cleaning / Warm-up',   'code': 'SET-CLEAN'},
                {'name': 'Planned Maintenance',  'code': 'SET-MNT'},
                {'name': 'Quality Inspection',   'code': 'SET-INSP'},
            ],
        },
        {
            'name': 'Idling & Minor Stops',
            'code': 'IDL',
            'subcategories': [
                {'name': 'Misfeed / Material Jam','code': 'IDL-JAM'},
                {'name': 'Obstructed Flow',      'code': 'IDL-FLOW'},
                {'name': 'Sensor Blocked / Misalign','code': 'IDL-SENS'},
                {'name': 'Quick Clean / Operator Fix','code': 'IDL-QCLN'},
            ],
        },
        {
            'name': 'Reduced Speed',
            'code': 'RSP',
            'subcategories': [
                {'name': 'Tool Wear',            'code': 'RSP-TWR'},
                {'name': 'Poor Lubrication',     'code': 'RSP-LUB'},
                {'name': 'Material Quality Issue','code': 'RSP-MAT'},
                {'name': 'Environmental Issue',  'code': 'RSP-ENV'},
                {'name': 'Startup/Shut-down Slow','code': 'RSP-SS'},
            ],
        },
        {
            'name': 'Process Defects',
            'code': 'DEF',
            'subcategories': [
                {'name': 'Incorrect Settings',   'code': 'DEF-SET'},
                {'name': 'Operator Handling Error','code': 'DEF-OPR'},
                {'name': 'Material Defect',      'code': 'DEF-MAT'},
                {'name': 'Dimensional Out-of-Spec','code': 'DEF-SPEC'},
            ],
        },
        {
            'name': 'Reduced Yield (Startup)',
            'code': 'YLD',
            'subcategories': [
                {'name': 'Startup Scrap',        'code': 'YLD-STR'},
                {'name': 'Warm-up Scrap',        'code': 'YLD-WUP'},
                {'name': 'Changeover Scrap',     'code': 'YLD-CO'},
            ],
        },
    ]

    # safely embed as JSON strings
    context = {
        'message': 'Hello, world! This is the maintenance form.',
        'downtime_codes_json': mark_safe(json.dumps(downtime_codes)),
        'lines_json':           mark_safe(json.dumps(prod_lines)),
    }
    return render(request, 'plant/maintenance_form.html', context)
