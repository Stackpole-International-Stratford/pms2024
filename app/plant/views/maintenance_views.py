# /home/tcareless/pms2024/app/plant/views/maintenance_views.py

import json
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.http import HttpRequest, HttpResponse

def maintenance_form(request: HttpRequest) -> HttpResponse:
    """
    Renders the maintenance form page, embedding the downtime-codes
    structure as JSON for the frontend to consume.
    """
    downtime_codes = [
        {
            'name': 'Equipment Failure',
            'code': 'EQP',
            'subcategories': [
                {'name': 'Tooling Failure',      'code': 'EQP-TOOL'},
                {'name': 'Breakdown',            'code': 'EQP-BRK'},
                {'name': 'Unplanned Maintenance','code': 'EQP-MNT'},
                {'name': 'Starved (No Material)', 'code': 'EQP-STAR'},
                {'name': 'Blocked (Downstream)', 'code': 'EQP-BLKD'},
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

    # Convert to a JSON string and mark safe so Django won’t escape it
    downtime_json = mark_safe(json.dumps(downtime_codes))

    context = {
        'message': 'Hello, world! This is the maintenance form.',
        'downtime_codes_json': downtime_json,
    }
    return render(request, 'plant/maintenance_form.html', context)
