import time
from django.db import connections
from django.views.decorators.cache import cache_page
from django.conf import settings
from importlib import import_module
import json
from datetime import datetime, timedelta
from django.http import Http404
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
import MySQLdb
from prod_query.models import OAMachineTargets
from collections import defaultdict

import pytz
from django.utils import timezone

import json
from typing import Dict, List, Set, Tuple, Optional, DefaultDict, Union

from django.http import JsonResponse, HttpResponseBadRequest
from django.db import connections
import copy
import math

# from https://github.com/DaveClark-Stackpole/trakberry/blob/e9fa660e2cdd5ef4d730e0d00d888ad80311cacc/trakberry/forms.py#L57
from django import forms


def sub_index(request):
    return redirect('dashboards:dashboard_index') 



class sup_downForm(forms.Form):
    machine = forms.CharField()
    reason = forms.CharField()
    priority = forms.CharField()


def pms_index_view(request):
    """Render the PMDSData12 index page, collecting metadata from each installed app.

    Iterates over `settings.INSTALLED_APPS`, skipping Django internals and specified
    middleware/apps. For each remaining app, it attempts to import `<app>.app_info` and,
    if a `get_app_info()` function is present, calls it and collects its result.
    Finally, renders `index_pms.html` with:
      - `main_heading`: "PMDSData12 Index"
      - `title`: "Index - pmdsdata12"
      - `app_infos`: List of metadata objects returned by each app's `get_app_info()`.

    Args:
        request (HttpRequest): The incoming request object.

    Returns:
        HttpResponse: The rendered index page with the collected app information.
    """
    context = {}
    context["main_heading"] = "PMDSData12 Index"
    context["title"] = "Index - pmdsdata12"
    
    app_infos = []
    for app in settings.INSTALLED_APPS:
        if app.startswith('django.') or app in ['whitenoise.runserver_nostatic', 'debug_toolbar', 'django_bootstrap5', 'widget_tweaks', 'corsheaders']:
            continue

        try:
            app_info_module = import_module(f"{app}.app_info")
            if hasattr(app_info_module, 'get_app_info'):
                app_info = app_info_module.get_app_info()
                app_infos.append(app_info)
        except ModuleNotFoundError:
            pass
        except AttributeError as e:
            pass

    context["app_infos"] = app_infos
    
    return render(request, 'index_pms.html', context)

def dashboard_index_view(request):
    context = {}
    context["main_heading"] = "Dashboard Index"
    context["title"] = "Dashboard Index - pmdsdata12"
    return render(request, f'dashboards/index_dashboard.html', context)

# from trakberry/trakberry/views_mod2.py
# Calculate Unix Shift Start times and return information


def stamp_shift_start():
    """Compute the Unix timestamps and durations for the current 8-hour shift.

    Determines which 8-hour shift block the local time falls into:
      - 06:00–14:00
      - 14:00–22:00
      - 22:00–06:00 (overnight)

    Returns:
        tuple:
            u (int): Unix timestamp at the start of the current shift.
            shift_time (int): Number of seconds elapsed since the shift started.
            shift_left (int): Number of seconds remaining until the shift ends.
            shift_end (int): Unix timestamp at the end of the current shift.
    """
    stamp = int(time.time())
    tm = time.localtime(stamp)
    hour1 = tm[3]
    t = int(time.time())
    tm = time.localtime(t)
    shift_start = -2
    current_shift = 3
    if tm[3] < 22 and tm[3] >= 14:
        shift_start = 14
    elif tm[3] < 14 and tm[3] >= 6:
        shift_start = 6
    cur_hour = tm[3]
    if cur_hour == 22:
        cur_hour = -1

    # Unix Time Stamp for start of shift Area 1
    u = t - (((cur_hour-shift_start)*60*60)+(tm[4]*60)+tm[5])

    # Amount of seconds run so far on the shift
    shift_time = t-u

    # Amount of seconds left on the shift to run
    shift_left = 28800 - shift_time

    # Unix Time Stamp for the end of the shift
    shift_end = t + shift_left

    return u, shift_time, shift_left, shift_end


def stamp_shift_start_3():
    """Calculate the start, elapsed, remaining, and end times for 8-hour shifts.

    This uses a three-shift schedule with local start times at:
      - 07:00–15:00
      - 15:00–23:00
      - 23:00–07:00 (overnight)

    It determines the current shift based on the local hour, then computes:
      - `u`: Unix timestamp at the shift’s start
      - `shift_time`: seconds elapsed since `u`
      - `shift_left`: seconds remaining until the 8-hour shift ends
      - `shift_end`: Unix timestamp at the shift’s end

    Returns:
        tuple[int, int, int, int]:
            u (int): Shift start timestamp.
            shift_time (int): Seconds elapsed in current shift.
            shift_left (int): Seconds remaining in current shift.
            shift_end (int): Shift end timestamp.
    """
    stamp = int(time.time())
    tm = time.localtime(stamp)
    hour1 = tm[3]
    t = int(time.time())
    tm = time.localtime(t)
    shift_start = -2
    current_shift = 3
    if tm[3] < 23 and tm[3] >= 15:
        shift_start = 15
    elif tm[3] < 15 and tm[3] >= 7:
        shift_start = 7
    cur_hour = tm[3]
    if cur_hour == 23:
        cur_hour = -1

    # Unix Time Stamp for start of shift Area 1
    u = t - (((cur_hour-shift_start)*60*60)+(tm[4]*60)+tm[5])

    # Amount of seconds run so far on the shift
    shift_time = t-u

    # Amount of seconds left on the shift to run
    shift_left = 28800 - shift_time

    # Unix Time Stamp for the end of the shift
    shift_end = t + shift_left

    return u, shift_time, shift_left, shift_end


"""
below applies to all these dashboard views

# t (t) = current timestamp
# codes (total8) =[('1504', 96, '#4FC34F', 338, 10, 8), ...
#                  [1]=asset number
#                  [2]=production this shift
#                  [3]=cell background color
#                  [4]=projected production
#                  [5]= operation 10, 20, 30
#                  [6]= ?

# op (op_total) = [0,0,... [10]= op 10 total count, [20] = op 20 etc]

# wip (wip_zip) = [('10', 8383, 36, 8391),(20, ...),(30, ...), ...]

# codes_60 (total8_0455) same as codes but for 10R60 part
# op_60 (op_total_0544) same as op_total above but for 10R60 part
# wip_60 (wip_zip_0455) same as wip_zip above but for 10R60 part

# args csrf token and form
"""
def get_line_prod(line_spec, line_target, parts, shift_start, shift_time):
    """Compute current and predicted production metrics for each machine and operation.

    Queries the GFxPRoduction table to get counts over two intervals:
      1. The last 5 minutes (for short‐term rate/color coding).
      2. Since the start of the shift (for cumulative and prediction).

    It then:
      - Calculates `prod_last_five` and `prod_now` per machine (applying any scale factor).
      - Estimates `predicted_production` for the 8-hour shift based on current rate.
      - Determines a `cell_colour` based on how the last‐five‐minute output compares to the per-machine target.
      - Aggregates predicted production by `operation`.

    Args:
        line_spec (list of tuple): Machine specifications. Each tuple is:
            (asset, sources, machine_rate, operation[, scale]) where:
            - asset (str): identifier on the dashboard,
            - sources (iterable): list of machine IDs in the DB,
            - machine_rate (int): number of machines contributing to the line’s target,
            - operation (int): index for grouping results,
            - scale (float, optional): multiplier for counts (default=1).
        line_target (int | float): Total production goal for the entire line over the shift.
        parts (str): SQL fragment for `AND Part IN (…)` or empty string for no filter.
        shift_start (int): Unix timestamp marking the start of the current shift.
        shift_time (int): Seconds elapsed since `shift_start`.

    Returns:
        tuple:
            machine_production (list of tuple): One tuple per machine:
                (asset, prod_now, cell_colour, predicted_production, operation, machine_rate)
            operation_production (list of int): Predicted production aggregated by operation index.
    """
    cursor = connections['prodrpt-md'].cursor()

    sql =  'SELECT Machine, COUNT(*) '
    sql += 'FROM GFxPRoduction '
    sql += 'WHERE TimeStamp >= %s '
    if parts:
        sql += f'AND Part IN ({parts}) '
    sql += 'GROUP BY Machine;'

    # Get production from last 5 mins for color coding
    five_mins_ago = shift_start + shift_time - 300
    cursor.execute(sql, [five_mins_ago])
    prod_last5 = cursor.fetchall()

    # Get production since start of shift for current and prediciton
    cursor.execute(sql, [shift_start])
    prod_shift = cursor.fetchall()

    machine_production = []
    operation_production = [0]*200

    for machine in line_spec:  # build the list of tupples for the template
        asset = machine[0]  # this is the asset number on the dashboard
        # change this to the asset you want to take the count from
        sources = machine[1]
        machine_rate = machine[2]
        operation = machine[3]
        scale = 1
        if len(machine) == 5:
            scale = machine[4]

        prod_last_five = 0
        prod_now = 0

        for source in sources:
            count_index = next(
                (i for i, v in enumerate(prod_last5) if v[0] == source), -1)
            if count_index > -1:
                prod_last_five += prod_last5[count_index][1] * scale
            else:
                prod_last_five += 0

            count_index = next(
                (i for i, v in enumerate(prod_shift) if v[0] == source), -1)
            if count_index > -1:
                prod_now += prod_shift[count_index][1] * scale
            else:
                prod_now += 0

        # Pediction
        try:
            shift_rate = prod_now / float(shift_time)
        except:
            shift_time = 100
            shift_rate = prod_now / float(shift_time)

        predicted_production = int(
            prod_now + (shift_rate * (28800 - shift_time)))

        # choose a color based on last 5 mins production vs machine rate
        # need 3200 in 8 hours.  Machine is one of X machines
        machine_target = line_target / machine_rate
        # need 'rate' parts in 5 minutes to make 3200 across cell
        five_minute_target = (machine_target / 28800) * 300
        five_minute_percentage = int(prod_last_five / five_minute_target * 100)
        if five_minute_percentage >= 100:
            cell_colour = '#009700'
        elif five_minute_percentage >= 90:
            cell_colour = '#4FC34F'
        elif five_minute_percentage >= 80:
            cell_colour = '#A4F6A4'
        elif five_minute_percentage >= 70:
            cell_colour = '#C3C300'
        elif five_minute_percentage >= 50:
            cell_colour = '#DADA3F'
        elif five_minute_percentage >= 25:
            cell_colour = '#F6F687'  # light Yellow
        elif five_minute_percentage >= 10:
            cell_colour = '#F7BA84'  # brown
        elif five_minute_percentage > 0:
            cell_colour = '#EC7371'  # faded red
        else:
            if predicted_production == 0:
                cell_colour = '#D5D5D5'  # Grey
            else:
                cell_colour = '#FF0400'  # Red

        machine_production.append(
            (asset, prod_now, cell_colour,
             predicted_production, operation, machine_rate)
        )
        operation_production[operation] += predicted_production

    return machine_production, operation_production


# this version returns an expanded OP structure with colors
def get_line_prod2(line_spec, line_target, parts, shift_start, shift_time):
    """Compute detailed production metrics with color‐coding for machines and operations.

    Retrieves counts from the GFxPRoduction table for both:
      - The last 5 minutes (for real‐time color thresholds), and
      - Since the shift start (for cumulative and prediction).

    For each machine in `line_spec`, it calculates:
      1. `prod_last_five` and `prod_now` (applying an optional scale factor).
      2. A `predicted_production` value for the full 8‐hour shift based on current rate.
      3. A `cell_colour` based on how the last‐five‐minute output compares to the per‐machine target.

    Then aggregates predicted production by `operation` and applies color thresholds
    at the operation level to produce an “expanded OP” structure.

    Args:
        line_spec (list of tuple):
            Each tuple defines a machine:
               (asset, source, machine_rate, operation[, scale])
        line_target (int | float):
            Total production goal across all machines for the shift.
        parts (str):
            SQL fragment for filtering `Part IN (…)`, or empty string for no filter.
        shift_start (int):
            Unix timestamp marking the shift’s start.
        shift_time (int):
            Seconds elapsed since `shift_start`.

    Returns:
        tuple:
            machine_production (list of tuple):
                One entry per machine:
                (asset, prod_now, cell_colour, predicted_production, operation, machine_rate)
            coloured_op_production (list of tuple):
                Indexed by operation, each value is:
                (aggregated_predicted_production, color) for that operation.
    """
    cursor = connections['prodrpt-md'].cursor()

    sql =  'SELECT Machine, COUNT(*) '
    sql += 'FROM GFxPRoduction '
    sql += 'WHERE TimeStamp >= %s '
    if parts:
        sql += f'AND Part IN ({parts}) '
    sql += 'GROUP BY Machine;'

    # Get production from last 5 mins for color coding
    five_mins_ago = shift_start + shift_time - 300
    cursor.execute(sql, [five_mins_ago])
    prod_last5 = cursor.fetchall()

    # Get production since start of shift for current and prediciton
    cursor.execute(sql, [shift_start])
    prod_shift = cursor.fetchall()

    machine_production = []
    operation_production = [0]*200

    for machine in line_spec:  # build the list of tupples for the template
        asset = machine[0]  # this is the asset number on the dashboard
        # change this to the asset you want to take the count from
        source = machine[1]
        machine_rate = machine[2]
        operation = machine[3]
        scale = 1
        if len(machine) == 5:
            scale = machine[4]

        count_index = next(
            (i for i, v in enumerate(prod_last5) if v[0] == source), -1)
        if count_index > -1:
            prod_last_five = prod_last5[count_index][1] * scale
        else:
            prod_last_five = 0

        count_index = next(
            (i for i, v in enumerate(prod_shift) if v[0] == source), -1)
        if count_index > -1:
            prod_now = prod_shift[count_index][1] * scale
        else:
            prod_now = 0

        # Pediction
        try:
            shift_rate = prod_now / float(shift_time)
        except:
            shift_time = 100
            shift_rate = prod_now / float(shift_time)

        predicted_production = int(
            prod_now + (shift_rate * (28800 - shift_time)))

        # choose a color based on last 5 mins production vs machine rate
        # need 3200 in 8 hours.  Machine is one of X machines
        machine_target = line_target / machine_rate
        # need 'rate' parts in 5 minutes to make 3200 across cell
        five_minute_target = (machine_target / 28800) * 300
        five_minute_percentage = int(prod_last_five / five_minute_target * 100)
        if five_minute_percentage >= 100:
            cell_colour = '#009700'
        elif five_minute_percentage >= 90:
            cell_colour = '#4FC34F'
        elif five_minute_percentage >= 80:
            cell_colour = '#A4F6A4'
        elif five_minute_percentage >= 70:
            cell_colour = '#C3C300'
        elif five_minute_percentage >= 50:
            cell_colour = '#DADA3F'
        elif five_minute_percentage >= 25:
            cell_colour = '#F6F687'  # light Yellow
        elif five_minute_percentage >= 10:
            cell_colour = '#F7BA84'  # brown
        elif five_minute_percentage > 0:
            cell_colour = '#EC7371'  # faded red
        else:
            if predicted_production == 0:
                cell_colour = '#D5D5D5'  # Grey
            else:
                cell_colour = '#FF0400'  # Red

        machine_production.append(
            (asset, prod_now, cell_colour,
             predicted_production, operation, machine_rate)
        )
        operation_production[operation] += predicted_production

    coloured_op_production = [0 for x in range(200)]
    for idx, op in enumerate(operation_production):
        if op > line_target:
            color = '#68FF33'
        elif op > line_target*.85:
            color = '#F9FF33'
        else:
            color = '#FF9333'
        coloured_op_production[idx] = (op, color)

    return machine_production, coloured_op_production

@cache_page(5)
def cell_track_9341(request, target):
    """Display real-time and predictive production metrics for cell 9341 (and 0455) with caching.

    Retrieves shift timing, production targets, and site variables, then:
      1. Computes the current shift start, elapsed, remaining, and end times.
      2. Fetches last-5-minute and cumulative production for part family "50-9341" 
         using `get_line_prod2()`, and logs shift counts via `log_shift_times()`.
      3. Computes per-operation actual output and OEE metrics with `compute_op_actual_and_oee()`.
      4. Repeats steps 2–3 for part family "50-0455".
      5. Handles optional date/shift history submission via `sup_downForm`.
      6. Stores run rate and computes color codes for overall cell performance.
      7. Renders the appropriate template (`dashboards/cell_track_9341.html`) based on `target`.

    Caching:
        The page is cached for 5 seconds to reduce database load under rapid refresh.

    Args:
        request (HttpRequest): The incoming HTTP request containing session and POST data.
        target (str): Display mode indicator (e.g. 'tv', 'mobile') to select the template styling.

    Returns:
        HttpResponse: Rendered dashboard page with context containing:
            - 'codes', 'codes_60': per-machine production tuples
            - 'op', 'op_60': per-operation production/color tuples
            - 'op_actual', 'op_oee', 'op_actual_60', 'op_oee_60': actual/output and OEE metrics
            - Shift timing, run rate, WIP lists, color codes, and history form args.
    """
    tic = time.time()  # track the execution time
    context = {}  # data sent to template
    context['page_title'] = '9341 Tracking'

    target_production_9341 = int(
        request.site_variables.get('target_production_9341', 2900))
    target_production_0455 = int(
        request.site_variables.get('target_production_0455', 900))

    # Get the Time Stamp info
    shift_start, shift_time, shift_left, shift_end = stamp_shift_start()
    context['t'] = shift_start + shift_time
    request.session['shift_start'] = shift_start

    line_spec_9341 = [  # ('Asset','source', rate, OP)
        # Main line
        ('1504', '1504', 8, 10), ('1506', '1506', 8, 10), ('1519', '1519', 8, 10), ('1520', '1520', 8, 10),
        ('1502', '1502', 4, 30), ('1507', '1507', 4, 30),
        ('1501', '1501', 4, 40), ('1515', '1515', 4, 40),
        ('1508', '1508', 4, 50), ('1532', '1532', 4, 50),
        ('1509', '1509', 2, 60),
        ('1514', '1514', 2, 70),
        ('1510', '1510', 2, 80),
        ('1503', '1503', 2, 100),
        ('1511', '1511', 2, 110),
        # Offline
        ('1518', '1518', 8, 10), ('1521', '1521', 8, 10), ('1522', '1522', 8, 10), ('1523', '1523', 8, 10),
        ('1539', '1539', 4, 30), ('1540', '1540', 4, 30),
        ('1524', '1524', 4, 40), ('1525', '1525', 4, 40),
        ('1538', '1538', 4, 50),
        ('1541', '1541', 2, 60),
        ('1531', '1541', 2, 70),
        ('1527', '1527', 2, 80),
        ('1530', '1530', 2, 100),
        ('1528', '1528', 2, 110),
        ('1513', '1513', 2, 90),
        ('1533', '1533', 2, 120),
        # uplift
        ('1546', '1546', 2, 30),
        ('1547', '1547', 2, 40),
        ('1548', '1548', 2, 50),
        ('1549', '1549', 2, 60),
        ('594', '1549', 2, 70),
        ('1551', '1551', 2, 80),
        ('1552', '1552', 2, 90),
        ('751', '751', 2, 100),
        ('1554', '1554', 2, 110),
    ]


    machine_production_9341, op_production_9341 = get_line_prod2(
        line_spec_9341, target_production_9341, '"50-9341"', shift_start, shift_time)

    context['codes'] = machine_production_9341
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_9341]
    part_list = ["50-9341"]
    context['actual_counts'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op'] = op_production_9341

    # -- surgical insertion here --
    op_actual_9341, op_oee_9341 = compute_op_actual_and_oee(
        line_spec_9341,
        machine_production_9341,
        shift_start,
        shift_time,
        part_list=["50-9341"]
    )
    context['op_actual'] = op_actual_9341
    context['op_oee']    = op_oee_9341

    context['wip'] = []

    line_spec = [  # ('Asset','Count', rate, OP)
        # Main line
        ('1800', '1800', 2, 10), ('1801', '1801', 2, 10), ('1802', '1802', 2, 10),
        ('1529', '1529', 4, 30), ('1543', '1543', 4, 30), ('776', '776', 4, 30), ('1824', '1824', 4, 30),
        ('1804', '1804', 2, 40), ('1805', '1805', 2, 40),
        ('1806', '1806', 1, 50),
        ('1808', '1808', 1, 60),
        ('1810', '1810', 1, 70),
        ('1815', '1815', 1, 80),
        ('1542', '1812', 1, 90),
        ('1812', '1812', 1, 100),
        ('1813', '1813', 1, 110),
        ('1816', '1816', 1, 120),
    ]



    machine_production_0455, op_production_0455 = get_line_prod2(
        line_spec, target_production_0455, '"50-0455"', shift_start, shift_time)

    context['codes_60'] = machine_production_0455
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_0455]
    part_list = ["50-0455"]
    context['actual_counts_60'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op_60'] = op_production_0455

    # -- surgical insertion here for 0455 OEE stuff --
    op_actual_60, op_oee_60 = compute_op_actual_and_oee(
        line_spec,
        machine_production_0455,
        shift_start,
        shift_time,
        part_list=["50-0455"]
    )
    context['op_actual_60'] = op_actual_60
    context['op_oee_60']    = op_oee_60

    context['wip_60'] = []

    # Date entry for History
    if request.POST:
        request.session["track_date"] = request.POST.get("date_st")
        request.session["track_shift"] = request.POST.get("shift")
        return render(request, 'redirect_cell_track_9341_history.html')
    else:
        form = sup_downForm()
    args = {'form': form}
    context['args'] = args
    request.session['runrate'] = 1128

    r80 = op_production_9341[120][0]
    c80 = "#bdb4b3"
    c60 = "#bdb4b3"
    if r80 >= target_production_9341:
        c80 = "#7FEB1E"
    elif r80 >= target_production_9341 * .9:
        c80 = "#FFEB55"
    else:
        c80 = "#FF7355"
    context['R80'] = c80

    r60 = op_production_0455[120][0]
    if r60 >= target_production_0455:
        c60 = "#7FEB1E"
    elif r60 >= target_production_0455 * .9:
        c60 = "#FFEB55"
    else:
        c60 = "#FF7355"
    context['R60'] = c60

    context['elapsed'] = time.time()-tic
    context['target'] = target
    if target == 'tv':
        template = 'dashboards/cell_track_9341.html'
    elif target == 'mobile':
        template = 'dashboards/cell_track_9341.html'
    else:
        template = 'dashboards/cell_track_9341.html'

    return render(request, template, context)



@cache_page(5)
def cell_track_1467(request, template):
    """Display real-time and cumulative production metrics for cell 1467 with short-term caching.

    This view performs the following steps:
      1. Retrieves the shift start and elapsed times via `stamp_shift_start()`.
      2. Reads the production target for part family "50-1467" from `request.site_variables`.
      3. Defines the line specification for machines 644–649.
      4. Calls `get_line_prod()` to fetch last-5-minute and shift-to-date counts, plus predictions.
      5. Logs shift counts via `log_shift_times()`.
      6. Assembles context variables:
         - `codes`: per-machine production tuples
         - `actual_counts`: time-series data for charting
         - `op`: per-operation aggregated production
         - `wip`: work-in-progress list (empty by default)
         - `args`: form arguments for history lookup
         - `runrate`: stored run-rate value
         - `elapsed`: view execution time
      7. On POST, captures date/shift for history and renders a redirect template.
      8. Otherwise, renders the specified dashboard template under `dashboards/`.

    Caching:
        The output is cached for 5 seconds via `@cache_page(5)` to reduce load under frequent reloads.

    Args:
        request (HttpRequest): Incoming request, including session and POST data.
        template (str): Filename of the dashboard template (e.g. 'cell_track_1467.html').

    Returns:
        HttpResponse: The rendered dashboard page or a history‐redirect page on POST.
    """
    tic = time.time()  # track the execution time
    context = {}  # data sent to template

    target_production_1467 = int(
        request.site_variables.get('target_production_1467', 1400))

    # Get the Time Stamp info
    shift_start, shift_time, shift_left, shift_end = stamp_shift_start()
    context['t'] = shift_start + shift_time
    request.session["shift_start"] = shift_start

    line_spec = [
        ('644', ['644'], 6, 10),
        ('645', ['645'], 6, 10), 
        ('646', ['646'], 6, 10),
        ('647', ['647'], 6, 10), 
        ('649', ['649'], 6, 10),
    ]

    # Right here I will call the new function

    machine_production, op_production = get_line_prod(
        line_spec, target_production_1467, '"50-1467"', shift_start, shift_time)

    context['codes'] = machine_production
    actual_counts = [(mp[0], mp[1]) for mp in machine_production]
    part_list = ["50-1467"]
    context['actual_counts'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op'] = op_production
    context['wip'] = []

    # Date entry for History
    if request.POST:
        request.session["track_date"] = request.POST.get("date_st")
        request.session["track_shift"] = request.POST.get("shift")
        return render(request, 'redirect_cell_track_1467_history.html')
    else:
        form = sup_downForm()
    args = {}
    # args.update(csrf(request))
    args['form'] = form
    context['args'] = args
    request.session['runrate'] = 1128
    context['elapsed'] = time.time()-tic

    return render(request, f'dashboards/{template}', context)

@cache_page(5)
def cell_track_trilobe(request, template):
    """Display real-time and predictive production and OEE metrics for the Trilobe cell line.

    Caches the view for 5 seconds to reduce load under frequent refresh.

    Workflow:
      1. Reads four production targets from `request.site_variables`:
         - `target_production_trilobe_sinter`
         - `target_production_trilobe_optimized`
         - `target_production_trilobe_trilobe`
         - `target_production_trilobe_optimized` (again, if configured)
      2. Uses `stamp_shift_start_3()` to determine the current 8-hour shift start, elapsed time, etc.
      3. For each of four column specifications (`line_spec_col_1` through `line_spec_col_4`):
         a. Calls `get_line_prod()` to fetch last-5-minute and shift-to-date counts plus predictions.  
         b. Logs shift counts via `log_shift_times()`.  
         c. Computes per-operation actual output and OEE metrics via `compute_op_actual_and_oee()`.  
         d. Populates context keys:
             - `codes_colN`, `actual_counts_colN`, `op_colN`, `op_actual_colN`, `op_oee_colN`, `wip_colN`
      4. On POST, captures `date_st` and `shift` into the session and renders a history-redirect template.
      5. Measures total execution time and passes it in context.

    Args:
        request (HttpRequest): The incoming request, including session, site variables, and POST data.
        template (str): The name of the dashboard template to render (e.g. `'cell_track_trilobe.html'`).

    Returns:
        HttpResponse: The rendered dashboard page with context containing production metrics, OEE, timing, and history form.
    """
    tic = time.time()  # track the execution time
    context = {}  # data sent to template

    target_production_col1 = int(
        request.site_variables.get('target_production_trilobe_sinter', 300))
    target_production_col2 = int(
        request.site_variables.get('target_production_trilobe_optimized', 300))
    target_production_col3 = int(
        request.site_variables.get('target_production_trilobe_trilobe', 300))
    target_production_col4 = int(request.site_variables.get(
        'target_production_trilobe_optimized', 300))

    # Get the Time Stamp info
    shift_start, shift_time, shift_left, shift_end = stamp_shift_start_3()
    context['t'] = shift_start + shift_time
    request.session["shift_start"] = shift_start

    line_spec_col_1 = [
        ('262', ['262'], 2, 10),  # Compact
        ('263', ['263'], 2, 10),  # Compact
        ('859', ['859'], 1, 20),  # nothing
        ('992', ['992'], 1, 30),  # nothing
    ]


    machine_production_col1, op_production_col1 = get_line_prod(
        line_spec_col_1, target_production_col1, None, shift_start, shift_time)

    context['codes_col1'] = machine_production_col1
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_col1]
    part_list = None
    context['actual_counts_col1'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op_col1'] = op_production_col1

    # -- surgical insertion here for Col 1 OEE stuff --
    op_actual_col1, op_oee_col1 = compute_op_actual_and_oee(
        line_spec_col_1,
        machine_production_col1,
        shift_start,
        shift_time,
        part_list=None
    )
    context['op_actual_col1'] = op_actual_col1
    context['op_oee_col1']    = op_oee_col1


    context['wip'] = []

    line_spec_col_2 = [
        ('784', ['770'], 1, 10),  # 50-1467, 50-3050, 50-5710
        ('770', ['770'], 1, 20),  # 50-1467, 50-3050, 50-5710
        ('618', ['618'], 4, 30),  # magna
        ('575', ['575'], 4, 30),  # manga
        ('624', ['624'], 4, 30),  # magna
        ('619', ['619'], 4, 30),  # magna
        ('769', ['769'], 1, 40),  # 50-1467, 50-3050, 50-5710
    ]


    machine_production_col2, op_production_col2 = get_line_prod(
        line_spec_col_2, target_production_col2, None, shift_start, shift_time)

    context['codes_col2'] = machine_production_col2
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_col2]
    part_list = None
    context['actual_counts_col2'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op_col2'] = op_production_col2


    # -- surgical insertion here for Col 2 OEE stuff --
    op_actual_col2, op_oee_col2 = compute_op_actual_and_oee(
        line_spec_col_2,
        machine_production_col2,
        shift_start,
        shift_time,
        part_list=None
    )
    context['op_actual_col2'] = op_actual_col2
    context['op_oee_col2']    = op_oee_col2



    context['wip_col2'] = []

    line_spec_col_3 = [
        ('573', ['728'], 1, 10),  # 50-1467
        ('728', ['728'], 1, 20),  # 50-1467
        ('644', ['644'], 6, 30),  # 50-1467
        ('645', ['645'], 6, 30),  # 50-1467
        ('646', ['646'], 6, 30),  # 50-1467
        ('647', ['647'], 6, 30),  # 50-1467
        ('649', ['649'], 6, 30),  # 50-1467
        ('742', ['742', '650L', '650R'], 1, 40),  # 50-1467    # 650L and 650R replaced with 742 5/28/2024
    ]


    machine_production_col3, op_production_col3 = get_line_prod(
        line_spec_col_3, target_production_col3, None, shift_start, shift_time)

    context['codes_col3'] = machine_production_col3
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_col3]
    part_list = None
    context['actual_counts_col3'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op_col3'] = op_production_col3

    # -- surgical insertion here for Col 3 OEE stuff --
    op_actual_col3, op_oee_col3 = compute_op_actual_and_oee(
        line_spec_col_3,
        machine_production_col3,
        shift_start,
        shift_time,
        part_list=None
    )
    context['op_actual_col3'] = op_actual_col3
    context['op_oee_col3']    = op_oee_col3

    context['wip_col3'] = []

    line_spec_col_4 = [
        ('636', ['636'], 1, 10),  # 50-5710
        ('625', ['625'], 1, 20),  # 50-5710
        ('Prediction', ['625', '636'], 1, 30),
    ]

    machine_production_col4, op_production_col4 = get_line_prod(
        line_spec_col_4, target_production_col4, None, shift_start, shift_time)

    context['codes_col4'] = machine_production_col4
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_col4]
    part_list = None
    context['actual_counts_col4'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op_col4'] = op_production_col4


    # -- surgical insertion here for Col 4 OEE stuff --
    op_actual_col4, op_oee_col4 = compute_op_actual_and_oee(
        line_spec_col_4,
        machine_production_col4,
        shift_start,
        shift_time,
        part_list=None
    )
    context['op_actual_col4'] = op_actual_col4
    context['op_oee_col4']    = op_oee_col4


    context['wip_col4'] = []

    # Date entry for History
    if request.POST:
        request.session["track_date"] = request.POST.get("date_st")
        request.session["track_shift"] = request.POST.get("shift")
        return render(request, 'redirect_cell_track_8670_history.html')
    else:
        form = sup_downForm()
    args = {}
    # args.update(csrf(request))
    args['form'] = form
    context['args'] = args

    context['elapsed'] = time.time()-tic
    return render(request, f'dashboards/{template}', context)

# @cache_page(5)
# def cell_track_8670(request, template):
#     tic = time.time()  # track the execution time
#     context = {}  # data sent to template

#     target_production_AB1V_Rx = int(
#         request.site_variables.get('target_production_AB1V_Rx', 300))
#     target_production_AB1V_Input = int(
#         request.site_variables.get('target_production_AB1V_Input', 300))
#     target_production_AB1V_OD = int(
#         request.site_variables.get('target_production_AB1V_OD', 300))
#     target_production_10R140 = int(request.site_variables.get(
#         'target_production_10R140_Rear', 300))

#     # Get the Time Stamp info
#     shift_start, shift_time, shift_left, shift_end = stamp_shift_start_3()
#     context['t'] = shift_start + shift_time
#     request.session["shift_start"] = shift_start

#     line_spec_10R140 = [
#         # OP 10
#         ('1708L', ['1708L'], 2, 10),
#         ('1708R', ['1708R'], 2, 10),
#         # OP 20
#         ('1709', ['1708L', '1708R'], 1, 20),
#         # OP 30
#         ('1710', ['1710'], 1, 30),
#         # OP 40
#         ('1711', ['1711'], 1, 40),
#         # OP 50
#         ('1715', ['1715'], 1, 50),
#         # OP 60
#         ('1717R', ['1717R'], 1, 60),
#         # OP 70
#         ('1706', ['1706'], 1, 70),
#         # OP 80
#         ('1720', ['1720'], 1, 80),
#         # OP 90
#         ('677', ['677'], 1, 90),
#         ('748', ['748'], 1, 90),
#         # OP 100
#         ('1723', ['1723'], 1, 100),
#         # Laser
#         ('1725', ['1725'], 1, 130),
#     ]



#     machine_production_10R140, op_production_10R140 = get_line_prod(
#         line_spec_10R140, target_production_10R140, '"50-3214","50-5214"', shift_start, shift_time)

#     context['codes_10R140'] = machine_production_10R140
#     actual_counts = [(mp[0], mp[1]) for mp in machine_production_10R140]
#     part_list = ["50-3214", "50-5214"]
#     context['actual_counts_10R140'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
#     context['op_10R140'] = op_production_10R140


#     # -- surgical insertion for 10R140 OEE stuff --
#     op_actual_10R140, op_oee_10R140 = compute_op_actual_and_oee(
#         line_spec_10R140,
#         machine_production_10R140,
#         shift_start,
#         shift_time,
#         part_list=["50-3214", "50-5214"]
#     )
#     context['op_actual_10R140'] = op_actual_10R140
#     context['op_oee_10R140']    = op_oee_10R140

#     context['wip_10R140'] = []

#     line_spec_8670 = [
#         # OP 10
#         ('1703L', ['1703L'], 4, 10), ('1704L', ['1704L'], 4, 10),
#         ('658', ['658'], 4, 10), ('661', ['661'], 4, 10),
#         ('622', ['622'], 4, 10),
#         # OP 20/30
#         ('1703R', ['1703R'], 4, 30), ('1704R', ['1704R'], 4, 30),
#         ('616', ['616'], 4, 30), ('623', ['623'], 4, 30),
#         ('617', ['617'], 4, 30),
#         # OP 40
#         ('1727', ['1727'], 1, 40),
#         # OP 50
#         ('659', ['659'], 2, 50), ('626', ['626'], 2, 50),
#         # OP 60
#         ('1712', ['1712'], 1, 60),
#         ('1716L', ['1716L'], 1, 70),
#         ('1719', ['1719'], 1, 80),
#         ('1723', ['1723'], 1, 90),
#         ('1750', ['1750'], 1, 130),
#         ('1724', ['1724'], 1, 130),
#         ('1725', ['1725'], 1, 130),
#     ]


#     machine_production_8670, op_production_8670 = get_line_prod(
#         line_spec_8670, target_production_AB1V_Rx, '"50-8670","50-0450"', shift_start, shift_time)

#     context['codes'] = machine_production_8670
#     actual_counts = [(mp[0], mp[1]) for mp in machine_production_8670]
#     part_list = ["50-8670", "50-0450"]
#     context['actual_counts'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
#     context['op'] = op_production_8670


#     # -- surgical insertion for 8670 OEE stuff --
#     op_actual_8670, op_oee_8670 = compute_op_actual_and_oee(
#         line_spec_8670,
#         machine_production_8670,
#         shift_start,
#         shift_time,
#         part_list=["50-8670", "50-0450"]
#     )
#     context['op_actual_8670'] = op_actual_8670
#     context['op_oee_8670']    = op_oee_8670


#     context['wip'] = []

#     line_spec_5401 = [
#         ('1740L', ['1740L'], 2, 10), ('1740R', ['1740R'], 2, 10),
#         ('1701L', ['1701L'], 2, 40), ('1701R', ['1701R'], 2, 40),
#         ('733', ['1701L', '1701R'], 1, 50),
#         ('775', ['775'], 2, 60), ('1702', ['1702'], 2, 60),
#         ('581', ['581'], 2, 70), ('788', ['788'], 2, 70),
#         ('1714', ['1714'], 1, 80),
#         ('1717L', ['1717L'], 1, 90),
#         ('1706', ['1706'], 1, 100),
#         ('1723', ['1723'], 1, 110),
#         ('1750', ['1750'], 1, 130),
#         ('1724', ['1724'], 1, 130),
#         ('1725', ['1725'], 1, 130),
#     ]


#     machine_production_5401, op_production_5401 = get_line_prod(
#         line_spec_5401, target_production_AB1V_Input, '"50-5401","50-0447"', shift_start, shift_time)

#     context['codes_5401'] = machine_production_5401
#     actual_counts = [(mp[0], mp[1]) for mp in machine_production_5401]
#     part_list = ["50-5401", "50-0447"]
#     context['actual_counts_5401'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
#     context['op_5401'] = op_production_5401


#     # -- surgical insertion for 5401 OEE stuff --
#     op_actual_5401, op_oee_5401 = compute_op_actual_and_oee(
#         line_spec_5401,
#         machine_production_5401,
#         shift_start,
#         shift_time,
#         part_list=["50-5401", "50-0447"]
#     )
#     context['op_actual_5401'] = op_actual_5401
#     context['op_oee_5401']    = op_oee_5401


#     context['wip_5401'] = []

#     line_spec_5404 = [
#         ('1705', ['1705L'], 2, 20), ('1746', ['1746R'], 2, 20),
#         ('621', ['621'], 2, 25), ('629', ['629'], 2, 25),
#         ('785', ['785'], 3, 30), ('1748', ['1748'],
#                                   3, 30), ('1718', ['1718'], 3, 30),
#         ('669', ['669'], 1, 35),
#         ('1726', ['1726'], 1, 40),
#         ('1722', ['1722'], 1, 50),
#         ('1713', ['1713'], 1, 60),
#         ('1716R', ['1716R'], 1, 70),
#         ('1719', ['1719'], 1, 80),
#         ('1723', ['1723'], 1, 90),
#         ('1750', ['1750'], 1, 130),
#         ('1724', ['1724'], 1, 130),
#         ('1725', ['1725'], 1, 130),
#     ]


#     target_production = 300
#     machine_production_5404, op_production_5404 = get_line_prod(
#         line_spec_5404, target_production_AB1V_OD, '"50-5404","50-0519"', shift_start, shift_time)

#     context['codes_5404'] = machine_production_5404
#     actual_counts = [(mp[0], mp[1]) for mp in machine_production_5404]
#     part_list = ["50-5404", "50-0519"]
#     context['actual_counts_5404'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
#     context['op_5404'] = op_production_5404


#     # -- surgical insertion for 5404 OEE stuff --
#     op_actual_5404, op_oee_5404 = compute_op_actual_and_oee(
#         line_spec_5404,
#         machine_production_5404,
#         shift_start,
#         shift_time,
#         part_list=["50-5404", "50-0519"]
#     )
#     context['op_actual_5404'] = op_actual_5404
#     context['op_oee_5404']    = op_oee_5404


#     context['wip_5404'] = []

#     # Date entry for History
#     if request.POST:
#         request.session["track_date"] = request.POST.get("date_st")
#         request.session["track_shift"] = request.POST.get("shift")
#         return render(request, 'redirect_cell_track_8670_history.html')
#     else:
#         form = sup_downForm()
#     args = {}
#     # args.update(csrf(request))
#     args['form'] = form
#     context['args'] = args

#     context['elapsed'] = time.time()-tic
#     return render(request, f'dashboards/{template}', context)


def track_graph_track(request, index):
    """Generate and display a time-series production graph for a single machine during the shift.

    This view:
    1. Sets a human-readable description in `session['track_track']`.
    2. Looks up the machine’s rate and part family (`prt`) from a hard-coded list based on `index`.
    3. Computes the effective per-second production rate from the 8-hour target.
    4. Stores the machine asset in several session keys (`asset1_area`, etc.).
    5. Determines the current shift window using `session['shift_start']` and a fixed 8-hour duration.
    6. Calls `track_data(request, end_time, start_time, prt, rate)` to retrieve the graph points.
    7. Renders the `"dashboards/graph_track_track.html"` template with the context key `'GList'`.

    Args:
        request (HttpRequest): The incoming HTTP request, which must include
            `session['shift_start']` (Unix timestamp for shift start).
        index (str): The machine identifier to track (used to select rate and part).

    Returns:
        HttpResponse: Renders the graph template with context `{'GList': gr_list}`.
    """
    prt = '50-9341'
    request.session['track_track'] = 'Shift Track for Machine ' + str(index)

    mr7 = [
        # mainline
        ('1504', 8, '50-9341'), ('1506', 8, '50-9341'), ('1519',
                                                         8, '50-9341'), ('1520', 8, '50-9341'),  # Op10/20
        ('1502', 4, '50-9341'), ('1507', 4, '50-9341'),  # op30
        ('1501', 4, '50-9341'), ('1515', 4, '50-9341'),  # op40
        ('1508', 3, '50-9341'), ('1532', 3, '50-9341'),  # op50
        ('1509', 2, '50-9341'),  # op60
        ('1514', 2, '50-9341'),  # op70
        ('1510', 2, '50-9341'),  # op80
        ('1513', 2, '50-9341'),  # op90
        ('1503', 2, '50-9341'),  # op100
        ('1511', 2, '50-9341'),  # op110
        # offline
        ('1518', 8, '50-9341'), ('1521', 8, '50-9341'), ('1522',
                                                         8, '50-9341'), ('1523', 8, '50-9341'),  # Op10/20
        ('1539', 4, '50-9341'), ('1540', 4, '50-9341'),  # Op30
        ('1524', 4, '50-9341'), ('1525', 4, '50-9341'),  # Op40
        ('1538', 3, '50-9341'),  # Op50
        ('1541', 2, '50-9341'),  # Op60
        ('1531', 2, '50-9341'),  # Op70
        ('1527', 2, '50-9341'),  # Op80
        ('1530', 2, '50-9341'),  # Op100
        ('1528', 2, '50-9341'),  # Op110
        ('1533', 1, '50-9341'),  # Final
        ('1800', 2, '50-0455'), ('1801', 2,
                                 '50-0455'), ('1802', 2, '50-0455'),  # Op10/20
        ('1529', 4, '50-0455'), ('1543', 4, '50-0455'), ('776',
                                                         4, '50-0455'), ('1824', 4, '50-0455'),  # Op30
        ('1804', 2, '50-0455'), ('1805', 2, '50-0455'),  # Op40
        ('1806', 1, '50-0455'),  # Op50
        ('1808', 1, '50-0455'),  # Op60
        ('1810', 1, '50-0455'),  # Op70
        ('1815', 1, '50-0455'),  # Op80
        ('1542', 1, '50-0455'),  # Op90
        ('1812', 1, '50-0455'),  # Op100
        ('1813', 1, '50-0455'),  # Op110
        ('1816', 1, '50-0455'),  # Final
    ]


    for i in mr7:
        if i[0] == index:
            rate = i[1]
            prt = i[2]
    rate2 = 3200 / rate
    rate = rate2 / 8

    request.session['asset1_area'] = index
    request.session['asset2_area'] = index
    request.session['asset3_area'] = index
    request.session['asset4_area'] = index

    u = int(request.session['shift_start'])
    t = int(u) + 28800
    t = int(time.time())

    gr_list = track_data(request, t, u, prt, rate)  # Get the Graph Data
    return render(request, "dashboards/graph_track_track.html", {'GList': gr_list})


def track_data(request, shift_end, shift_start, part, rate):
    m = '1533'
    asset1 = request.session['asset1_area']
    asset2 = request.session['asset2_area']
    asset3 = request.session['asset3_area']
    asset4 = request.session['asset4_area']
    mrr = (rate*(28800))/float(28800)
    cursor = connections['prodrpt-md'].cursor()
    sql = f'SELECT * FROM GFxPRoduction'
    sql += f' where TimeStamp >= {shift_start} and TimeStamp< {shift_end} and part = "{part}"'
    sql += f' and Machine IN ("{asset1}","{asset2}","{asset3}","{asset4}")'
    cursor.execute(sql)
    result = cursor.fetchall()
    gr_list, brk1, brk2, multiplier = Graph_Data(
        shift_end, shift_start, m, result, mrr)
    return gr_list


def Graph_Data(t, u, machine, tmp, multiplier):
    # global tst
    cc = 0
    cr = 0
    cm = 0
    # last_by used for comparison
    last_by = 0
    temp_ctr = 0
    brk1 = 0
    brk2 = 0
    multiplier = multiplier / float(6)
    tm_sh = int((t-u)/600)
    px = [0 for x in range(tm_sh)]
    pp = [0 for x in range(tm_sh)]
    by = [0 for x in range(tm_sh)]
    ay = [0 for x in range(tm_sh)]
    cy = [0 for x in range(tm_sh)]
    for ab in range(0, tm_sh):
        temp_u = u + (cc*600)
        u_time = stamp_pdate4(temp_u)

        pp[ab] = u_time
        pp[ab] = u
        px[ab] = u + (cc*600)

        yy = px[ab]
        cc = cc + 1
        cr = cr + multiplier
        cm = cr * .8
        tst = []

        a = []
        ctr = 0
        for i in tmp:
            ctr = ctr+1
            a.append(i[4])

        op4 = list(filter(lambda c: c[4] < yy, tmp))
        by[ab] = len(op4)

        ay[ab] = int(cr)
        cy[ab] = int(cm)

    tm_sh = tm_sh - 1

    gr_list = list(zip(px, by, ay, cy, pp))

    return gr_list, brk1, brk2, multiplier


def stamp_pdate4(stamp):
    """Format a Unix timestamp into a zero-padded 'HH:MM' time string.

    Converts the given Unix timestamp to local time and returns the hour and
    minute, each left-padded with a '0' if necessary, in the format 'HH:MM'.

    Args:
        stamp (int): Unix timestamp (seconds since epoch).

    Returns:
        str: Local time formatted as 'HH:MM'.
    """
    tm = time.localtime(stamp)
    ma = ''
    da = ''
    ha = ''
    mia = ''
    if tm[1] < 10:
        ma = '0'
    if tm[2] < 10:
        da = '0'
    if tm[3] < 10:
        ha = '0'
    if tm[4] < 10:
        mia = '0'
    y1 = str(tm[0])
    m1 = str(tm[1])
    d1 = str(tm[2])
    h1 = str(tm[3])
    mi1 = str(tm[4])

    pdate = y1 + '-' + (ma + m1) + '-' + (da + d1) + \
        ' ' + (ha + h1) + ':' + (mia + mi1)
    pdate = (ha + h1) + ':' + (mia + mi1)

    return pdate


#################################################################################


##############################  Shift Points  ###################################


##################################################################################



# shift_points view
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Max, F
from .models import ShiftPoint

@login_required(login_url="login")
def list_and_update_shift_points(request):
    """Display, add, update, or delete ShiftPoint entries based on TV number selection.

    **GET**:
        - Renders a list of all `ShiftPoint` objects.
        - If `tv_number` is provided in the query string, highlights the selected entry.
    
    **POST**:
        - **add_tv**:  
          Creates a new `ShiftPoint` with default points, assigning the next available `tv_number`,  
          then redirects to select the newly created entry.
        - **update_tv**:  
          Updates the `points` list of the specified `ShiftPoint` (by `update_tv_number`),  
          saving any changes and redirecting with a confirmation flag.
        - **delete_tv**:  
          Deletes the specified `ShiftPoint`, then decrements the `tv_number` of all subsequent entries  
          to maintain a continuous sequence, and redirects back to the list view.

    Args:
        request (HttpRequest): Incoming request, optionally containing:
            - `GET['tv_number']`: TV number of the entry to select.
            - `POST['add_tv']`, `POST['update_tv_number']`, or `POST['delete_tv_number']`.

    Returns:
        HttpResponse: Renders `dashboards/list_and_update_shift_points.html` with context:
            - `shift_points`: all `ShiftPoint` objects.
            - `selected_shift_point`: the currently selected entry (if any).
            - `selected_tv_number`: the selected TV number.
            - `new_tv_number`: the number assigned to a newly created entry (if added).
    """
    selected_tv_number = request.GET.get('tv_number')
    shift_points = ShiftPoint.objects.all()
    selected_shift_point = None
    new_tv_number = None

    if selected_tv_number:
        selected_shift_point = get_object_or_404(ShiftPoint, tv_number=selected_tv_number)

    if request.method == 'POST':
        if 'add_tv' in request.POST:
            points = [
                "This is shift point 1.",
                "This is shift point 2.",
                "This is shift point 3.",
                "This is shift point 4."
            ]  # Default points

            # Find the max tv_number in the database
            max_tv_number = ShiftPoint.objects.aggregate(Max('tv_number'))['tv_number__max']
            if max_tv_number is None:
                max_tv_number = 0  # Handle case where there are no existing entries
            new_tv_number = max_tv_number + 1

            ShiftPoint.objects.create(tv_number=new_tv_number, points=points)
            return redirect(f'{request.path}?tv_number={new_tv_number}')

        elif 'update_tv' in request.POST:
            tv_number = request.POST.get('update_tv_number')
            shift_point = get_object_or_404(ShiftPoint, tv_number=tv_number)
            points = request.POST.getlist('point')
            if points == ['']:  # Handle case where all points are removed
                points = []
            shift_point.points = points
            shift_point.save()
            return redirect(f"{request.path}?tv_number={tv_number}&changes_saved=true")

        elif 'delete_tv' in request.POST:
            tv_number = int(request.POST.get('delete_tv_number'))
            shift_point = get_object_or_404(ShiftPoint, tv_number=tv_number)
            shift_point.delete()
            
            # Decrement tv_number of subsequent TVs
            ShiftPoint.objects.filter(tv_number__gt=tv_number).update(tv_number=F('tv_number') - 1)
            return redirect('dashboards:list_and_update_shift_points')

    return render(request, 'dashboards/list_and_update_shift_points.html', {
        'shift_points': shift_points,
        'selected_shift_point': selected_shift_point,
        'selected_tv_number': selected_tv_number,
        'new_tv_number': new_tv_number,
    })



def display_shift_points(request, tv_number):
    """Render the list of shift points for a specific TV number.

    Retrieves the `ShiftPoint` instance matching the provided `tv_number`, extracts its
    `points` list, and renders the `display_shift_points.html` template with both the
    model instance and the list of points.

    Args:
        request (HttpRequest): The incoming HTTP request.
        tv_number (int): The TV number identifying which `ShiftPoint` to display.

    Returns:
        HttpResponse: Renders `dashboards/display_shift_points.html` with context:
            - `shift_point`: the `ShiftPoint` instance
            - `shift_points`: list of strings representing the shift points
    """
    shift_point = get_object_or_404(ShiftPoint, tv_number=tv_number)
    shift_points = shift_point.points
    return render(request, 'dashboards/display_shift_points.html', {'shift_point': shift_point, 'shift_points': shift_points})









# ==============================================================
# ==============================================================
# ==================== Rejects Dashboard =======================
# ==============================================================
# ==============================================================


# define your line→machines map
LINE_TO_MACHINES = {
    "10R80": ["1508", "1532", "1538"],
    # add more lines here...
}


def get_db_connection():
    """Establish and return a MySQL database connection using configured settings.

    Reads the hostname, username, password, and database name from Django settings
    (`NEW_HOST`, `DAVE_USER`, `DAVE_PASSWORD`, `DAVE_DB`) and opens a connection
    via MySQLdb.

    Returns:
        MySQLdb.connections.Connection: A new MySQL database connection.

    Raises:
        MySQLdb.Error: If the connection cannot be established.
    """
    return MySQLdb.connect(
        host=settings.NEW_HOST,
        user=settings.DAVE_USER,
        passwd=settings.DAVE_PASSWORD,
        db=settings.DAVE_DB
    )


def fetch_pie_chart_data(machine):
    """Retrieve 24-hour production and reject counts with percentage breakdown and color coding.

    Connects to the GFxPRoduction table to count “good” and “reject” entries for the given
    machine (and its “REJ” suffix) over the last 24 hours. Computes the overall total,
    the percentage share of each category, and chooses a Bootstrap text color class
    based on the reject rate.

    Args:
        machine (str): Identifier of the machine whose production to analyze.

    Returns:
        dict: {
            "total" (int): Sum of good + reject counts,
            "grades" (dict[str, int]): {"Good": good_count, "Reject": reject_count},
            "percentages" (dict[str, float]): {"Good": good_pct, "Reject": reject_pct},
            "failures_total" (int): Same as reject_count,
            "reject_color" (str): Bootstrap text class based on reject_pct
                ("text-success" if <2.5%, "text-warning" if <5%, else "text-danger")
        }
    """
    now = datetime.now()
    cutoff = now.timestamp() - 24 * 3600
    conn = get_db_connection()

    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM GFxPRoduction "
            "WHERE Machine = %s AND TimeStamp >= %s",
            [machine, cutoff]
        )
        good = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM GFxPRoduction "
            "WHERE Machine = %s AND TimeStamp >= %s",
            [f"{machine}REJ", cutoff]
        )
        rejects = cursor.fetchone()[0]

    total = good + rejects
    # avoid divide‐by‐zero
    pct_good   = round((good   / total * 100), 2) if total else 0.0
    pct_reject = round((rejects/ total * 100), 2) if total else 0.0


    # ←— NEW: pick the right bootstrap class by percentage
    if pct_reject < 2.5:
        reject_color = "text-success"
    elif pct_reject < 5.0:
        reject_color = "text-warning"
    else:
        reject_color = "text-danger"

    return {
        "total": total,
        "grades": {
            "Good": good,
            "Reject": rejects,
        },
        "percentages": {
            "Good": pct_good,
            "Reject": pct_reject,
        },
        "failures_total": rejects,
        # ←— NEW FIELD your frontend will just apply
        "reject_color": reject_color,
    }



def fetch_weekly_data_for_machine(machine):
    """Retrieve 7-day production and reject statistics for a machine in 8-hour intervals.

    This function:
      1. Defines the start of the 7-day window (midnight 7 days ago).
      2. Iterates over each day and 8-hour block (00:00–08:00, 08:00–16:00, 16:00–24:00),
         skipping any blocks that start in the future.
      3. For each block, queries the GFxPRoduction table for both the machine’s “good”
         records and its rejects (machine identifier suffixed with "REJ").
      4. Builds a `breakdown` list of dictionaries containing:
         - `"interval_start"`: formatted block start time
         - `"interval_end"`: formatted block end time
         - `"total_count"`: sum of good + rejects
         - `"grade_counts"`: nested dict with `"Good"` and `"Reject"` each as
            `"count (percentage%)"`
      5. Rolls up totals across all blocks to compute:
         - `total_count_last_7_days`
         - `grade_counts_last_7_days` with formatted `"count (percentage%)"` per category

    Args:
        machine (str): Identifier of the machine to analyze.

    Returns:
        dict: {
            "asset": machine,
            "total_count_last_7_days": int,
            "grade_counts_last_7_days": {
                "Good": "count (pct%)",
                "Reject": "count (pct%)"
            },
            "breakdown_data": list of {
                "interval_start": str,
                "interval_end": str,
                "total_count": int,
                "grade_counts": {"Good": str, "Reject": str}
            }
        }
    """
    now = datetime.now()
    start_dt = (now - timedelta(days=7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    interval_hours = [0, 8, 16]
    breakdown = []
    conn = get_db_connection()

    with conn.cursor() as cursor:
        for day in range(8):  # 7 days + today
            day_base = start_dt + timedelta(days=day)
            for h in interval_hours:
                block_start = day_base + timedelta(hours=h)
                block_end   = block_start + timedelta(hours=8)
                if block_start >= now:
                    continue

                s_ts = block_start.timestamp()
                e_ts = block_end.timestamp()

                # good
                cursor.execute(
                    "SELECT COUNT(*) FROM GFxPRoduction "
                    "WHERE Machine = %s AND TimeStamp >= %s AND TimeStamp < %s",
                    [machine, s_ts, e_ts]
                )
                good_cnt = cursor.fetchone()[0]

                # reject
                cursor.execute(
                    "SELECT COUNT(*) FROM GFxPRoduction "
                    "WHERE Machine = %s AND TimeStamp >= %s AND TimeStamp < %s",
                    [f"{machine}REJ", s_ts, e_ts]
                )
                rej_cnt = cursor.fetchone()[0]

                total = good_cnt + rej_cnt
                if total == 0:
                    continue

                breakdown.append({
                    "interval_start": block_start.strftime("%b-%d %H:%M"),
                    "interval_end":   block_end.strftime("%b-%d %H:%M"),
                    "total_count":    total,
                    "grade_counts": {
                        "Good":  f"{good_cnt} ({round(good_cnt/total*100,2)}%)",
                        "Reject": f"{rej_cnt} ({round(rej_cnt/total*100,2)}%)",
                    }
                })

    # roll-up for the 7-day totals
    total_count = sum(item["total_count"] for item in breakdown)
    total_good   = sum(int(item["grade_counts"]["Good"].split()[0]) for item in breakdown)
    total_rej    = sum(int(item["grade_counts"]["Reject"].split()[0]) for item in breakdown)

    pct_good = round((total_good   / total_count * 100), 2) if total_count else 0
    pct_rej  = round((total_rej    / total_count * 100), 2) if total_count else 0

    return {
        "asset": machine,
        "total_count_last_7_days": total_count,
        "grade_counts_last_7_days": {
            "Good":  f"{total_good} ({pct_good}%)",
            "Reject": f"{total_rej} ({pct_rej}%)",
        },
        "breakdown_data": breakdown,
    }


def rejects_dashboard(request, line):
    """Display a rejects‐focused dashboard for a specified production line.

    Looks up the list of machine identifiers for the given `line` from `LINE_TO_MACHINES`,
    then for each machine:
      1. Fetches weekly production and reject breakdown via `fetch_weekly_data_for_machine()`.
      2. Fetches 24-hour pie chart data via `fetch_pie_chart_data()`.
      3. Embeds the pie data into the weekly stats.

    The aggregated data is JSON-encoded and passed to the `"dashboards/rejects_dashboard.html"` template.

    Args:
        request (HttpRequest): The incoming HTTP request.
        line (str): Key identifying the production line (e.g. `"10R80"`).

    Returns:
        HttpResponse: Renders the rejects dashboard template with context:
            `{"json_data": <pretty-printed JSON of per-machine stats>}`.

    Raises:
        Http404: If `line` is not defined in `LINE_TO_MACHINES`.
    """
    """
    Renders the dashboard for a given line (e.g. 10R80),
    which internally shows machines defined in LINE_TO_MACHINES[line].
    """
    machines = LINE_TO_MACHINES.get(line)
    if not machines:
        raise Http404(f"Unknown line: {line}")

    data = {}
    for m in machines:
        weekly = fetch_weekly_data_for_machine(m)
        pie    = fetch_pie_chart_data(m)
        weekly["pie_chart_data"] = pie
        data[m] = weekly

    return render(
        request,
        "dashboards/rejects_dashboard.html",
        {"json_data": json.dumps(data, indent=4)}
    )


def rejects_dashboard_finder(request):
    """Render a line‐selection page or redirect to the rejects dashboard for that line.

    On **GET**:
      - Displays a list of available production lines (keys of `LINE_TO_MACHINES`) 
        via the `"dashboards/rejects_dashboard_finder.html"` template.

    On **POST**:
      - Reads the selected `line` from `request.POST`.
      - If valid, redirects to the `rejects_dashboard_by_line` view, passing `line` as a URL argument.

    Args:
        request (HttpRequest): The incoming HTTP request, which on POST should include
            a `"line"` form field matching one of the available lines.

    Returns:
        HttpResponse: 
          - On GET, renders the finder template with context `{"lines": lines}`.
          - On valid POST, returns an `HttpResponseRedirect` to the line’s rejects dashboard.
    """
    lines = list(LINE_TO_MACHINES.keys())   # ["10R80", "AB1V", …]
    if request.method == "POST":
        chosen = request.POST.get("line")
        if chosen in lines:
            return redirect("rejects_dashboard_by_line", line=chosen)
    return render(request,
                  "dashboards/rejects_dashboard_finder.html",
                  {"lines": lines})















# ===================================================================
# ===================================================================
# ======== New function to fetch targets and then return oee ========
# ===================================================================
# ===================================================================

# ——— EDIT THIS: list machine IDs here that need part_list targets ———
machines_requiring_part_list = [
        # e.g. '1723', '1504', ...
        '1723', '1724', '581', '788',
    ]

def log_shift_times(shift_start, shift_time, actual_counts, part_list):
    """Calculate per-machine completion percentages against shift targets.

    Converts the shift start timestamp to local datetime, computes elapsed time,
    and for each machine in `actual_counts`, retrieves its raw shift target via
    `get_machine_target()`. If `part_list` is provided and the machine requires it,
    uses the raw target directly; otherwise scales the target by elapsed time
    over an 8-hour shift. Returns each machine’s actual count as a percentage
    of its target or "N/A" if no valid target exists.

    Args:
        shift_start (int): Unix timestamp marking the beginning of the shift.
        shift_time (int): Seconds elapsed since `shift_start`.
        actual_counts (list[tuple[str, int]]): List of `(machine_id, count)` pairs.
        part_list (list[str] | None): List of part numbers for machines that need
            a part-specific target lookup; use `None` if not applicable.

    Returns:
        list[tuple[str, int | str]]: For each machine, a tuple of
        `(machine_id, percentage)` where `percentage` is an integer
        percent of target completion or `"N/A"` if no target was found.
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo



    # ————————————————————————————————————————————————————————————————

    est = ZoneInfo("America/New_York")
    start_dt = datetime.fromtimestamp(shift_start, tz=est)
    elapsed = timedelta(seconds=shift_time)

    total_actual = sum(count for _, count in actual_counts)
    minutes_elapsed = shift_time / 60.0

    # Prepare new list to hold (machine, pct_or_NA)
    swapped_counts = []

    for machine, count in actual_counts:
        # decide whether to pass part_list into the target lookup
        if part_list and machine in machines_requiring_part_list:
            raw_target = get_machine_target(machine, shift_start, part_list) or 0
            
        else:
            raw_target = get_machine_target(machine, shift_start) or 0


        if part_list and machine in machines_requiring_part_list:
            # compute pct only if we had a real target; otherwise N/A
            if raw_target > 0:
                pct = int(count / raw_target * 100)
            else:
                pct = "N/A"
        else:
            # adjust for shift duration
            adjusted_target = raw_target * (minutes_elapsed / 7200.0)

            # compute pct only if we had a real target; otherwise N/A
            if adjusted_target > 0:
                pct = int(count / adjusted_target * 100)
            else:
                pct = "N/A"


        # swap out the count for the pct or "N/A"
        swapped_counts.append((machine, pct))

    return swapped_counts



MACHINE_TARGET_ALIASES = {
    '733': ['1701L', '1701R'],
    '1746': ['1746R'],
    '1705': ['1746R']
    # Add more as needed  cursor = connections['prodrpt-md'].cursor()
}

def get_machine_target(machine_id, shift_start_unix, part_list=None):
    """
    Returns the most recent non-deleted target for a given machine (or its alias group),
    optionally filtered by part_list, at or before the shift start.
    Tries the machine_id directly, or strips trailing letter, or sums targets from aliases.

    If part_list is provided, prints run‐minutes + scaled targets per part and a summary,
    then returns the truncated int “smart total” instead of the normal target.
    """
    cursor = connections['prodrpt-md'].cursor()

    def query_target(mid):
        qs = (
            OAMachineTargets.objects
            .filter(
                machine_id=mid,
                isDeleted=False,
                effective_date_unix__lte=shift_start_unix
            )
        )
        if part_list:
            qs = qs.filter(part__in=part_list)
        return qs.order_by('-effective_date_unix').first()

    def _compute_and_print_smart_total(mid):
        # only runs when part_list is provided
        start_ts = shift_start_unix
        end_ts   = time.time()

        # fetch ordered events for this machine & those parts
        placeholder = ", ".join(["%s"] * len(part_list))
        sql = f"""
            SELECT TimeStamp, Part
              FROM GFxPRoduction
             WHERE Machine   = %s
               AND TimeStamp >= %s
               AND TimeStamp <  %s
               AND Part IN ({placeholder})
             ORDER BY TimeStamp ASC
        """
        params = [mid, start_ts, end_ts] + part_list
        cursor.execute(sql, params)
        rows = cursor.fetchall()

        # accumulate run‐seconds per part
        totals = {p: 0.0 for p in part_list}
        if rows:
            current_part = rows[0][1]
            run_start    = rows[0][0]
            for ts, part in rows[1:]:
                if part != current_part:
                    totals[current_part] += (ts - run_start)
                    current_part = part
                    run_start    = ts
            totals[current_part] += (end_ts - run_start)

        # compute & print per‐part plus sum up the smart total
        total_smart = 0.0
        for part, sec in totals.items():
            mins = int(sec // 60)

            part_obj = (
                OAMachineTargets.objects
                .filter(
                    machine_id=mid,
                    part=part,
                    isDeleted=False,
                    effective_date_unix__lte=shift_start_unix
                )
                .order_by('-effective_date_unix')
                .first()
            )

            if part_obj and part_obj.target is not None:
                # target is pieces per 7,200 min; rate per min = target/7200
                scaled = (part_obj.target / 7200.0) * mins
                total_smart += scaled
                # print(
                #     f"Machine {mid} ran part {part} for {mins} minutes since shift start; "
                #     f"target for that period is {scaled:.2f}"
                # )
            else:
                print(
                    f"Machine {mid} ran part {part} for {mins} minutes since shift start; "
                    f"no target found for this part"
                )

        # summary line
        # print(
        #     f"So since shift start the total target across the part list for this machine is "
        #     f"{int(total_smart)}"
        # )

        return int(total_smart)


    # —— original lookup logic follows —— #

    # Case 1: use machine_id directly
    result = query_target(machine_id)
    if result:
        if part_list:
            return _compute_and_print_smart_total(machine_id)
        return result.target

    # Case 2: strip trailing letter if needed
    if machine_id and machine_id[-1].isalpha():
        fallback_id     = machine_id[:-1]
        fallback_result = query_target(fallback_id)
        if fallback_result:
            if part_list:
                return _compute_and_print_smart_total(fallback_id)
            return fallback_result.target

    # Case 3: sum aliases
    if machine_id in MACHINE_TARGET_ALIASES:
        # if parts → sum each alias’s smart total
        if part_list:
            group_total = 0
            for aliased_id in MACHINE_TARGET_ALIASES[machine_id]:
                group_total += _compute_and_print_smart_total(aliased_id)
            return group_total

        # otherwise original target‐sum logic
        total = 0
        for aliased_id in MACHINE_TARGET_ALIASES[machine_id]:
            aliased_result = query_target(aliased_id)
            if aliased_result:
                total += aliased_result.target
        return total if total > 0 else None

    return None




from collections import defaultdict

def compute_op_actual_and_oee(line_spec,
                              machine_production,
                              shift_start,
                              shift_time,
                              part_list=None):
    """
    Returns two lists:
      op_actual_list[i] = total actual for OP i
      op_oee_list[i]    = int OEE% (or "N/A") for OP i

    Only for machines in machines_requiring_part_list will we call
      get_machine_target(asset, shift_start, part_list)
    and treat its return as the period target.
    All others get the weekly target scaled by shift_time/7200.
    """
    minutes_elapsed = shift_time / 60.0
    factor          = minutes_elapsed / 7200.0

    # map asset → OP
    asset2op = {asset: op for asset, *_, op in line_spec}

    # accumulators
    op_actual   = defaultdict(int)
    op_adjusted = defaultdict(float)

    for asset, actual_count, *_ in machine_production:
        op = asset2op.get(asset)
        if op is None:
            continue

        # choose per-machine target logic
        if part_list and asset in machines_requiring_part_list:
            # smart‐total for this exact period & parts
            period_target = get_machine_target(asset, shift_start, part_list) or 0
        else:
            # fall back to weekly target → scale for this shift
            weekly_target = get_machine_target(asset, shift_start) or 0
            period_target = weekly_target * factor

        # accumulate
        op_actual[op]   += actual_count
        op_adjusted[op] += period_target

    # build output lists
    max_op = max(op_actual.keys() | op_adjusted.keys(), default=-1)
    op_actual_list = [0] * (max_op + 1)
    op_oee_list    = [None] * (max_op + 1)

    for op, actual in op_actual.items():
        op_actual_list[op] = actual

    for op, adjusted in op_adjusted.items():
        if adjusted > 0:
            op_oee_list[op] = int(op_actual[op] / adjusted * 100)
        else:
            op_oee_list[op] = "N/A"

    return op_actual_list, op_oee_list


















# =================================================================
# =================================================================
# =================== Testing New Display =========================
# =================================================================
# =================================================================



PAGES = {
    "9341": {
        "dayshift_start": "06:00",
        "programs": [
            {
            "program": "10R80",
            "lines": [
                {
                    "line": "Mainline",
                    "scrap_line": "Mainline",
                    "operations": [
                        {
                            "op": "OP10",
                            "machines": [
                                {"number": "1504"},
                                {"number": "1506"},
                                {"number": "1519"},
                                {"number": "1520"},
                                {"number": "1518"},
                                {"number": "1521"},
                                {"number": "1522"},
                                {"number": "1523"},
                            ],
                        },
                        {
                            "op": "OP30",
                            "machines": [
                                {"number": "1502"},
                                {"number": "1507"},
                                {"number": "1539"},
                                {"number": "1540"},
                                {
                                "number": "1546",
                                "parts": ["50-9341"]
                                },
                            ],
                        },
                        {
                            "op": "OP40",
                            "machines": [
                                {"number": "1501"},
                                {"number": "1515"},
                                {"number": "1524"},
                                {"number": "1525"},
                                {
                                "number": "1547",
                                "parts": ["50-9341"]
                                },
                            ],
                        },
                        {
                            "op": "OP50",
                            "machines": [
                                {"number": "1508"},
                                {"number": "1532"},
                                {"number": "1538"},
                                {
                                "number": "1548",
                                "parts": ["50-9341"]
                                },
                            ],
                        },
                        {
                            "op": "OP60",
                            "machines": [
                                {"number": "1509"},
                                {"number": "1541"},
                                {
                                "number": "1549",
                                "parts": ["50-9341"]
                                }
                            ],
                        },
                        {
                            "op": "OP70",
                            "machines": [
                                {"number": "1514"},
                                {"number": "1531"},
                                {
                                "number": "594",
                                "parts": ["50-9341"]
                                }

                            ],
                        },
                        {
                            "op": "OP80",
                            "machines": [
                                {"number": "1510"},
                                {"number": "1527"},
                                {
                                "number": "1551",
                                "parts": ["50-9341"]
                                }

                            ],
                        },
                        {
                            "op": "OP90",
                            "machines": [
                                {"number": "1513"},
                                {
                                "number": "1552",
                                "parts": ["50-9341"]
                                }
                            ],
                        },
                        {
                            "op": "OP100",
                            "machines": [
                                {"number": "1503"},
                                {"number": "1530"},
                                {
                                "number": "751",
                                "parts": ["50-9341"]
                                }
                            ],
                        },
                        {
                            "op": "OP110",
                            "machines": [
                                {"number": "1511"},
                                {"number": "1528"},
                                {
                                "number": "1554",
                                "parts": ["50-9341"]
                                }
                            ],
                        },
                        {
                        "op": "Final",
                        "machines": [
                            {
                            "number": "1533",
                            "parts": ["50-9341"]
                            }
                        ]
                        },
                    ],
                }
            ],
        },

            {
                "program": "10R60",
                "lines": [
                    {
                        "line": "Mainline",
                        "scrap_line": "Mainline",
                        "operations": [
                            {
                                "op": "OP10",
                                "machines": [
                                    {"number": "1800"},
                                    {"number": "1801"},
                                    {"number": "1802"},
                                ],
                            },
                            {
                                "op": "OP30",
                                "machines": [
                                    {"number": "1529"},
                                    {"number": "776"},
                                    {"number": "1824"},
                                    {"number": "1543"},
                                ],
                            },
                            {
                                "op": "OP40",
                                "machines": [
                                    {"number": "1804"},
                                    {"number": "1805"},
                                ],
                            },
                            {
                                "op": "OP50",
                                "machines": [
                                    {"number": "1806"},
                                ],
                            },
                            {
                                "op": "OP60",
                                "machines": [
                                    {"number": "1808"},
                                ],
                            },
                            {
                                "op": "OP70",
                                "machines": [
                                    {"number": "1810"},
                                ],
                            },
                            {
                                "op": "OP80",
                                "machines": [
                                    {"number": "1815"},
                                ],
                            },
                            {
                                "op": "OP90",
                                "machines": [
                                    {"number": "1542"},
                                ],
                            },
                            {
                                "op": "OP100",
                                "machines": [
                                    {"number": "1812"},
                                ],
                            },
                            {
                                "op": "OP110",
                                "machines": [
                                    {"number": "1813"},
                                ],
                            },
                             {
                                "op": "Final",
                                "machines": [
                                    {"number": "1816"},
                                ],
                            },
                        ],
                    }
                ],
            },
        ],
    },
    "trilobe": {
        "dayshift_start": "07:00",
        "programs": [
            {
                "program": "Sinter",
                "lines": [
                    {
                        "line": "Sinter",
                        "scrap_line": "Sinter",
                        "operations": [
                            {
                            "op": "Compact",
                            "machines": [
                                {
                                "number": "262"
                                },
                                {
                                "number": "263",
                                "parts": ["compact"]
                                }
                            ]
                            },
                            {
                                "op": "Assemb",
                                "machines": [
                                    {"number": "859"},
                                ],
                            },
                            {
                                "op": "Unload",
                                "machines": [
                                    {"number": "992"},
                                ],
                            },
                        ],
                    }
                ],
            },
            {
                "program": "Optimized",
                "lines": [
                    {
                        "line": "Optimized",
                        "scrap_line": "Optimized",
                        "operations": [
                            {
                                "op": "Broach",
                                "machines": [
                                    {"number": "784"},
                                ],
                            },
                            {
                                "op": "Heat",
                                "machines": [
                                    {"number": "770"},
                                ],
                            },
                            {
                                "op": "Machine",
                                "machines": [
                                    {"number": "618"},
                                    {"number": "575"},
                                    {"number": "624"},
                                    {"number": "619"},
                                ],
                            },
                            {
                                "op": "Slurry",
                                "machines": [
                                    {"number": "769"},
                                ],
                            },
                        ],
                    }
                ],
            },
            {
                "program": "Trilobe",
                "lines": [
                    {
                        "line": "Trilobe",
                        "scrap_line": "Trilobe",
                        "operations": [
                            {
                                "op": "Broach",
                                "machines": [
                                    {"number": "573"},
                                ],
                            },
                            {
                                "op": "Heat",
                                "machines": [
                                    {"number": "728"},
                                ],
                            },
                            {
                                "op": "Machine",
                                "machines": [
                                    {"number": "644"},
                                    {"number": "645"},
                                    {"number": "646"},
                                    {"number": "647"},
                                    {"number": "649"},
                                ],
                            },
                            {
                                "op": "Slurry",
                                "machines": [
                                    {"number": "742"},
                                ],
                            },
                        ],
                    }
                ],
            },
            {
                "program": "Offline",
                "lines": [
                    {
                        "line": "Offline",
                        "scrap_line": "Offline",
                        "operations": [
                            {
                                "op": "Machine",
                                "machines": [
                                    {"number": "636"},
                                ],
                            },
                            {
                                "op": "Machine",
                                "machines": [
                                    {"number": "625"},
                                ],
                            },
                        ],
                    }
                ],
            },
        ],
    },
    "8670": {
        "dayshift_start": "07:00",
        "programs": [
            {
                "program": "AB1V Rx",
                "lines": [
                    {
                        "line": "AB1V Reaction",
                        "scrap_line": "AB1V Reaction",
                        "operations": [
                           {
                            "op": "OP10",
                            "machines": [
                                {
                                "number": "1703L",
                                "parts": ["50-8670", "50-0450"]
                                },
                                {
                                "number": "1704L",
                                "parts": ["50-8670", "50-0450"]
                                },
                                {
                                "number": "658",
                                "parts": ["50-8670", "50-0450"]
                                },
                                {
                                "number": "661",
                                "parts": ["50-8670", "50-0450"]
                                },
                                {
                                "number": "622",
                                "parts": ["50-8670", "50-0450"]
                                }
                            ]
                            },
                            {
                                "op": "OP20/30",
                                "machines": [
                                    {"number": "1703R"},
                                    {"number": "1704R"},
                                    {"number": "616"},
                                    {"number": "623"},
                                    {"number": "617"},
                                ],
                            },
                            {
                                "op": "OP40",
                                "machines": [
                                    {"number": "1727"},
                                ],
                            },
                            {
                                "op": "OP50",
                                "machines": [
                                    {"number": "659"},
                                    {"number": "626"},
                                ],
                            },
                            {
                                "op": "OP60",
                                "machines": [
                                    {"number": "1712"},
                                ],
                            },
                            {
                                "op": "OP70",
                                "machines": [
                                    {"number": "1716L"},
                                ],
                            },
                            {
                                "op": "OP80",
                                "machines": [
                                {
                                "number": "1719",
                                "parts": ["50-8670", "50-0450"]
                                }
                                ],
                            },
                            {
                            "op": "OP90",
                            "machines": [
                                {
                                "number": "1723",
                                "parts": [
                                    "50-0450",
                                    "50-8670"
                                ]
                                }
                            ]
                            },
                            {
                                "op": "Laser",
                                "machines": [
                                {
                                "number": "1724",
                                "parts": [
                                    "50-0450",
                                    "50-8670"
                                ]
                                },
                                {
                                "number": "1750",
                                "parts": [
                                    "50-0450",
                                    "50-8670"
                                ]
                                },
                                ],
                            },
                        ],
                    }
                ],
            },
            {
                "program": "AB1V Overdrive",
                "lines": [
                    {
                        "line": "AB1V Overdrive",
                        "scrap_line": "AB1V Overdrive",
                        "operations": [
                            {
                                "op": "OP20",
                                "machines": [
                                    {"number": "1705"},
                                    {"number": "1746"},
                                ],
                            },
                            {
                                "op": "OP25",
                                "machines": [
                                    {"number": "621"},
                                    {"number": "629"},
                                ],
                            },
                            {
                                "op": "OP30",
                                "machines": [
                                    {"number": "785"},
                                    {"number": "1748"},
                                    {"number": "1718"},
                                ],
                            },
                            {
                                "op": "OP35",
                                "machines": [
                                    {"number": "669"},
                                ],
                            },
                            {
                                "op": "OP40",
                                "machines": [
                                    {"number": "1726"},
                                ],
                            },
                            {
                                "op": "OP50",
                                "machines": [
                                    {"number": "1722"},
                                ],
                            },
                            {
                                "op": "OP60",
                                "machines": [
                                    {"number": "1713"},
                                ],
                            },
                            {
                                "op": "OP70",
                                "machines": [
                                    {"number": "1716R"},
                                ],
                            },
                            {
                                "op": "OP80",
                                "machines": [
                                      {
                                "number": "1719",
                                "parts": [
                                    "50-0519",
                                    "50-5404"
                                ]
                                }
                                ],
                            },
                            {
                            "op": "OP90",
                            "machines": [
                                {
                                "number": "1723",
                                "parts": [
                                    "50-0519",
                                    "50-5404"
                                ]
                                }
                            ]
                            },
                            {
                                "op": "Laser",
                                "machines": [
                                {
                                "number": "1724",
                                "parts": [
                                    "50-0519",
                                    "50-5404"
                                ]
                                },
                                {
                                "number": "1750",
                                "parts": [
                                    "50-0519",
                                    "50-5404"
                                ]
                                },
                                ],
                            },
                        ],
                    }
                ],
            },
            {
                "program": "AB1V Input",
                "lines": [
                    {
                        "line": "AB1V Input",
                        "scrap_line": "AB1V Input",
                        "operations": [
                            {
                                "op": "OP10",
                                "machines": [
                                    {"number": "1740L"},
                                    {"number": "1740R"},
                                ],
                            },
                            {
                                "op": "OP40",
                                "machines": [
                                    {"number": "1701L"},
                                    {"number": "1701R"},
                                ],
                            },
                            {
                                "op": "OP50",
                                "machines": [
                                    {"number": "733"},
                                ],
                            },
                            {
                                "op": "OP60",
                                "machines": [
                                    {"number": "775"},
                                    {"number": "1702"},
                                ],
                            },
                            {
                                "op": "OP70",
                                "machines": [
                                    {
                                        "number": "581",
                                        "parts": ["50-0447", "50-5401"]
                                    },
                                    {
                                        "number": "788",
                                        "parts": ["50-0447", "50-5401"]
                                    },
                                ],
                            },
                            {
                                "op": "OP80",
                                "machines": [
                                    {"number": "1714"},
                                ],
                            },
                            {
                                "op": "OP90",
                                "machines": [
                                    {"number": "1717L"},
                                ],
                            },
                            {
                                "op": "OP100",
                                "machines": [
                                    {
                                    "number": "1706",
                                    "parts": [
                                        "50-0447",
                                        "50-5401"
                                    ]
                                    }
                                ],
                            },
                            {
                            "op": "OP110",
                            "machines": [
                                {
                                "number": "1723",
                                "parts": [
                                    "50-0447",
                                    "50-5401"
                                ]
                                }
                            ]
                            },
                            {
                                "op": "Laser",
                                "machines": [
                                    {
                                        "number": "1724",
                                        "parts": ["50-0447", "50-5401"]
                                    },
                                    {
                                        "number": "1750",
                                        "parts": ["50-0447", "50-5401"]
                                    },
                                ],
                            },
                        ],
                    }
                ],
            },
            {
                "program": "10R140 Rear",
                "lines": [
                    {
                        "line": "10R140 Rear",
                        "scrap_line": "10R140 Rear",
                        "operations": [
                            {
                                "op": "OP10",
                                "machines": [
                                    {"number": "1708L"},
                                    {"number": "1708R"},
                                ],
                            },
                            {
                                "op": "OP20",
                                "machines": [
                                    {"number": "1709"},
                                ],
                            },
                            {
                                "op": "OP30",
                                "machines": [
                                    {"number": "1710"},
                                ],
                            },
                            {
                                "op": "OP40",
                                "machines": [
                                    {"number": "1711"},
                                ],
                            },
                            {
                                "op": "OP50",
                                "machines": [
                                    {"number": "1715"},
                                ],
                            },
                            {
                                "op": "OP60",
                                "machines": [
                                    {"number": "1717R"},
                                ],
                            },
                            {
                                "op": "OP70",
                                "machines": [
                                    {
                                "number": "1706",
                                "parts": [
                                    "50-5214",
                                    "50-3214"
                                    ]
                                    }
                                ],
                            },
                            {
                                "op": "OP80",
                                "machines": [
                                    {"number": "1720"},
                                ],
                            },
                            {
                                "op": "OP90",
                                "machines": [
                                    {"number": "677"},
                                    {"number": "748"},
                                ],
                            },
                            {
                            "op": "OP100",
                            "machines": [
                                {
                                "number": "1723",
                                "parts": [
                                    "50-5214",
                                    "50-3214"
                                ]
                                }
                            ]
                            },
                            {
                                "op": "Laser",
                                "machines": [
                                {
                                "number": "1725",
                                "parts": [
                                    "50-5214",
                                    "50-3214"
                                ]
                                }
                                ],
                            },
                        ],
                    }
                ],
            },
        ],
    },
    "Area2": {
        "dayshift_start": "07:00",
        "programs": [
            {
                "program": "Area 2",
                "lines": [
                    {
                        "line": "Area 2 Presses",
                        "scrap_line": "Presses",
                        "operations": [
                            {
                                "op": "compact",
                                "machines": [
                                { "number": "272" }
                                ]
                            },
                            {
                                "op": "compact",
                                "machines": [
                                { "number": "273" }
                                ]
                            },
                            {
                                "op": "compact",
                                "machines": [
                                { "number": "277" }
                                ]
                            },
                            {
                                "op": "compact",
                                "machines": [
                                { "number": "278" }
                                ]
                            },
                        ],
                    },
                    {
                        "line": "Area 2 Furnaces",
                        "scrap_line": "Furances",
                        "operations": [
                            {
                            "op": "sinter",
                            "machines": [
                                {
                                "number": "344",
                                "parts": [
                                    "50-5404",
                                    "50-3214",
                                    "50-0447",
                                    "50-5214",
                                    "50-9341",
                                    "50-0519",
                                    "50-5401"
                                ]
                                },
                                {
                                "number": "345",
                                "parts": [
                                    "50-5404",
                                    "50-3214",
                                    "50-0447",
                                    "50-5214",
                                    "50-9341",
                                    "50-0519",
                                    "50-5401"
                                ]
                                }
                            ]
                            }
                        ],
                    },
                ],
            },
        ],
    },
    "Area1": {
        "dayshift_start": "07:00",
        "programs": [
            {
                "program": "Area 1",
                "lines": [
                    {
                        "line": "Area 1 Presses",
                        "scrap_line": "Presses",
                        "operations": [
                            {
                                "op": "compact",
                                "machines": [
                                { "number": "262" }
                                ]
                            },
                            {
                                "op": "compact",
                                "machines": [
                                { "number": "240" }
                                ]
                            },
                            {
                                "op": "compact",
                                "machines": [
                                { "number": "280" }
                                ]
                            },
                            {
                                "op": "compact",
                                "machines": [
                                { "number": "242" }
                                ]
                            },
                            {
                                "op": "compact",
                                "machines": [
                                { "number": "245" }
                                ]
                            },
                        ],
                    },
                    {
                        "line": "Area 1 Assemblers",
                        "scrap_line": "Assemblers",
                        "operations": [
                            {
                            "op": "assemble",
                            "machines": [
                                {
                                "number": "1516",
                                },
                            ]
                            },
                        ],
                    },
                    {
                        "line": "Area 1 Furnaces",
                        "scrap_line": "Furances",
                        "operations": [
                            {
                            "op": "sinter",
                            "machines": [
                                {
                                "number": "332",
                                "parts": [
                                    "50-3050",
                                    "50-1467",
                                ]
                                },
                                {
                                "number": "333",
                                "parts": [
                                    "50-3050",
                                    "50-1467",
                                ]
                                },
                                {
                                "number": "349",
                                "parts": [
                                    "50-9341",
                                ]
                                },
                            ]
                            }
                        ],
                    }
                ],
            },
            
        ],
    },
}




# ───────────────────────────────────────────────────────────────────────────────
# helpers
# ───────────────────────────────────────────────────────────────────────────────

_SECONDS_PER_WEEK_7200 = 7200 * 60  # 432 000


def get_cycle_time_seconds(
    machine_id: str,
    part: Optional[Union[str, List[str]]] = None,
    as_of_epoch: Optional[int] = None,
) -> Optional[float]:
    """Retrieve the cycle time (seconds per part) for a machine, optionally across multiple parts.

    If `part` is a list of part numbers, this function calls itself for each part and
    returns the maximum cycle time among them. Otherwise, it queries the
    `OAMachineTargets` model for the most recent target (by `effective_date_unix`)
    where `machine_id` matches and `effective_date_unix` is on or before `as_of_epoch`.

    For single-part lookups:
      - If `part` is provided, filters targets by that part.
      - If `part` is `None` or omitted, filters for entries where `part__isnull=True`.
      - Returns `None` if no valid target row is found or if `row.target <= 0`.
      - Otherwise computes `seconds = _SECONDS_PER_WEEK_7200 / row.target`.

    Debug prints can be enabled by uncommenting the `print` calls; e.g., for
    `machine_id == "1703L"`.

    Args:
        machine_id (str): Identifier of the machine to look up in `OAMachineTargets`.
        part (str | list[str], optional): A single part number or a list of parts.
            If a list, the max cycle time across those parts is returned.
        as_of_epoch (int, optional): Unix timestamp cutoff; only targets with
            `effective_date_unix <= as_of_epoch` are considered. Defaults to now.

    Returns:
        float | None: The cycle time in seconds (seconds per part), or `None` if
        no valid target is found.
    """
    """
    If `part` is a list of strings, return the *max* cycle time among those parts.
    Otherwise, behave exactly as before. Adds debug prints when machine_id == "1703L".
    """
    if as_of_epoch is None:
        as_of_epoch = int(timezone.now().timestamp())

    # If part is a list, compute each individually and take max
    if isinstance(part, list):

        cts = []
        for p in part:
            single_ct = get_cycle_time_seconds(machine_id, p, as_of_epoch)
            if single_ct is not None:
                cts.append(single_ct)

        if not cts:
            # print(f"NA: {machine_id} /{','.join(part)}")
            return None

        chosen = max(cts)
        return chosen

    # Single-part (or no-part) logic
    qs = (
        OAMachineTargets.objects
        .filter(machine_id=machine_id, isDeleted=False, effective_date_unix__lte=as_of_epoch)
    )
    if part:
        qs = qs.filter(part=part)
    else:
        qs = qs.filter(part__isnull=True)


    row = qs.order_by("-effective_date_unix").first()
    tag = f"{machine_id}{' /' + part if part else ''}"


    if not row or not row.target or row.target <= 0:
        # print(f"NA: {tag}")
        return None

    seconds = _SECONDS_PER_WEEK_7200 / row.target


    return seconds




def compute_part_durations_for_machine(
    machine_number: str,
    shift_start_epoch: int,
    shift_end_epoch: Optional[int] = None,
) -> List[Dict]:
    """
    Return a list of contiguous part‐runs for `machine_number` between the
    two epoch timestamps. Adds debug prints when machine_number == "1703L".
    Each element:
        {part, start_ts, end_ts, duration}
    """
    if shift_end_epoch is None:
        shift_end_epoch = int(timezone.now().timestamp())


    cursor = connections["prodrpt-md"].cursor()

    # ── what was running at shift start? ───────────────────────────────
    cursor.execute(
        """
        SELECT Part, TimeStamp
        FROM   GFxPRoduction
        WHERE  Machine   = %s
          AND  TimeStamp < %s
        ORDER  BY TimeStamp DESC
        LIMIT  1
        """,
        [machine_number, shift_start_epoch],
    )
    row = cursor.fetchone()
    initial_part, _ = row if row else (None, None)


    # ── all records inside the window ──────────────────────────────────
    cursor.execute(
        """
        SELECT Part, TimeStamp
        FROM   GFxPRoduction
        WHERE  Machine   = %s
          AND  TimeStamp BETWEEN %s AND %s
        ORDER  BY TimeStamp ASC
        """,
        [machine_number, shift_start_epoch, shift_end_epoch],
    )
    rows = cursor.fetchall()


    # ── walk through and segment contiguous runs ───────────────────────
    runs: List[Dict] = []
    current_part = None
    current_start = None

    if initial_part is not None:
        current_part, current_start = initial_part, shift_start_epoch

    for part, ts in rows:
        if current_part is None:
            current_part, current_start = part, max(shift_start_epoch, ts)
            continue

        if part == current_part:
            continue

        # part changed → close previous run
        duration = int(ts - current_start)
        runs.append({
            "part": current_part,
            "start_ts": current_start,
            "end_ts": ts,
            "duration": duration,
        })

        current_part, current_start = part, ts

    # whatever is still running at shift end
    if current_part is not None:
        final_duration = int(shift_end_epoch - current_start)
        runs.append({
            "part": current_part,
            "start_ts": current_start,
            "end_ts": shift_end_epoch,
            "duration": final_duration,
        })


    return runs



def efficiency_color(eff: int) -> str:
    """
    Given an efficiency percentage (0–100), return a hex color:
      •  0% → pure red   (#ff0000)
      • 50% → yellow     (#ffff00)
      •100% → forest‐green (#228b22)

    Below  0 or above 100 will be clamped.
    """
    # Clamp onto [0,100]
    if eff < 0:
        eff = 0
    elif eff > 100:
        eff = 100

    if eff <= 50:
        # Fade from red → yellow: keep R=255, increase G from 0→255
        r = 255
        g = int((eff / 50) * 255)
        b = 0
    else:
        # Fade from yellow → forest‐green
        #   At eff=50: (255,255,0)
        #   At eff=100: ( 34,139,34)  ← “forest green”
        proportion = (eff - 50) / 50.0
        # Linearly interpolate each channel:
        start_r, start_g, start_b = 255, 255, 0
        target_r, target_g, target_b = 34, 139, 34
        r = int(start_r + (target_r - start_r) * proportion)
        g = int(start_g + (target_g - start_g) * proportion)
        b = int(start_b + (target_b - start_b) * proportion)

    return f"#{r:02x}{g:02x}{b:02x}"



# ───────────────────────────────────────────────────────────────────────────────
# view itself
# ──────────────────────────────────────────────────────────────────────────────-


# Define alias‐to‐sources mapping (so that “733” is computed from machines “1701L” & “1701R”)
# Add more entries here in future if similar aliasing is needed.
ALIASES: Dict[str, List[str]] = {
    "733": ["1701L", "1701R"],
    "1709": ["1708L", "1708R"],
    "1516": ["1516C1", "1516C2"],
    "1542": ["1812"],
    "784": ["770"],
    "573": ["728"],
    "1705": ["1705L", "1705R"],
    "1746": ["1746L", "1746R"],
    "1516": ["1516C1", "1516C2"],
    # e.g. "XYZ": ["A", "B", "C"], 
}




def dashboard_current_shift(request, pages: str):
    """Render a live‐updating shift dashboard for one or two programs with efficiency coloring.

    Splits the `pages` argument on “&” to allow one or two program names (e.g. “programA” or
    “programA&programB”), validates against the `PAGES` configuration, and returns a
    400‐BadRequest if the format is invalid or if any program is unknown.

    For each requested program, this view:
      1. Determines the 8-hour shift boundaries in Eastern Time (day/afternoon/night)
         based on a program-specific base hour.
      2. Converts those boundaries to UTC timestamps for database queries.
      3. Builds a set of machines (including expanded sources for any aliases) and
         captures their part groupings.
      4. Runs two SQL aggregations against `GFxPRoduction` to get per-machine, per-part
         counts for the full shift and the last 5 minutes.
      5. Calls `compute_part_durations_for_machine` to fetch part run durations over both intervals.
      6. Annotates each “cell” in the program template with:
         - Cumulative and recent piece counts
         - Cycle time(s) and “smart” targets
         - Shift-long and 5-min efficiencies
         - A color code based on recent efficiency
      7. Constructs alias cells by summing metrics across their source machines, applying
         the same efficiency and coloring logic.
      8. Pads each operation line to a uniform width, filters part runs to declared parts,
         then computes per-operation totals and efficiencies (excluding machines with no target),
         adding a “recent_efficiency” and “color” for each operation.
      9. Collects all program objects into `all_programs`, then renders
         `dashboards/dashboard_renewed.html` with context:
         ```python
         {
             "pages": pages,
             "programs": all_programs
         }
         ```

    Args:
        request (HttpRequest): The incoming request, containing session and timezone context.
        pages (str): A single program name or two names joined by "&" indicating which
                     program dashboards to render.

    Returns:
        HttpResponse: Renders the renewed dashboard template with JSON-ready program data,
                      or returns HttpResponseBadRequest for invalid input.
    """
    """
    pages: either "programA" or "programA&programB"
    We split on "&", ensure 1 or 2 valid program names, run the annotation logic
    for each machine, and—when computing per-op totals—exclude any machines
    whose smart_target is None or zero so they don’t skew the efficiency.
    Now also computes a 5-minute “recent efficiency” at the operation level and
    colors the operation cell accordingly.  Machines like “733” can be aliased
    to sum the data from multiple source machines (e.g. “1701L” & “1701R”).
    """

    # ── 1) Split on "&" and validate count ──────────────────────────────────
    parts = [p.strip() for p in pages.split("&") if p.strip()]
    if len(parts) == 0 or len(parts) > 2:
        return HttpResponseBadRequest(
            {"error": f"Invalid URL segment '{pages}'.  Use /dashboard/foo/ or /dashboard/foo&bar/.  At most two programs allowed."},
            content_type="application/json",
        )

    # ── 2) Ensure each program name exists in PAGES ─────────────────────────
    for prog_name in parts:
        if prog_name not in PAGES:
            return HttpResponseBadRequest(
                {
                    "error": f"Unknown program '{prog_name}'. "
                             f"Valid programs are: {list(PAGES.keys())}"
                },
                content_type="application/json",
            )

    # ── Helper for deciding base hour per program ───────────────────────────
    def get_base_hour_for(program: str) -> int:
        return 7 if program in ("8670", "plant3", "trilobe", "Area2") else 6

    # ── Compute “now” once, in EST ───────────────────────────────────────────
    tz_est  = pytz.timezone("America/New_York")
    now_est = timezone.now().astimezone(tz_est)

    all_programs: List[Dict] = []

    # ── Loop over each (one or two) requested program ────────────────────────
    for prog_name in parts:
        # 3) Compute base‐hour in EST for this program
        base_hr = get_base_hour_for(prog_name)
        base_est = tz_est.localize(
            datetime(now_est.year, now_est.month, now_est.day, base_hr, 0, 0)
        )
        if now_est < base_est:
            base_est -= timedelta(days=1)

        # Define the three shift boundaries in EST
        day_start  = base_est
        aft_start  = base_est + timedelta(hours=8)
        nite_start = base_est + timedelta(hours=16)

        if day_start <= now_est < aft_start:
            current_shift = "day"
            shift_start   = day_start
        elif aft_start <= now_est < nite_start:
            current_shift = "afternoon"
            shift_start   = aft_start
        else:
            current_shift = "night"
            shift_start   = nite_start

        shift_start_epoch = int(shift_start.astimezone(pytz.UTC).timestamp())
        shift_end_epoch   = int(timezone.now().timestamp())
        shift_length      = shift_end_epoch - shift_start_epoch

        # “Last 5 minutes” cutoff
        last5_start_epoch = shift_end_epoch - 300

        # 4) Deep‐copy this program’s config so we can annotate in place
        programs_copy = copy.deepcopy(PAGES[prog_name]["programs"])
        machine_set: Set[str] = set()
        # machine_occ maps (machine_id, frozenset_of_parts) → list of cell‐dicts
        machine_occ: Dict[Tuple[str, Optional[FrozenSet[str]]], List[Dict]] = {}

        # Build initial machine_set & machine_occ from PAGES
        for prog_obj in programs_copy:
            for line in prog_obj["lines"]:
                for op in line["operations"]:
                    for m in op["machines"]:
                        mid = m["number"]
                        machine_set.add(mid)
                        if "parts" in m:
                            pk = frozenset(m["parts"])
                        else:
                            pk = None
                        machine_occ.setdefault((mid, pk), []).append(m)

        # ── 5) Handle aliases: remove alias keys, add their source machines ────
        # alias_occ will hold the original cell‐dict lists (for later annotation)
        alias_occ: Dict[Tuple[str, Optional[FrozenSet[str]]], List[Dict]] = {}

        for alias_mid, sources in ALIASES.items():
            # For each parts_key under which this alias appears:
            for (mid_key, pk_key) in list(machine_occ.keys()):
                if mid_key == alias_mid:
                    # extract that cell list
                    alias_occ[(mid_key, pk_key)] = machine_occ.pop((mid_key, pk_key))
            # If alias was in machine_set, remove it
            if alias_mid in machine_set:
                machine_set.remove(alias_mid)
            # Add all sources into machine_set so we compute their metrics
            for src in sources:
                machine_set.add(src)

        # ── 6) Query total pieces since shift start ────────────────────────────
        placeholders = ",".join(["%s"] * len(machine_set))
        params       = list(machine_set) + [shift_start_epoch]
        sql = f"""
            SELECT Machine, Part, SUM(`Count`) AS cnt
            FROM   GFxPRoduction
            WHERE  Machine IN ({placeholders})
              AND  TimeStamp >= %s
            GROUP  BY Machine, Part
        """
        cur = connections["prodrpt-md"].cursor()
        cur.execute(sql, params)
        counts_by_mp: Dict[Tuple[str, str], int] = {
            (str(m), p): int(c) for m, p, c in cur.fetchall()
        }

        totals_by_machine: Dict[str, int] = defaultdict(int)
        for (m, _p), c in counts_by_mp.items():
            totals_by_machine[m] += c

        # ── 7) Query total pieces in last 5 minutes ───────────────────────────
        params5 = list(machine_set) + [last5_start_epoch]
        sql5 = f"""
            SELECT Machine, Part, SUM(`Count`) AS cnt
            FROM   GFxPRoduction
            WHERE  Machine IN ({placeholders})
              AND  TimeStamp >= %s
            GROUP  BY Machine, Part
        """
        cur.execute(sql5, params5)
        counts5_by_mp: Dict[Tuple[str, str], int] = {
            (str(m), p): int(c) for m, p, c in cur.fetchall()
        }

        totals5_by_machine: Dict[str, int] = defaultdict(int)
        for (m, _p), c in counts5_by_mp.items():
            totals5_by_machine[m] += c

        # ── 8) Compute part_runs for entire shift & last 5 minutes ─────────────
        part_runs: Dict[str, List[Dict]]      = {}
        part_runs_5min: Dict[str, List[Dict]] = {}
        for mid in machine_set:
            runs  = compute_part_durations_for_machine(mid, shift_start_epoch, shift_end_epoch)
            runs5 = compute_part_durations_for_machine(mid, last5_start_epoch, shift_end_epoch)
            part_runs[mid]      = runs
            part_runs_5min[mid] = runs5

        # ── 9) Annotate each REAL “machine‐cell” with shift‐wide & 5min metrics ─
        for (mid, parts_key), cells in list(machine_occ.items()):
            # If this key was one of the alias keys, we removed it above, so skip
            if mid in ALIASES:
                continue

            # (a) shift‐wide pieces made for this machine & part‐group
            if parts_key is None:
                pieces_made = totals_by_machine.get(mid, 0)
            else:
                pieces_made = sum(
                    counts_by_mp.get((mid, p), 0) for p in parts_key
                )

            # (b) last 5min pieces for this machine & part‐group
            if parts_key is None:
                pieces5_made = totals5_by_machine.get(mid, 0)
            else:
                pieces5_made = sum(
                    counts5_by_mp.get((mid, p), 0) for p in parts_key
                )

            # (c) cycle times & “smart targets”
            if parts_key is None:
                # No explicit part grouping → use single cycle time
                ct_single = get_cycle_time_seconds(mid)  # part=None internally
                cycle_by_part: Dict[str, Optional[float]] = {}
                if ct_single is not None:
                    for run in part_runs[mid]:
                        cycle_by_part[run["part"]] = ct_single
                rep_ct = ct_single

                if ct_single:
                    # shift‐long “smart target” = floor(sum(run_duration/ct_single))
                    smart_pcs = sum(run["duration"] / ct_single for run in part_runs[mid])
                    smart_target = int(math.floor(smart_pcs)) if smart_pcs > 0 else None
                    # 5min “smart target”
                    smart5_pcs = sum(
                        run5["duration"] / ct_single for run5 in part_runs_5min[mid]
                    )
                    smart_target_5min = int(math.floor(smart5_pcs)) if smart5_pcs > 0 else None
                else:
                    smart_target = None
                    smart_target_5min = None

            else:
                # Mixed‐part grouping → call cycle_time per part, take first non‐None
                cycle_by_part = {p: get_cycle_time_seconds(mid, p) for p in parts_key}
                rep_ct = next((v for v in cycle_by_part.values() if v is not None), None)
                if rep_ct:
                    smart_target      = int(math.floor(shift_length / rep_ct))
                    smart_target_5min = int(math.floor(300 / rep_ct))
                else:
                    smart_target = None
                    smart_target_5min = None

            # (d) annotate each cell in this group (for this real machine)
            for cell in cells:
                cell["count"]            = pieces_made
                cell["pieces5_made"]     = pieces5_made
                cell["cycle_time"]       = rep_ct
                cell["cycle_by_part"]    = cycle_by_part
                cell["smart_target"]     = smart_target or 0
                cell["smart_target_5min"]= smart_target_5min or 0

                # compute cell‐level efficiency for shift‐long
                if pieces_made <= 0 or not smart_target:
                    cell["efficiency"] = None
                    cell["color"]      = "#cccccc"
                else:
                    eff_pct = int((pieces_made / smart_target) * 100)
                    eff_pct = max(0, min(eff_pct, 100))
                    cell["efficiency"] = eff_pct

                    # compute 5‐min efficiency for this machine
                    if pieces5_made <= 0 or not smart_target_5min:
                        eff_5min = 0 if pieces5_made == 0 else None
                    else:
                        eff_5min = int((pieces5_made / smart_target_5min) * 100)
                        eff_5min = max(0, min(eff_5min, 100))

                    # color according to 5‐min eff if available
                    cell["color"] = (
                        efficiency_color(eff_5min) if eff_5min is not None else "#cccccc"
                    )

        # ── 10) Build “alias” cells by summing their source machines ────────────
        # At this point, machine_occ no longer contains alias entries; alias_occ
        # holds the original cell‐dict lists from PAGES. We will compute each
        # alias’s metrics from its sources (which we included in machine_set).
        for (alias_mid, parts_key), cells in alias_occ.items():
            sources = ALIASES.get(alias_mid, [])
            # (a) Sum shift‐long pieces_made across sources
            pieces_made_alias = sum(totals_by_machine.get(src, 0) for src in sources)
            # (b) Sum 5min pieces across sources
            pieces5_made_alias = sum(totals5_by_machine.get(src, 0) for src in sources)

            # (c) Compute alias’s “smart” targets by summing each source’s smart_pcs
            alias_smart_pcs     = 0.0
            alias_smart_pcs_5   = 0.0
            for src in sources:
                ct_src = get_cycle_time_seconds(src)
                if ct_src:
                    # sum fractional “parts” from durations
                    alias_smart_pcs   += sum(run["duration"] / ct_src for run in part_runs[src])
                    alias_smart_pcs_5 += sum(run5["duration"] / ct_src for run5 in part_runs_5min[src])
            smart_target_alias      = (
                int(math.floor(alias_smart_pcs)) if alias_smart_pcs > 0 else None
            )
            smart_target_5min_alias = (
                int(math.floor(alias_smart_pcs_5)) if alias_smart_pcs_5 > 0 else None
            )

            # (d) Determine alias’s shift‐long efficiency and 5min efficiency
            if smart_target_alias and smart_target_alias > 0:
                eff_alias = int((pieces_made_alias / smart_target_alias) * 100)
                eff_alias = max(0, min(eff_alias, 100))
            else:
                eff_alias = None

            if smart_target_5min_alias and smart_target_5min_alias > 0:
                eff5_alias = int((pieces5_made_alias / smart_target_5min_alias) * 100)
                eff5_alias = max(0, min(eff5_alias, 100))
            else:
                eff5_alias = None

            # (e) Color the alias by its 5min efficiency (or gray if none)
            alias_color = (
                efficiency_color(eff5_alias) if eff5_alias is not None else "#808080"
            )

            # (f) Annotate each original “m” dict (from PAGES) in place
            for cell in cells:
                cell["number"]            = alias_mid
                cell["count"]             = pieces_made_alias
                cell["pieces5_made"]      = pieces5_made_alias
                cell["cycle_time"]        = None
                cell["cycle_by_part"]     = {}
                cell["smart_target"]      = smart_target_alias or 0
                cell["smart_target_5min"] = smart_target_5min_alias or 0
                cell["efficiency"]        = eff_alias
                cell["color"]             = alias_color

            # (g) Re‐insert alias entry into machine_occ so that downstream logic runs
            machine_occ[(alias_mid, parts_key)] = cells

        # ── 11) “Padding” each line exactly as before ─────────────────────────
        for prog_obj in programs_copy:
            for line in prog_obj["lines"]:
                max_m = max((len(op["machines"]) for op in line["operations"]), default=1)
                line["max_machines"] = max_m
                for op in line["operations"]:
                    op["pad"] = [None] * (max_m - len(op["machines"]))

        # ── 12) Filter part_runs for parts declared in config (no change) ─────
        filtered_part_runs: Dict[str, List[Dict]] = {}
        for mid, runs in part_runs.items():
            declared_parts = {
                p
                for (m, pk) in machine_occ
                if m == mid and pk is not None
                for p in pk
            }
            if declared_parts:
                runs = [r for r in runs if r["part"] in declared_parts]
            filtered_part_runs[mid] = runs

        # ── 13) Compute total_produced & efficiency at the OP level,
        #          excluding any machine where smart_target <= 0,
        #          then compute 5-minute op-level efficiency and set op["color"]. ─
        for prog_obj in programs_copy:
            for line in prog_obj["lines"]:
                for op in line["operations"]:
                    # consider only machines whose shift-long smart_target > 0
                    valid_machines = [m for m in op["machines"] if m.get("smart_target", 0) > 0]

                    # (a) shift‐long op totals
                    total_produced = sum(m["count"] for m in valid_machines)
                    total_smart    = sum(m["smart_target"] for m in valid_machines)

                    if total_smart > 0:
                        op_eff = int(math.floor((total_produced / total_smart) * 100))
                        op_eff = max(0, min(op_eff, 100))
                    else:
                        op_eff = None

                    op["total_produced"]     = total_produced
                    op["total_smart_target"] = total_smart
                    op["efficiency"]         = op_eff

                    # (a) shift‐long op totals
                    total_produced = sum(m["count"] for m in valid_machines)
                    total_smart    = sum(m["smart_target"] for m in valid_machines)
                    if total_smart > 0:
                        op_eff = int(math.floor((total_produced / total_smart) * 100))
                        op_eff = max(0, min(op_eff, 100))
                    else:
                        op_eff = None

                    op["total_produced"]     = total_produced
                    op["total_smart_target"] = total_smart
                    op["efficiency"]         = op_eff

                    # (b) last‐5‐minute op totals
                    total5_produced = sum(m["pieces5_made"] for m in valid_machines)
                    total5_smart    = sum(m["smart_target_5min"] for m in valid_machines)
                    if total5_smart > 0:
                        op_eff_5min = int(math.floor((total5_produced / total5_smart) * 100))
                        op_eff_5min = max(0, min(op_eff_5min, 100))
                    else:
                        op_eff_5min = None

                    op["recent_efficiency"] = op_eff_5min

                    # (c) color the op cell by its shift‐to‐date efficiency (or gray if none)
                    op["color"] = (
                        efficiency_color(op_eff) if op_eff is not None else "#808080"
                    )

        # ── 14) Merge each prog_obj into all_programs ─────────────────────────
        for prog_obj in programs_copy:
            all_programs.append(prog_obj)

    # ── 15) Render the template with updated efficiency & coloring logic ─────
    context = {
        "pages":    pages,
        "programs": all_programs,
    }
    return render(request, "dashboards/dashboard_renewed.html", context)
