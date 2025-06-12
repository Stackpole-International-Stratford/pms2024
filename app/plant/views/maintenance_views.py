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
from prod_query.views import lines as prod_lines_initial
from django.views.decorators.csrf import csrf_exempt  # or use @ensure_csrf_cookie / csrf_protect
from django.template.loader import render_to_string
from django.db.models import Exists, OuterRef, Case, When, Value, BooleanField
import copy
import csv
from django.utils.encoding import smart_str
from collections import OrderedDict


lines_untracked = [
     {
        "line": "10R80",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "30",
                "machines": [
                    {"number": "1826", "target": 27496,},
                    {"number": "1555", "target": 27496,},
                    {"number": "1546", "target": 27496,},
                ],
            },
            {
                "op": "40",
                "machines": [
                    {"number": "1547", "target": 27496,},
                ],
            },
            {
                "op": "50",
                "machines": [
                    {"number": "1548", "target": 27496,},
                ],
            },
            {
                "op": "60",
                "machines": [
                    {"number": "1549", "target": 27496,},
                ],
            },
            {
                "op": "70",
                "machines": [
                    {"number": "594", "target": 27496,},
                ],
            },
            {
                "op": "80",
                "machines": [
                    {"number": "1551", "target": 27496,},
                ],
            },
            {
                "op": "90",
                "machines": [
                    {"number": "1552", "target": 27496,},
                ],
            },
            {
                "op": "100",
                "machines": [
                    {"number": "751", "target": 27496,},
                ],
            },
                        {
                "op": "110",
                "machines": [
                    {"number": "1554", "target": 27496,},
                ],
            },
                        {
                "op": "120",
                "machines": [
                    {"number": "1557", "target": 27496,},
                ],
            },
            {
                "op": "lasermark",
                "machines": [
                    {"number": "1505", "target": 27496,},
                    {"number": "1534", "target": 27496,},
                ],
            },
        ],
    },
    {
        "line": "10R60",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "30",
                "machines": [
                    {"number": "1826", "target": 27496,},
                ],
            },
            {
                "op": "lasermark",
                "machines": [
                    {"number": "1811", "target": 27496,},
                ],
            },
        ],
    },
     {
        "line": "Tyler Test",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "10",
                "machines": [
                    {"number": "test", "target": 27496,},

                ],
            },
        ],
    },
    {
        "line": "AB1V Reaction",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "10",
                "machines": [
                    {"number": "658", "target": 27496,},
                    {"number": "661", "target": 27496,},

                ],
            },
            {
                "op": "50",
                "machines": [
                    {"number": "660", "target": 27496,},
                ],
            },
                        {
                "op": "80",
                "machines": [
                    {"number": "1719", "target": 27496,},
                ],
            },
            {
                "op": "120",
                "machines": [
                    {"number": "1724", "target": 27496,},
                    {"number": "1725", "target": 27496,},
                    {"number": "1750", "target": 27496,},
                ],
            },
            {
                "op": "Final",
                "machines": [
                    {"number": "1730", "target": 27496,},
                ],
            },
        ],
    },
        {
        "line": "AB1V Input",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "20",
                "machines": [
                    {"number": "662", "target": 27496,},
                ],
            },
            {
                "op": "60",
                "machines": [
                    {"number": "1742", "target": 27496,},
                ],
            },
            {
                "op": "70",
                "machines": [
                    {"number": "604", "target": 27496,},
                ],
            },
            {
                "op": "Final",
                "machines": [
                    {"number": "1730", "target": 27496,},
                ],
            },
        ],
    },
        {
        "line": "AB1V Overdrive",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "35",
                "machines": [
                    {"number": "668", "target": 27496,},
                    {"number": "580", "target": 27496,},

                ],
            },
            {
                "op": "50",
                "machines": [
                    {"number": "580", "target": 27496,},
                ],
            },
            {
                "op": "100",
                "machines": [
                    {"number": "1724", "target": 27496,},
                    {"number": "1725", "target": 27496,},
                    {"number": "1750", "target": 27496,},
                ],
            },
            {
                "op": "Final",
                "machines": [
                    {"number": "1730", "target": 27496,},
                ],
            },
        ],
    },
     {
        "line": "Presses",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "compact",
                "machines": [
                    {"number": "271", "target": 27496,},
                ],
            },
              {
                "op": "pellet / wafers",
                "machines": [
                    {"number": "227", "target": 27496,},
                    {"number": "238", "target": 27496,},
                    {"number": "218", "target": 27496,},
                    {"number": "215", "target": 27496,},
                    {"number": "274", "target": 27496,},
                    {"number": "244", "target": 27496,},
                    {"number": "216", "target": 27496,},
                    {"number": "275", "target": 27496,},
                    {"number": "204", "target": 27496,},
                    {"number": "265", "target": 27496,},
                    {"number": "205", "target": 27496,},
                    {"number": "261", "target": 27496,},
                    {"number": "263", "target": 27496,},
                ],
            },
        ],
    },
    {
        "line": "10R140",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "autogauge",
                "machines": [
                    {"number": "1760", "target": 27496,},
                ],
            },
            {
                "op": "op10",
                "machines": [
                    {"number": "654", "target": 27496,},
                    {"number": "686", "target": 27496,},
                    {"number": "655", "target": 27496,},
                ],
            },
             {
                "op": "op20",
                "machines": [
                    {"number": "611", "target": 27496,},
                ],
            },
        ],
    },
    {
        "line": "10R140 Front",
        "scrap_line": "NA",
        "operations": [
                        {
                "op": "op10",
                "machines": [
                    {"number": "686", "target": 27496,},
                    {"number": "655", "target": 27496,},
                    {"number": "654", "target": 27496,},
                ],
            },
            {
                "op": "op20",
                "machines": [
                    {"number": "611", "target": 27496,},
                ],
            },
        ],
    },
     {
        "line": "GF6",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "10",
                "machines": [
                    {"number": "583", "target": 27496,},
                    {"number": "582", "target": 27496,},
                    {"number": "627", "target": 27496,},
                    {"number": "574", "target": 27496,},
                ],
            },
             {
                "op": "20",
                "machines": [
                    {"number": "731", "target": 27496,},
                    {"number": "628", "target": 27496,},
                    {"number": "635", "target": 27496,},
                    {"number": "564", "target": 27496,},
                    {"number": "620", "target": 27496,},
                ],
            },
            {
                "op": "30",
                "machines": [
                    {"number": "692", "target": 27496,},
                    {"number": "749", "target": 27496,},
                    {"number": "750", "target": 27496,},
                ],
            },
            {
                "op": "40",
                "machines": [
                    {"number": "672", "target": 27496,},
                    {"number": "673", "target": 27496,},
                    {"number": "676", "target": 27496,},
                    {"number": "674", "target": 27496,},
                ],
            },
            {
                "op": "50",
                "machines": [
                    {"number": "667", "target": 27496,},
                    {"number": "745", "target": 27496,},
                ],
            },
            {
                "op": "slurry",
                "machines": [
                    {"number": "596", "target": 27496,},
                    {"number": "577", "target": 27496,},
                ],
            },
            {
                "op": "hpwash",
                "machines": [
                    {"number": "782", "target": 27496,},
                    {"number": "783", "target": 27496,},
                ],
            },
                        {
                "op": "Wash/Dryer",
                "machines": [
                    {"number": "696", "target": 27496,},
                    {"number": "781", "target": 27496,},
                ],
            },
                                    {
                "op": "Media Detection",
                "machines": [
                    {"number": "883", "target": 27496,},
                    {"number": "882", "target": 27496,},
                ],
            },
        ],
    },
    {
  "line": "GFX",
  "scrap_line": "NA",
  "operations": [
    {
      "op": "10",
      "machines": [
        { "number": "771",  "target": 27496, },
        { "number": "773",  "target": 27496, }
      ]
    },
    {
      "op": "10/20",
      "machines": [
        { "number": "1601", "target": 27496, },
        { "number": "1602", "target": 27496, },
        { "number": "1604", "target": 27496, },
        { "number": "1603", "target": 27496, }
      ]
    },
    {
      "op": "20",
      "machines": [
        { "number": "772",  "target": 27496, },
        { "number": "774",  "target": 27496, }
      ]
    },
    {
      "op": "30",
      "machines": [
        { "number": "1606", "target": 27496, },
        { "number": "1607", "target": 27496, },
        { "number": "1608", "target": 27496, },
        { "number": "1605", "target": 27496, }
      ]
    },
    {
      "op": "40",
      "machines": [
        { "number": "888",  "target": 27496, },
        { "number": "1611", "target": 27496, }
      ]
    },
    {
      "op": "50",
      "machines": [
        { "number": "887",  "target": 27496, },
        { "number": "1610", "target": 27496, },
        { "number": "639",  "target": 27496, },
        { "number": "780",  "target": 27496, }
      ]
    },
    {
      "op": "60",
      "machines": [
        { "number": "1612", "target": 27496, },
        { "number": "1620", "target": 27496, }
      ]
    },
    {
      "op": "70",
      "machines": [
        { "number": "1609", "target": 27496, }
      ]
    },
    {
      "op": "80",
      "machines": [
        { "number": "1617", "target": 27496, }
      ]
    }
  ]
},
     {
        "line": "9HP/ZF",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "Machining",
                "machines": [
                    {"number": "786", "target": 27496,},
                    {"number": "787", "target": 27496,},
                    {"number": "789", "target": 27496,},
                    {"number": "791", "target": 27496,},
                    {"number": "792", "target": 27496,},
                    {"number": "793", "target": 27496,},
                    {"number": "794", "target": 27496,},
                ],
            },
             {
                "op": "Balancers",
                "machines": [
                    {"number": "798", "target": 27496,},
                    {"number": "746", "target": 27496,},
                    {"number": "953", "target": 27496,},
                ],
            },
             {
                "op": "Slurries",
                "machines": [
                    {"number": "630", "target": 27496,},
                    {"number": "634", "target": 27496,},
                ],
            },
            {
                "op": "Washer/Dryer",
                "machines": [
                    {"number": "612", "target": 27496,},
                ],
            },
                        {
                "op": "Autogauge",
                "machines": [
                    {"number": "797", "target": 27496,},
                ],
            },
        ],
    },
    {
        "line": "Furnaces",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "furnace",
                "machines": [
                    {"number": "1516", "target": 27496,},
                    {"number": "859", "target": 27496,},
                    {"number": "341", "target": 27496,},
                    {"number": "697", "target": 27496,},
                    {"number": "678", "target": 27496,},
                    {"number": "743", "target": 27496,},
                    {"number": "342", "target": 27496,},
                    {"number": "343", "target": 27496,},
                    {"number": "346", "target": 27496,},
                    {"number": "441", "target": 27496,},
                    {"number": "331", "target": 27496,},
                    {"number": "314", "target": 27496,},


                ],
            },

            {
                "op": "Compact",
                "machines": [
                    {"number": "262", "target": 27496,},
                    {"number": "263", "target": 27496,},
                ],
            },
             {
                "op": "Assembler",
                "machines": [
                    {"number": "859", "target": 27496,},
                   



                ],
            },
             {
                "op": "Unload",
                "machines": [
                    {"number": "954", "target": 27496,},
                    {"number": "992", "target": 27496,},

                ],
            },
        ],
    },
    {
        "line": "Optimized",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "Broach",
                "machines": [
                    {"number": "784", "target": 27496,},
                ],
            },
             {
                "op": "Heat",
                "machines": [
                    {"number": "770", "target": 27496,},

                ],
            },
             {
                "op": "Machine",
                "machines": [
                    {"number": "618", "target": 27496,},
                    {"number": "575", "target": 27496,},
                    {"number": "624", "target": 27496,},
                    {"number": "619", "target": 27496,},
                ],
            },
                         {
                "op": "Slurry",
                "machines": [
                    {"number": "769", "target": 27496,},
                ],
            },
        ],
    },
     {
        "line": "Trilobe",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "Broach",
                "machines": [
                    {"number": "573", "target": 27496,},
                ],
            },
             {
                "op": "Heat",
                "machines": [
                    {"number": "728", "target": 27496,},

                ],
            },
             {
                "op": "Machine",
                "machines": [
                    {"number": "644", "target": 27496,},
                    {"number": "645", "target": 27496,},
                    {"number": "646", "target": 27496,},
                    {"number": "647", "target": 27496,},
                    {"number": "649", "target": 27496,},
                ],
            },
                         {
                "op": "Slurry",
                "machines": [
                    {"number": "742", "target": 27496,},
                ],
            },
        ],
    },
     {
        "line": "Offline",
        "scrap_line": "NA",
        "operations": [
            {
                "op": "Machine",
                "machines": [
                    {"number": "636", "target": 27496,},
                    {"number": "625", "target": 27496,},
                    {"number": "595", "target": 27496,},
                    {"number": "637", "target": 27496,},
                    {"number": "638", "target": 27496,},
                ],
            },
        ],
    },

]

# ============================================================================
# ============================================================================
# ============================================================================
# ============================================================================
'''
You may wonder what this is. I did this to silently merge the untracked lines object into the lines object so it doesn't affect any OEE calculations 
but reflects the needs of the maintenance app that still has machines that go down even machines that are not being tracked
'''
# build a map by line name
_by_name = { L['line']: copy.deepcopy(L) for L in prod_lines_initial }

for un in lines_untracked:
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

    # ── 3) gather any still-open participations ───────────────────────────────
    open_parts_qs = DowntimeParticipation.objects.filter(
        event=event,
        leave_epoch__isnull=True
    )

    # ── 4) enforce “everyone must leave” for non-supervisors ─────────────────
    if open_parts_qs.exists():
        # 4a) anonymous users can never close out if people are still joined
        if not request.user.is_authenticated:
            return HttpResponseForbidden(
                "Authentication required to close out until all participants have left."
            )

        # 4b) only maintenance_supervisors OR maintenance_managers may override
        allowed = request.user.groups.filter(
            name__in=["maintenance_supervisors", "maintenance_managers"]
        ).exists()
        if not allowed:
            return HttpResponseForbidden(
                "Cannot close out until all participants have left."
            )

    # ── 5) compute epoch ───────────────────────────────────────────────────────
    epoch_ts = int(close_dt.timestamp())

    # ── 6) perform updates atomically ─────────────────────────────────────────
    with transaction.atomic():
        # 6a) close out the event itself
        event.closeout_epoch   = epoch_ts
        event.closeout_comment = closeout_comment
        event.save(update_fields=['closeout_epoch', 'closeout_comment'])

        # 6b) mark each still‐joined participation as left now
        for part in open_parts_qs:
            part.leave_epoch   = epoch_ts
            part.leave_comment = f"Job is finished: {closeout_comment}"
            part.total_minutes = math.ceil((epoch_ts - part.join_epoch) / 60)
            part.save(update_fields=['leave_epoch', 'leave_comment', 'total_minutes'])

    # ── 7) respond to caller ───────────────────────────────────────────────────
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
    """
    Downtime‐entry form: CATEGORY is required; SUBCATEGORY + code are optional.
    """
    #── Paging params ─────────────────────────────────────────────────
    offset    = int(request.GET.get('offset', 0))
    page_size = 300

    if request.method == "POST":
        #── Pull form data ─────────────────────────────────────────────
        entry_id     = request.POST.get('entry_id')   # None for new
        line         = request.POST.get('line', '').strip()
        machine      = request.POST.get('machine', '').strip()
        raw_cat      = request.POST.get('category', '').strip()
        raw_sub      = request.POST.get('subcategory', '').strip()
        start_date   = request.POST.get('start_date', '')   # "YYYY-MM-DD"
        start_time   = request.POST.get('start_time', '')   # "HH:MM"
        comment      = request.POST.get('description', '').strip()
        emp_id       = request.POST.get('employee_id', '').strip()
        raw_labour   = request.POST.get('labour_types', '[]')

        #── Parse labour JSON ──────────────────────────────────────────
        try:
            labour_list = json.loads(raw_labour)
            if not isinstance(labour_list, list):
                labour_list = []
        except json.JSONDecodeError:
            labour_list = []

        #── Validate & look up CATEGORY ───────────────────────────────
        if not raw_cat:
            return HttpResponseBadRequest("You must choose a category.")
        # find any DowntimeCode that starts with "raw_cat-"
        cat_obj = DowntimeCode.objects.filter(code__startswith=raw_cat + "-").first()
        if not cat_obj:
            return HttpResponseBadRequest("Invalid category code.")
        category_name = cat_obj.category

        #── Validate & look up SUBCATEGORY (optional) ─────────────────
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

        #── Build epoch timestamp ─────────────────────────────────────
        try:
            dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_default_timezone())
        except ValueError:
            return HttpResponseBadRequest("Bad date/time format.")
        epoch_ts = int(dt.timestamp())

        #── Create or update the event ───────────────────────────────
        if entry_id:
            e = get_object_or_404(MachineDowntimeEvent, pk=entry_id, is_deleted=False)
            e.line        = line
            e.machine     = machine
            e.category    = category_name
            e.subcategory = subcategory_name
            e.code        = code_value
            e.start_epoch = epoch_ts
            e.comment     = comment
            e.labour_types= labour_list
            e.employee_id = emp_id or None
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

        #── Redirect back, preserving ?offset=… ───────────────────────
        return redirect(request.get_full_path())

    #── GET: list open events + render form ─────────────────────────
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
                has_plctech = Exists(
            DowntimeParticipation.objects.filter(
                event=OuterRef('pk'),
                leave_epoch__isnull=True,
                user__groups__name='maintenance_plctech'
            )
        ),
        has_imt = Exists(
            DowntimeParticipation.objects.filter(
                event=OuterRef('pk'),
                leave_epoch__isnull=True,
                user__groups__name='maintenance_imt'
            )
        ),
    ).order_by('-start_epoch')

    total     = qs.count()
    entries   = list(qs[offset: offset + page_size])
    has_more  = (offset + page_size) < total

    # rebuild your JSON blobs for the selects just like before…
    downtime_codes = DowntimeCode.objects.all().order_by('category','subcategory','code')
    structured     = {}
    for c in downtime_codes:
        cat = c.code.split('-',1)[0]
        if cat not in structured:
            structured[cat] = {'name': c.category, 'code': cat, 'subcategories': []}
        structured[cat]['subcategories'].append({'code': c.code, 'name': c.subcategory})
    downtime_codes_list = list(structured.values())

    return render(request, 'plant/maintenance_form.html', {
        'entries':             entries,
        'offset':              offset,
        'page_size':           page_size,
        'has_more':            has_more,
        'downtime_codes_json': mark_safe(json.dumps(downtime_codes_list)),
        'lines_json':          mark_safe(json.dumps(prod_lines)),
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
    PAGE_SIZE = 500
    entries   = list(qs[:PAGE_SIZE])
    today     = timezone.localdate()
    tz        = get_default_timezone()
    for e in entries:
        dt = e.start_at
        if is_naive(dt):
            dt = make_aware(dt, tz)
        local_dt      = localtime(dt)
        e.start_display = (
            local_dt.strftime("%H:%M")
            if local_dt.date() == today
            else local_dt.strftime("%m/%d")
        )
        e.user_has_open = e.participants.filter(
            user=request.user,
            leave_epoch__isnull=True
        ).exists()

    # 4) Collect all maintenance‐role users
    User               = get_user_model()
    maint_groups       = list(ROLE_TO_GROUP.values())
    all_maint_users    = (
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
            name         = u.get_full_name() or u.username
            user_groups  = set(u.groups.values_list("name", flat=True))
            roles        = [
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
    full_choices   = MachineDowntimeEvent.LABOUR_CHOICES
    if is_manager or is_supervisor:
        labour_choices = list(full_choices)
    else:
        labour_choices = [
            (code, label) for code, label in full_choices
            if code not in ("PLCTECH", "IMT")
        ]

    # 9) Downtime‐codes JSON for the modal
    downtime_codes = DowntimeCode.objects.all().order_by("category","subcategory","code")
    structured     = {}
    for c in downtime_codes:
        cat = c.code.split("-",1)[0]
        structured.setdefault(cat, {
            "name": cat,
            "code": cat,
            "subcategories": []
        })["subcategories"].append({
            "code": c.code,
            "name": c.subcategory
        })

    # 10) Final render
    return render(request, "plant/maintenance_all_entries.html", {
        "entries":                    entries,
        "page_size":                  PAGE_SIZE,
        "line_priorities":            LinePriority.objects.all(),
        "is_manager":                 is_manager,
        "is_supervisor":              is_supervisor,
        "labour_choices":             labour_choices,
        "active_workers_by_role":     active_by_role,
        "inactive_workers_by_role":   inactive_by_role,
        "downtime_codes_json":        mark_safe(json.dumps(list(structured.values()))),
        "lines_json":                 mark_safe(json.dumps(prod_lines)),
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


def get_machine_priority_map():
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




@login_required
def employee_login_status(request):
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
    if request.method == 'GET':
        # extract just the line names
        line_names = [blk['line'] for blk in prod_lines]
        return JsonResponse({'lines': line_names})
    return HttpResponse(status=405)