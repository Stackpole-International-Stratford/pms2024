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


    # Right here I will call the new function

    machine_production_col1, op_production_col1 = get_line_prod(
        line_spec_col_1, target_production_col1, None, shift_start, shift_time)

    context['codes_col1'] = machine_production_col1
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_col1]
    part_list = None
    context['actual_counts_col1'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op_col1'] = op_production_col1
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


    # Right here I will call the new function

    machine_production_col2, op_production_col2 = get_line_prod(
        line_spec_col_2, target_production_col2, None, shift_start, shift_time)

    context['codes_col2'] = machine_production_col2
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_col2]
    part_list = None
    context['actual_counts_col2'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op_col2'] = op_production_col2
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


    # Right here I will call the new function

    machine_production_col3, op_production_col3 = get_line_prod(
        line_spec_col_3, target_production_col3, None, shift_start, shift_time)

    context['codes_col3'] = machine_production_col3
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_col3]
    part_list = None
    context['actual_counts_col3'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op_col3'] = op_production_col3
    context['wip_col3'] = []

    line_spec_col_4 = [
        ('636', ['636'], 1, 10),  # 50-5710
        ('625', ['625'], 1, 20),  # 50-5710
        ('Prediction', ['625', '636'], 1, 30),  # Prediction
    ]

    machine_production_col4, op_production_col4 = get_line_prod(
        line_spec_col_4, target_production_col4, None, shift_start, shift_time)

    context['codes_col4'] = machine_production_col4
    actual_counts = [(mp[0], mp[1]) for mp in machine_production_col4]
    part_list = None
    context['actual_counts_col4'] = log_shift_times(shift_start, shift_time, actual_counts, part_list)
    context['op_col4'] = op_production_col4
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



def log_shift_times(shift_start, shift_time, actual_counts, part_list):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    # ——— EDIT THIS: list machine IDs here that need part_list targets ———
    machines_requiring_part_list = [
        # e.g. '1723', '1504', ...
        '1723', '1724',
    ]
    # ————————————————————————————————————————————————————————————————

    est = ZoneInfo("America/New_York")
    start_dt = datetime.fromtimestamp(shift_start, tz=est)
    elapsed = timedelta(seconds=shift_time)

    # print(f"[Shift] start: {start_dt.strftime('%Y-%m-%d %I:%M:%S %p %Z')} | elapsed: {elapsed}")

    total_actual = sum(count for _, count in actual_counts)
    # print(f"[Shift] total actual count: {total_actual}")

    minutes_elapsed = shift_time / 60.0
    # print("[Shift] per-machine actuals vs targets:")

    # Prepare new list to hold (machine, int_pct)
    swapped_counts = []

    for machine, count in actual_counts:
        # decide whether to pass part_list into the target lookup
        if part_list and machine in machines_requiring_part_list:
            raw_target = get_machine_target(machine, shift_start, part_list) or 0
        else:
            raw_target = get_machine_target(machine, shift_start) or 0

        # adjust for shift duration
        adjusted_target = raw_target * (minutes_elapsed / 7200.0)
        pct = (count / adjusted_target * 100) if adjusted_target else 0.0

        # print with truncated percent
        # print(f"  - {machine}: actual={count}, target={adjusted_target:.2f}, {int(pct)}")

        # swap out the count for the int pct
        swapped_counts.append((machine, int(pct)))

    return swapped_counts


MACHINE_TARGET_ALIASES = {
    '733': ['1701L', '1701R'],
    '1746': ['1746R'],
    '1705': ['1746R']
    # Add more as needed
}

def get_machine_target(machine_id, shift_start_unix, part_list=None):
    """
    Returns the most recent non-deleted target for a given machine (or its alias group),
    optionally filtered by part_list, at or before the shift start.
    Tries the machine_id directly, or strips trailing letter, or sums targets from aliases.
    """

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

    # Case 1: use machine_id directly
    result = query_target(machine_id)
    if result:
        return result.target

    # Case 2: if ends in a letter and no match, try stripping it
    if machine_id and machine_id[-1].isalpha():
        fallback_id = machine_id[:-1]
        fallback_result = query_target(fallback_id)
        if fallback_result:
            return fallback_result.target

    # Case 3: piggyback logic (sum of other machine targets)
    if machine_id in MACHINE_TARGET_ALIASES:
        total = 0
        for aliased_id in MACHINE_TARGET_ALIASES[machine_id]:
            aliased_result = query_target(aliased_id)
            if aliased_result:
                total += aliased_result.target
        return total if total > 0 else None

    return None



def compute_op_actual_and_oee(line_spec,
                              machine_production,
                              shift_start,
                              shift_time,
                              part_list=None):
    """
    Returns two lists:
      op_actual_list[i] = total actual for OP i
      op_oee_list[i]    = int OEE% for OP i
    Prints debug info.
    """
    # print(f"compute_op_actual_and_oee: shift_start={shift_start}, shift_time={shift_time}")
    minutes_elapsed = shift_time / 60.0
    factor          = minutes_elapsed / 7200.0
    # print(f"  minutes_elapsed={minutes_elapsed:.1f}, factor={factor:.5f}")

    # map asset → OP
    asset2op = {asset: op for asset, *_ , op in line_spec}
    # print(f"  asset2op mapping: {asset2op}")

    # temporary dicts to accumulate
    op_actual   = defaultdict(int)
    op_adjusted = defaultdict(float)

    # print("  per-machine production:")
    for asset, actual_count, *_, in machine_production:
        op = asset2op.get(asset)
        if op is None:
            print(f"    - skipping {asset!r}: no OP mapping")
            continue

        # raw target lookup
        raw = None
        if part_list:
            raw = get_machine_target(asset, shift_start, part_list)
            # print(f"    - {asset}: get_machine_target(part_list) → {raw}")
        if raw is None:
            raw = get_machine_target(asset, shift_start)
            # print(f"    - {asset}: fallback get_machine_target → {raw}")
        raw = raw or 0

        adj = raw * factor
        pct = int(actual_count / adj * 100) if adj else 0

        # print(f"    - {asset}: actual={actual_count}, raw={raw}, adjusted={adj:.2f}, pct={pct}%")

        op_actual[op]   += actual_count
        op_adjusted[op] += adj

    # print("  per-OP accumulation:")
    # for op in sorted(op_actual):
    #     # print(f"    OP{op}: sum_actual={op_actual[op]}, sum_adjusted={op_adjusted[op]:.2f}")

    # figure out how big our list needs to be
    max_op = max(op_actual.keys() | op_adjusted.keys(), default=0)
    op_actual_list = [0] * (max_op + 1)
    op_oee_list    = [0] * (max_op + 1)

    # fill them
    for op, actual in op_actual.items():
        op_actual_list[op] = actual

    for op, adjusted in op_adjusted.items():
        pct = int(op_actual[op] / adjusted * 100) if adjusted else 0
        op_oee_list[op] = pct
        # print(f"    OP{op}: computed OEE={pct}%")

    return op_actual_list, op_oee_list

