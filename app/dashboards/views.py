import time
from django.db import connections
from django.views.decorators.cache import cache_page
from django.conf import settings
from importlib import import_module
import json
from datetime import datetime, timedelta
from django.http import Http404

from django.shortcuts import render, redirect
import MySQLdb
from prod_query.models import OAMachineTargets
from collections import defaultdict

import pytz
from django.utils import timezone

import json

from django.http import JsonResponse, HttpResponseBadRequest
from django.db import connections
import copy



# from https://github.com/DaveClark-Stackpole/trakberry/blob/e9fa660e2cdd5ef4d730e0d00d888ad80311cacc/trakberry/forms.py#L57
from django import forms


def sub_index(request):
    return redirect('dashboards:dashboard_index') 



class sup_downForm(forms.Form):
    machine = forms.CharField()
    reason = forms.CharField()
    priority = forms.CharField()


def pms_index_view(request):
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

@cache_page(5)
def cell_track_8670(request, template):
    tic = time.time()  # track the execution time
    context = {}  # data sent to template

    target_production_AB1V_Rx = int(
        request.site_variables.get('target_production_AB1V_Rx', 300))
    target_production_AB1V_Input = int(
        request.site_variables.get('target_production_AB1V_Input', 300))
    target_production_AB1V_OD = int(
        request.site_variables.get('target_production_AB1V_OD', 300))
    target_production_10R140 = int(request.site_variables.get(
        'target_production_10R140_Rear', 300))

    # Get the Time Stamp info
    shift_start, shift_time, shift_left, shift_end = stamp_shift_start_3()
    context['t'] = shift_start + shift_time
    request.session["shift_start"] = shift_start

    line_spec_10R140 = [
        # OP 10
        ('1708L', ['1708L'], 2, 10),
        ('1708R', ['1708R'], 2, 10),
        # OP 20
        ('1709', ['1708L', '1708R'], 1, 20),
        # OP 30
        ('1710', ['1710'], 1, 30),
        # OP 40
        ('1711', ['1711'], 1, 40),
        # OP 50
        ('1715', ['1715'], 1, 50),
        # OP 60
        ('1717R', ['1717R'], 1, 60),
        # OP 70
        ('1706', ['1706'], 1, 70),
        # OP 80
        ('1720', ['1720'], 1, 80),
        # OP 90
        ('677', ['677'], 1, 90),
        ('748', ['748'], 1, 90),
        # OP 100
        ('1723', ['1723'], 1, 100),
        # Laser
        ('1725', ['1725'], 1, 130),
    ]



    machine_production_10R140, op_production_10R140 = get_line_prod(
        line_spec_10R140, target_production_10R140, '"50-3214","50-5214"', shift_start, shift_time)

    context['codes_10R140'] = machine_production_10R140
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_10R140]
    part_list = ["50-3214", "50-5214"]
    context['actual_counts_10R140'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op_10R140'] = op_production_10R140


    # -- surgical insertion for 10R140 OEE stuff --
    op_actual_10R140, op_oee_10R140 = compute_op_actual_and_oee(
        line_spec_10R140,
        machine_production_10R140,
        shift_start,
        shift_time,
        part_list=["50-3214", "50-5214"]
    )
    context['op_actual_10R140'] = op_actual_10R140
    context['op_oee_10R140']    = op_oee_10R140

    context['wip_10R140'] = []

    line_spec_8670 = [
        # OP 10
        ('1703L', ['1703L'], 4, 10), ('1704L', ['1704L'], 4, 10),
        ('658', ['658'], 4, 10), ('661', ['661'], 4, 10),
        ('622', ['622'], 4, 10),
        # OP 20/30
        ('1703R', ['1703R'], 4, 30), ('1704R', ['1704R'], 4, 30),
        ('616', ['616'], 4, 30), ('623', ['623'], 4, 30),
        ('617', ['617'], 4, 30),
        # OP 40
        ('1727', ['1727'], 1, 40),
        # OP 50
        ('659', ['659'], 2, 50), ('626', ['626'], 2, 50),
        # OP 60
        ('1712', ['1712'], 1, 60),
        ('1716L', ['1716L'], 1, 70),
        ('1719', ['1719'], 1, 80),
        ('1723', ['1723'], 1, 90),
        ('1750', ['1750'], 1, 130),
        ('1724', ['1724'], 1, 130),
        ('1725', ['1725'], 1, 130),
    ]


    machine_production_8670, op_production_8670 = get_line_prod(
        line_spec_8670, target_production_AB1V_Rx, '"50-8670","50-0450"', shift_start, shift_time)

    context['codes'] = machine_production_8670
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_8670]
    part_list = ["50-8670", "50-0450"]
    context['actual_counts'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op'] = op_production_8670


    # -- surgical insertion for 8670 OEE stuff --
    op_actual_8670, op_oee_8670 = compute_op_actual_and_oee(
        line_spec_8670,
        machine_production_8670,
        shift_start,
        shift_time,
        part_list=["50-8670", "50-0450"]
    )
    context['op_actual_8670'] = op_actual_8670
    context['op_oee_8670']    = op_oee_8670


    context['wip'] = []

    line_spec_5401 = [
        ('1740L', ['1740L'], 2, 10), ('1740R', ['1740R'], 2, 10),
        ('1701L', ['1701L'], 2, 40), ('1701R', ['1701R'], 2, 40),
        ('733', ['1701L', '1701R'], 1, 50),
        ('775', ['775'], 2, 60), ('1702', ['1702'], 2, 60),
        ('581', ['581'], 2, 70), ('788', ['788'], 2, 70),
        ('1714', ['1714'], 1, 80),
        ('1717L', ['1717L'], 1, 90),
        ('1706', ['1706'], 1, 100),
        ('1723', ['1723'], 1, 110),
        ('1750', ['1750'], 1, 130),
        ('1724', ['1724'], 1, 130),
        ('1725', ['1725'], 1, 130),
    ]


    machine_production_5401, op_production_5401 = get_line_prod(
        line_spec_5401, target_production_AB1V_Input, '"50-5401","50-0447"', shift_start, shift_time)

    context['codes_5401'] = machine_production_5401
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_5401]
    part_list = ["50-5401", "50-0447"]
    context['actual_counts_5401'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op_5401'] = op_production_5401


    # -- surgical insertion for 5401 OEE stuff --
    op_actual_5401, op_oee_5401 = compute_op_actual_and_oee(
        line_spec_5401,
        machine_production_5401,
        shift_start,
        shift_time,
        part_list=["50-5401", "50-0447"]
    )
    context['op_actual_5401'] = op_actual_5401
    context['op_oee_5401']    = op_oee_5401


    context['wip_5401'] = []

    line_spec_5404 = [
        ('1705', ['1705L'], 2, 20), ('1746', ['1746R'], 2, 20),
        ('621', ['621'], 2, 25), ('629', ['629'], 2, 25),
        ('785', ['785'], 3, 30), ('1748', ['1748'],
                                  3, 30), ('1718', ['1718'], 3, 30),
        ('669', ['669'], 1, 35),
        ('1726', ['1726'], 1, 40),
        ('1722', ['1722'], 1, 50),
        ('1713', ['1713'], 1, 60),
        ('1716R', ['1716R'], 1, 70),
        ('1719', ['1719'], 1, 80),
        ('1723', ['1723'], 1, 90),
        ('1750', ['1750'], 1, 130),
        ('1724', ['1724'], 1, 130),
        ('1725', ['1725'], 1, 130),
    ]


    target_production = 300
    machine_production_5404, op_production_5404 = get_line_prod(
        line_spec_5404, target_production_AB1V_OD, '"50-5404","50-0519"', shift_start, shift_time)

    context['codes_5404'] = machine_production_5404
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_5404]
    part_list = ["50-5404", "50-0519"]
    context['actual_counts_5404'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op_5404'] = op_production_5404


    # -- surgical insertion for 5404 OEE stuff --
    op_actual_5404, op_oee_5404 = compute_op_actual_and_oee(
        line_spec_5404,
        machine_production_5404,
        shift_start,
        shift_time,
        part_list=["50-5404", "50-0519"]
    )
    context['op_actual_5404'] = op_actual_5404
    context['op_oee_5404']    = op_oee_5404


    context['wip_5404'] = []

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


def track_graph_track(request, index):
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

def list_and_update_shift_points(request):
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
    return MySQLdb.connect(
        host=settings.NEW_HOST,
        user=settings.DAVE_USER,
        passwd=settings.DAVE_PASSWORD,
        db=settings.DAVE_DB
    )


def fetch_pie_chart_data(machine):
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
                                ],
                            },
                            {
                                "op": "OP30",
                                "machines": [
                                    {"number": "1502"},
                                    {"number": "1507"},
                                ],
                            },
                            {
                                "op": "OP40",
                                "machines": [
                                    {"number": "1501"},
                                    {"number": "1515"},
                                ],
                            },
                            {
                                "op": "OP50",
                                "machines": [
                                    {"number": "1508"},
                                    {"number": "1532"},
                                ],
                            },
                            {
                                "op": "OP60",
                                "machines": [
                                    {"number": "1509"},
                                ],
                            },
                            {
                                "op": "OP70",
                                "machines": [
                                    {"number": "1514"},
                                ],
                            },
                            {
                                "op": "OP80",
                                "machines": [
                                    {"number": "1510"},
                                ],
                            },
                            {
                                "op": "OP90",
                                "machines": [
                                    {"number": "1513"},
                                ],
                            },
                            {
                                "op": "OP100",
                                "machines": [
                                    {"number": "1503"},
                                ],
                            },
                            {
                                "op": "OP110",
                                "machines": [
                                    {"number": "1511"},
                                ],
                            },
                        ],
                    },
                    {
                        "line": "OffLine",
                        "scrap_line": "OffLine",
                        "operations": [
                            {
                                "op": "OP10",
                                "machines": [
                                    {"number": "1521"},
                                    {"number": "1522"},
                                    {"number": "1523"},
                                ],
                            },
                            {
                                "op": "OP30",
                                "machines": [
                                    {"number": "1539"},
                                    {"number": "1540"},
                                ],
                            },
                            {
                                "op": "OP40",
                                "machines": [
                                    {"number": "1524"},
                                    {"number": "1525"},
                                ],
                            },
                            {
                                "op": "OP50",
                                "machines": [
                                    {"number": "1538"},
                                ],
                            },
                            {
                                "op": "OP60",
                                "machines": [
                                    {"number": "1541"},
                                ],
                            },
                            {
                                "op": "OP70",
                                "machines": [
                                    {"number": "1531"},
                                ],
                            },
                            {
                                "op": "OP80",
                                "machines": [
                                    {"number": "1527"},
                                ],
                            },
                            {
                                "op": "OP90",
                                "machines": [],
                            },
                            {
                                "op": "OP100",
                                "machines": [
                                    {"number": "1530"},
                                ],
                            },
                            {
                                "op": "OP110",
                                "machines": [
                                    {"number": "1528"},
                                ],
                            },
                        ],
                    },
                    {
                        "line": "Uplift",
                        "scrap_line": "Uplift",
                        "operations": [
                            {
                                "op": "OP10",
                                "machines": [],
                            },
                            {
                                "op": "OP30",
                                "machines": [
                                    {"number": "1546"},
                                ],
                            },
                            {
                                "op": "OP40",
                                "machines": [
                                    {"number": "1547"},
                                ],
                            },
                            {
                                "op": "OP50",
                                "machines": [
                                    {"number": "1548"},
                                ],
                            },
                            {
                                "op": "OP60",
                                "machines": [
                                    {"number": "1549"},
                                ],
                            },
                            {
                                "op": "OP70",
                                "machines": [
                                    {"number": "594"},
                                ],
                            },
                            {
                                "op": "OP80",
                                "machines": [
                                    {"number": "1551"},
                                ],
                            },
                            {
                                "op": "OP90",
                                "machines": [
                                    {"number": "1552"},
                                ],
                            },
                            {
                                "op": "OP100",
                                "machines": [
                                    {"number": "751"},
                                ],
                            },
                            {
                                "op": "OP110",
                                "machines": [
                                    {"number": "1554"},
                                ],
                            },
                        ],
                    },
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
                                    {"number": "262"},
                                    {"number": "263"},
                                ],
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
                                    {"number": "1703L"},
                                    {"number": "1704L"},
                                    {"number": "658"},
                                    {"number": "661"},
                                    {"number": "622"},
                                ],
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
                                    {"number": "1719"},
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
                                    {"number": "1724"},
                                    {"number": "1725"},
                                    {"number": "1750"},
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
                                    {"number": "1719"},
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
                                    {"number": "1724"},
                                    {"number": "1725"},
                                    {"number": "1750"},
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
                                    {"number": "581"},
                                    {"number": "788"},
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
                                    {"number": "1706"},
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
                                    {"number": "1724"},
                                    {"number": "1725"},
                                    {"number": "1750"},
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
                                    {"number": "1706"},
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
                                    {"number": "1725"},
                                ],
                            },
                        ],
                    }
                ],
            },
        ],
    },
}






# ─────────────────────────────────────────────────────────────────────────────
# Assume PAGES is defined elsewhere in this module exactly as you provided.
# ─────────────────────────────────────────────────────────────────────────────


def compute_part_durations_for_machine(machine_number: str,
                                       shift_start_epoch: int,
                                       shift_end_epoch: int = None):
    """
    Returns a list of dictionaries, each containing:
       {
           'part':    <part_number_as_string>,
           'start_ts':<epoch_timestamp_when_this_part_started>,
           'end_ts':  <epoch_timestamp_when_this_part_ended>,
           'duration':<duration_in_seconds_between_start_and_end>
       }
    for the given machine across the specified shift window.

    If shift_end_epoch is None, it will default to “now” (UTC).
    """
    # 1) If no shift_end_epoch provided, use current UTC timestamp.
    if shift_end_epoch is None:
        now_utc = timezone.now()
        shift_end_epoch = int(now_utc.timestamp())

    cursor = connections["prodrpt-md"].cursor()

    # 2) Fetch the last record before shift_start_epoch (to see what was running at shift start)
    sql_before = """
        SELECT Part, TimeStamp
        FROM GFxPRoduction
        WHERE Machine = %s
          AND TimeStamp < %s
        ORDER BY TimeStamp DESC
        LIMIT 1
    """
    cursor.execute(sql_before, [machine_number, shift_start_epoch])
    row_before = cursor.fetchone()
    if row_before:
        initial_part, initial_ts = row_before

    else:
        initial_part, initial_ts = (None, None)


    # 3) Fetch all records during the shift window, ordered by timestamp ascending
    sql_during = """
        SELECT Part, TimeStamp
        FROM GFxPRoduction
        WHERE Machine = %s
          AND TimeStamp >= %s
          AND TimeStamp <= %s
        ORDER BY TimeStamp ASC
    """
    cursor.execute(sql_during, [machine_number, shift_start_epoch, shift_end_epoch])
    rows_during = cursor.fetchall()


    # 4) Initialize variables for tracking “current run segment”
    runs = []
    current_part = None
    current_start = None

    # 4a) If there was a part already running as of shift_start, initialize it
    if initial_part is not None:
        current_part = initial_part
        current_start = shift_start_epoch


    # 4b) Iterate through every (part, timestamp) record during the shift
    for part, ts in rows_during:

        # If we don’t have an active “current_part” yet, start one here.
        if current_part is None:
            current_part = part
            # If the first record’s timestamp is earlier than shift_start, clamp to shift_start
            current_start = max(shift_start_epoch, ts)
            continue


        # Otherwise, part has changed at this timestamp → close out the previous run
        run_end = ts
        run_duration = int(run_end - current_start)
        runs.append({
            "part": current_part,
            "start_ts": current_start,
            "end_ts": run_end,
            "duration": run_duration,
        })


        # Start a new run for the new part
        current_part = part
        current_start = ts

    # 5) After processing all “during” records, close out whichever part is still running at shift_end
    if current_part is not None and current_start is not None:
        final_end = shift_end_epoch
        final_duration = int(final_end - current_start)
        runs.append({
            "part": current_part,
            "start_ts": current_start,
            "end_ts": final_end,
            "duration": final_duration,
        })
    else:
        print(f"[DEBUG][{machine_number}] No active run to close at end of shift.")

    return runs



def dashboard_current_shift(request, page: str):
    """
    Given a URL like /dashboard/dashboard/<page>/,
    1. Verify `page` is valid.
    2. Deep-copy that page's programs so we can annotate.
    3. Determine current shift (day/afternoon/night) in EST.
    4. Compute epoch of shift start → query GFxPRoduction SUM(Count).
    5. Annotate each machine dict with m['count'].
    6. Compute line["max_machines"] and op["pad"] for templating.
    7. For each machine, call compute_part_durations_for_machine to get per-part durations.
    8. Render into 'dashboards/dashboard_renewed.html' (Bootstrap).
    """
    # 1) Validate page
    if page not in PAGES:
        return HttpResponseBadRequest(
            {
                "error": (
                    f"Unknown page '{page}'. "
                    f"Valid pages are: {list(PAGES.keys())}"
                )
            },
            content_type="application/json",
        )

    # 2) Deep-copy programs for this page so we can annotate counts & padding
    programs = copy.deepcopy(PAGES[page]["programs"])

    # Build a set of all machine numbers under this page
    machine_set = set()
    for prog in programs:
        for line in prog["lines"]:
            for op in line["operations"]:
                for m in op["machines"]:
                    machine_set.add(m["number"])

    # If no machines at all, short-circuit to an empty dashboard
    if not machine_set:
        context = {
            "page": page,
            "dayshift_start": PAGES[page]["dayshift_start"],
            "current_shift": None,
            "shift_start_est": None,
            "per_machine": {},
            "programs": programs,
            "part_runs": {},  # no machines → no part durations
        }
        return render(request, "dashboards/dashboard_renewed.html", context)

    # 3) Determine "now" in EST
    now_utc = timezone.now()  # Aware UTC
    eastern = pytz.timezone("America/New_York")
    now_est = now_utc.astimezone(eastern)

    # 4) Decide shift boundaries based on page:
    if page == "8670":
        shift_base_hour = 7
    else:
        shift_base_hour = 6

    # Build today's (EST) "base" at shift_base_hour:00
    today_est_date = now_est.date()
    today_base_est = eastern.localize(
        datetime(
            year=today_est_date.year,
            month=today_est_date.month,
            day=today_est_date.day,
            hour=shift_base_hour,
            minute=0,
            second=0,
        )
    )

    # If now_est is before today's base, roll the base back one day
    if now_est < today_base_est:
        base_est = today_base_est - timedelta(days=1)
    else:
        base_est = today_base_est

    # Define the three 8-hour shifts from base_est:
    day_start_est = base_est
    afternoon_start_est = base_est + timedelta(hours=8)
    night_start_est = base_est + timedelta(hours=16)

    # 5) Determine which shift we’re currently in (in EST)
    if day_start_est <= now_est < afternoon_start_est:
        current_shift = "day"
        shift_start_est = day_start_est
    elif afternoon_start_est <= now_est < night_start_est:
        current_shift = "afternoon"
        shift_start_est = afternoon_start_est
    else:
        current_shift = "night"
        if now_est >= night_start_est:
            shift_start_est = night_start_est
        else:
            shift_start_est = night_start_est  # because base_est was already rolled back


    # 6) Convert shift_start_est → UTC epoch for SQL
    shift_start_utc = shift_start_est.astimezone(pytz.UTC)
    shift_start_epoch = int(shift_start_utc.timestamp())

    # 7) Query GFxPRoduction for SUM(Count) per machine since shift_start_epoch
    placeholders = ",".join(["%s"] * len(machine_set))
    params = list(machine_set) + [shift_start_epoch]

    raw_sql = f"""
        SELECT
            Machine,
            SUM(`Count`) AS total_since_shift_start
        FROM
            GFxPRoduction
        WHERE
            Machine IN ({placeholders})
            AND TimeStamp >= %s
        GROUP BY
            Machine
    """

    cursor = connections["prodrpt-md"].cursor()
    cursor.execute(raw_sql, params)
    rows = cursor.fetchall()  # [(machine_number, total_since_shift_start), ...]

    # 8) Build a per_machine dict with zero defaults, then override with actual totals
    per_machine = {m: 0 for m in machine_set}
    for machine_num, total in rows:
        per_machine[str(machine_num)] = int(total)

    # 9) Annotate each machine dict (in our deep-copied `programs`) with its count
    for prog in programs:
        for line in prog["lines"]:
            for op in line["operations"]:
                for m in op["machines"]:
                    mnum = m["number"]
                    m["count"] = per_machine.get(mnum, 0)

    # 10) For each line, compute max_machines & pad lists
    for prog in programs:
        for line in prog["lines"]:
            max_machines = 0
            for op in line["operations"]:
                count_m = len(op["machines"])
                if count_m > max_machines:
                    max_machines = count_m
            if max_machines == 0:
                max_machines = 1
            line["max_machines"] = max_machines

            for op in line["operations"]:
                pad_count = max_machines - len(op["machines"])
                if pad_count < 0:
                    pad_count = 0
                op["pad"] = [None] * pad_count

    # 11) Compute part durations for each machine across this shift
    shift_end_epoch = int(timezone.now().timestamp())
    part_runs = {}
    for mnum in machine_set:
        runs = compute_part_durations_for_machine(mnum, shift_start_epoch, shift_end_epoch)
        part_runs[mnum] = runs

    # ── DEBUG: Summarize part_runs in console ──
    for mnum, runs in part_runs.items():
        for r in runs:
            # Convert epoch to EST datetime strings
            start_dt = datetime.fromtimestamp(r["start_ts"], tz=pytz.UTC).astimezone(eastern)
            end_dt   = datetime.fromtimestamp(r["end_ts"],   tz=pytz.UTC).astimezone(eastern)

    # 12) Build context and render template
    context = {
        "page": page,
        "dayshift_start": PAGES[page]["dayshift_start"],
        "current_shift": current_shift,
        "shift_start_est": shift_start_est,
        "per_machine": per_machine,
        "programs": programs,
        "part_runs": part_runs,
    }
    return render(request, "dashboards/dashboard_renewed.html", context)