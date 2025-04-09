from django.http import HttpResponse
from django.shortcuts import render
from django.db import connections
import mysql.connector
# import mysql.connector

from datetime import datetime, date, timedelta
import time

from .forms import MachineInquiryForm
from .forms import CycleQueryForm
from .forms import WeeklyProdDate
from .forms import WeeklyProdUpdate
from .models import Weekly_Production_Goal
from query_tracking.models import record_execution_time
from django.shortcuts import redirect
from math import ceil
import logging
from django.conf import settings
from django.views.decorators.http import require_GET


from django.utils.dateparse import parse_datetime
from django.http import JsonResponse
from plant.models.setupfor_models import SetupFor, AssetCycleTimes


from .forms import ShiftTotalsForm
import time
import numpy as np
from collections import Counter


DAVE_HOST = settings.DAVE_HOST
DAVE_USER = settings.DAVE_USER
DAVE_PASSWORD = settings.DAVE_PASSWORD
DAVE_DB = settings.DAVE_DB



logger = logging.getLogger('prod-query')


def sub_index(request):
    return redirect('prod_query:prod-query_index')



# part is the part number [##-####] as a string
# end_of_period is the timestamp of the last second of the period (used to search for currently effective goal)
# returns a tupple with the part number and the goal

def weekly_prod_goal(part, end_of_period):
    goals = Weekly_Production_Goal.objects.filter(part_number=part).order_by('-year', '-week').all()
    for goal in goals:
        goal_date = date.fromisocalendar(year=goal.year, week=goal.week, day=7)
        goal_ts = datetime.combine(goal_date, datetime.min.time()).timestamp()-7200
        if goal_ts <= end_of_period:
            return goal.goal
    return 0



def adjust_target_to_effective_date(target_date):
    (temp_year,temp_week,temp_day) = target_date.isocalendar()
    effective_date = date.fromisocalendar(year=temp_year, week=temp_week, day=7)
    effective_date -= timedelta(days = 7)
    return effective_date
    

#  Report total production by part from end of line machines
def weekly_prod(request):

    # Part, shift start in 24 hour time, list of machines used
    parameters = [
        ("50-9341", 22, ['1533']),
        ("50-0455", 22, ['1816']),
        ("50-1467", 22, ['742', '650L', '650R', '769']),  # 650L and 650R replaced with 742 5/28/2024
        ("50-3050", 22, ['769']),
        ("50-8670", 23, ['1724', '1725', '1750']),
        ("50-0450", 23, ['1724', '1725', '1750']),
        ("50-5401", 23, ['1724', '1725', '1750']),
        ("50-0447", 23, ['1724', '1725', '1750']),
        ("50-5404", 23, ['1724', '1725', '1750']),
        ("50-0519", 23, ['1724', '1725', '1750']),
        ("50-4865", 23, ['1617']),
        ("50-5081", 23, ['1617']),
        ("50-4748", 23, ['797']),
        ("50-3214", 23, ['1725']),
        ("50-5214", 23, ['1725']),
    ]
    # Add new part information here.
    # Increase number of rows in template script file

    context = {}
    tic = time.time()
    target = datetime.today().date()        #this is wrong, doesn't allow setting goal setting for previous weeks
    (temp_year,temp_week,temp_day) = datetime.today().date().isocalendar()
    effective_date = date.fromisocalendar(year=temp_year, week=temp_week, day=7)
    effective_date -= timedelta(days = 7)
    context['form'] = WeeklyProdDate(initial={'date': target})
    context['update_form'] = WeeklyProdUpdate(initial={'effective_date': effective_date})

    if request.method == 'POST':

        if 'update' in request.POST:
            form = WeeklyProdUpdate(request.POST)
            if form.is_valid():
                effective_date = form.cleaned_data.get('effective_date')
                goal = form.cleaned_data.get('goal')
                part_number = form.cleaned_data.get('part_number')

                #check for weekly goal, if there overwrite it, else make new weekly goal
                
                effective_year = effective_date.year
                effective_week = effective_date.isocalendar().week

                new_weekly_goal, created = Weekly_Production_Goal.objects.get_or_create(
                    part_number=part_number,
                    year=effective_year, 
                    week=effective_week,
                    defaults={'goal': goal},)

                new_weekly_goal.goal = goal
                new_weekly_goal.save()

        form = WeeklyProdDate(request.POST)
        if form.is_valid():
            # Previous week
            if 'prev' in request.POST:
                target = form.cleaned_data.get('date') - timedelta(days=7)
                new_effective_date = adjust_target_to_effective_date(target)
                context['update_form'] = WeeklyProdUpdate(initial={'effective_date': new_effective_date})
            # Specific week
            if 'specific' in request.POST:
                target = form.cleaned_data.get('date')
                new_effective_date = adjust_target_to_effective_date(target)
                context['update_form'] = WeeklyProdUpdate(initial={'effective_date': new_effective_date})
            # Current week
            context['form'] = WeeklyProdDate(initial={'date': target})

    cursor = connections['prodrpt-md'].cursor()

    # Date headers for table
    days_past_sunday = target.isoweekday() % 7
    sunday = target - timedelta(days=days_past_sunday)
    dates = []
    for i in range(1, 8):
        dates.append(sunday + timedelta(days=i))

    seconds_in_shift = 28800
    rows = []
    for part, shift_start_hour, source_machine_list in parameters:

        # Time stamps for each shift
        shift_start = datetime(target.year, target.month, target.day,
                               shift_start_hour, 0, 0)-timedelta(days=days_past_sunday)
        shift_starts = []
        start = datetime.timestamp(shift_start)
        for i in range(0, 21):
            shift_starts.append(start)
            start = start + seconds_in_shift
        last_shift_end = shift_starts[20] + seconds_in_shift

        # Goal
        end_of_period = last_shift_end
        goal = weekly_prod_goal(part,end_of_period)

        # One query for each machine used by part
        # sql "in" is very slow
        values_from_query = 21
        row = [0] * values_from_query
        for machine in source_machine_list:
            # Prepares select for query
            sum_string = ''
            for i in range(0, values_from_query):
                sum_string += f"IFNULL(SUM(\n"
                sum_string += f"CASE\n"
                sum_string += f"WHEN TimeStamp >= {shift_starts[i]}\n"
                sum_string += f"AND TimeStamp <= {shift_starts[i] + seconds_in_shift} THEN 1\n"
                sum_string += f"ELSE 0\n"
                sum_string += f"END\n"
                sum_string += f"), 0) as quantitycol{i+1},"
            sum_string = sum_string[:-1]
            sum_string = "SELECT\n" + sum_string

            # Prepares remainder of query
            sql_quantities = f"\nFROM\n"
            sql_quantities += f"GFxPRoduction\n"
            sql_quantities += f"WHERE\n"
            sql_quantities += f"TimeStamp >= {shift_starts[0]}\n"
            sql_quantities += f"AND TimeStamp < {last_shift_end}\n"
            sql_quantities += f"AND Machine = '{machine}'\n"
            sql_quantities += f"AND Part = '{part}'"

            # Executes query
            sql_quantities = sum_string + sql_quantities
            cursor.execute(sql_quantities)
            # The return value is a tuple with a single value, which this unpacks
            (res,) = cursor.fetchall()
            for i in range(0, values_from_query):
                row[i] += res[i]

        # Calculates:
        # The total parts actually produced
        # The predicted total by end of week
        #   based off of percent of time left in week
        #   sets the percent to 100% if the week is in the past
        # The difference between the predicted total and the goal
        # This processing occurs once per row
        week_total = sum(row)
        time_left = last_shift_end - datetime.timestamp(datetime.now())
        if time_left < 0:
            predicted = round(int(week_total))
        else:
            proportion = time_left / 604800
            predicted = round(int(week_total)/(1-proportion))
        difference = round(predicted-int(goal))

        # Goal is inserted after the loop processing is completed, simplifying the indexes
        row.insert(0, part)
        row.append(week_total)
        row.append(predicted)
        row.append(goal)  # add in goal for reference
        row.append(difference)
        rows.append(row)

    context['dates'] = dates
    context['rows'] = rows
    context['page_title'] = "Weekly Production"

    print(time.time()-tic)

    return render(request, 'prod_query/weekly-prod.html', context)


def prod_query_index_view(request):
    context = {}
    context["main_heading"] = "Prod Query Index"
    context["title"] = "Prod Query Index - pmsdata12"
    return render(request, f'prod_query/index_prod_query.html', context)

# Updated strokes_per_min_graph view
def strokes_per_min_graph(request):
    default_numGraphPoints = 300
    context = {}
    if request.method == 'GET':
        form = CycleQueryForm()
        context['form'] = form
        context['numGraphPoints'] = default_numGraphPoints
    elif request.method == 'POST':
        form = CycleQueryForm(request.POST)
        if form.is_valid():
            machine = form.cleaned_data['machine']
            start_date = form.cleaned_data['start_date']
            start_time = form.cleaned_data['start_time']
            end_date = form.cleaned_data['end_date']
            end_time = form.cleaned_data['end_time']
            numGraphPoints = int(request.POST.get('numGraphPoints', default_numGraphPoints))

            # Ensure numGraphPoints is within the allowed range
            if numGraphPoints < 50:
                numGraphPoints = 50
            elif numGraphPoints > 1000:
                numGraphPoints = 1000

            # Combine date and time into datetime objects
            start_datetime = datetime.combine(start_date, start_time)
            end_datetime = datetime.combine(end_date, end_time)

            # Convert datetimes to Unix timestamps
            start_timestamp = int(time.mktime(start_datetime.timetuple()))
            end_timestamp = int(time.mktime(end_datetime.timetuple()))

            # Calculate the total duration in minutes
            total_minutes = (end_datetime - start_datetime).total_seconds() / 60

            # Calculate the interval to display numGraphPoints points
            interval = max(int(total_minutes / numGraphPoints), 1)

            labels, counts = fetch_chart_data(machine, start_timestamp, end_timestamp, interval=interval, group_by_shift=False)
            context['chartdata'] = {
                'labels': labels,
                'dataset': {
                    'label': 'Quantity',
                    'data': counts,
                    'borderWidth': 1
                }
            }
        context['form'] = form
        context['numGraphPoints'] = numGraphPoints

    return render(request, 'prod_query/strokes_per_minute.html', context)


def strokes_per_minute_chart_data(machine, start, end, interval=5):
    sql  = f'SELECT DATE_ADD('
    sql += f'FROM_UNIXTIME({start}), '
    sql += f'Interval CEILING(TIMESTAMPDIFF(MINUTE, FROM_UNIXTIME({start}), '
    sql += f'FROM_UNIXTIME(TimeStamp))/{interval})*{interval} minute) as event_datetime_interval, '
    sql += f'count(*) '
    sql += f'FROM GFxPRoduction '
    sql += f'WHERE TimeStamp BETWEEN {start} AND {end} AND Machine = "{machine}" '
    sql += f'GROUP BY event_datetime_interval '
    sql += f'ORDER BY event_datetime_interval; '

    with connections['prodrpt-md'].cursor() as c:
        c.execute(sql)
        labels = []
        counts = []
        
        row = c.fetchone()
        for time in range(int(start),int(end),interval*60):
            dt= datetime.fromtimestamp(time)

            if not row:  # fills in rows that dont exist at the end of the period
                row = (dt,0)
            if row[0] > dt:  # create periods with no production (dont show in query)
                labels.append(dt)
                counts.append(0)
                continue
            while row[0] < dt:
                row = c.fetchone() # query pulls one period before
            if row[0] == dt:
                labels.append(dt)
                counts.append(row[1]/interval)
                row = c.fetchone()
        
    return labels, counts

# def cycle_times(request):
#     context = {}
#     toc = time.time()
#     if request.method == 'GET':
#         form = CycleQueryForm()

#     if request.method == 'POST':
#         form = CycleQueryForm(request.POST)
#         if form.is_valid():
#             target_date = form.cleaned_data.get('target_date')
#             times = form.cleaned_data.get('times')
#             machine = form.cleaned_data.get('machine')

#             shift_start = request.POST.get('shift_start')
#             shift_end = request.POST.get('shift_end')
#             tic = time.time()

#             sql = f'SELECT * FROM `GFxPRoduction` '
#             sql += f'WHERE `Machine`=\'{machine}\' '
#             sql += f'AND `TimeStamp` BETWEEN \'{int(shift_start.timestamp())}\' AND \'{int(shift_end.timestamp())}\' '
#             sql += f'ORDER BY TimeStamp;'
#             cursor = connections['prodrpt-md'].cursor()
#             cursor.execute(sql)
#             lastrow = -1
#             times = {}

#             count = 0
#             # get the first row and save the first cycle time            
#             row = cursor.fetchone()
#             if row:
#                 lastrow = row[4]

#             while row:
#                 cycle = round(row[4]-lastrow)
#                 if cycle > 0 :
#                     times[cycle] = times.get(cycle, 0) + 1
#                     lastrow = row[4]
#                     count += 1
#                 row = cursor.fetchone()

#             res = sorted(times.items())
#             if (len(res) == 0):
#                 context['form'] = form
#                 return render(request, 'prod_query/cycle_query.html', context)

#             # Uses a range loop to rehydrate the frequency table without holding the full results in memory
#             # Sums values above the lower trim index and stops once it reaches the upper trim index
#             PERCENT_EXCLUDED = 0.05
#             remove = round(count * PERCENT_EXCLUDED)
#             low_trimindex = remove
#             high_trimindex = count - remove
#             it = iter(res)
#             trimsum = 0
#             track = 0
#             val = next(it)
#             for i in range(high_trimindex):
#                 if (track >= val[1]):
#                     val = next(it)
#                     track = 0
#                 if (i > low_trimindex):
#                     trimsum += val[0]
#                 track += 1
#             trimAve = trimsum / high_trimindex
#             context['trimmed'] = f'{trimAve:.3f}'
#             context['excluded'] = f'{PERCENT_EXCLUDED:.2%}'

#             # Sums all cycle times that are DOWNTIME_FACTOR times larger than the trimmed average
#             DOWNTIME_FACTOR = 3
#             threshold = int(trimAve * DOWNTIME_FACTOR)
#             downtime = 0
#             microstoppage = 0
#             for r in res:
#                 if (r[0] > trimAve and r[0] < threshold):
#                     microstoppage += (r[0] - trimAve) * r[1]
#                 if (r[0] > threshold):
#                     downtime += r[0] * r[1]
#             context['microstoppage'] = f'{microstoppage / 60:.1f}'
#             context['downtime'] = f'{downtime / 60:.1f}'
#             context['factor'] = DOWNTIME_FACTOR

#             record_execution_time("cycle_times", sql, toc-tic)
#             context['time'] = f'Elapsed: {toc-tic:.3f}'

#             context['result'] = res
#             context['machine'] = machine

#             labels, counts = strokes_per_minute_chart_data(machine, shift_start.timestamp(), shift_end.timestamp(), 5 )
#             context['chartdata'] = {
#                 'labels': labels,
#                 'dataset': {'label': 'Quantity',
#                         'data': counts,
#                         'borderWidth': 1}
#             }



#     context['form'] = form
#     context['title'] = 'Production'



#     return render(request, 'prod_query/cycle_query.html', context)


def get_cycle_metrics(cycle_data):
    """
    Compute cycle metrics from a sorted list of (cycle_time, frequency).

    Args:
      cycle_data: A list of tuples (cycle_time_in_seconds, frequency),
                  sorted by ascending cycle_time.


    Returns:
      A dictionary with:
         - 'top_eight': a list of the top 8 tuples (cycle_time, frequency) sorted by frequency descending,
         - 'weighted_cycle_time': the weighted average of the top eight cycle times (rounded to 3 decimals),
         - 'histogram': the original cycle_data list.
    """
    if not cycle_data:
        return {"top_eight": [], "weighted_cycle_time": 0, "histogram": []}


    # Sort the cycle_data list by frequency in descending order (highest frequency first)
    # and then take the first 8 entries. Each entry is a tuple: (cycle_time, frequency).
    top_eight = sorted(cycle_data, key=lambda x: x[1], reverse=True)[:8]

    # Calculate the total frequency by summing the frequencies of the top eight cycle times.
    # This gives us the total count of cycles among the top eight.
    total_frequency = sum(freq for ct, freq in top_eight)

    # Calculate the weighted sum by multiplying each cycle time (ct) by its frequency (freq)
    # and then summing all these products. This sum reflects the overall 'weight' of the cycle times.
    weighted_sum = sum(ct * freq for ct, freq in top_eight)

    # Compute the weighted cycle time:
    # Divide the weighted sum by the total frequency to get the average cycle time,
    # weighted by how often each cycle time occurred.
    # Round the result to 3 decimal places.
    # If the total_frequency is zero (to avoid division by zero), return 0.
    weighted_cycle_time = round(weighted_sum / total_frequency, 3) if total_frequency else 0



    return {
        "top_eight": top_eight,
        "weighted_cycle_time": weighted_cycle_time,
        "histogram": cycle_data
    }



def fetch_cycle_data(machine, start_ts, end_ts, include_zeros, part_number):
    """
    Fetch cycle records for a machine between two timestamps and build a sorted
    list of (adjusted_cycle_time, frequency) tuples. The adjustment divides the raw
    cycle time (difference between groups of records) by the mode of the observed
    batch sizes (i.e. how many rows have the same timestamp), thereby converting the
    cycle time to a per-part value.

    Args:
        machine (str): Machine identifier.
        start_ts (int): Start timestamp.
        end_ts (int): End timestamp.
        include_zeros (bool): Whether to include cycles of 0 seconds.

    Returns:
        List[Tuple[int, int]]: Sorted list of (adjusted_cycle_time, frequency) tuples.
    """
    # Build SQL query
    if part_number:
        sql = (
            f"SELECT * "
            f"FROM GFxPRoduction "
            f"WHERE Machine = '{machine}' "
            f"AND Part = '{part_number}' "
            f"AND TimeStamp BETWEEN {start_ts} AND {end_ts} "
            f"ORDER BY TimeStamp"
    )
    else:
        sql = (
            f"SELECT * "
            f"FROM GFxPRoduction "
            f"WHERE Machine = '{machine}' "
            f"AND TimeStamp BETWEEN {start_ts} AND {end_ts} "
            f"ORDER BY TimeStamp"
        )

    # Execute the query
    cursor = connections['prodrpt-md'].cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    cursor.close()

    # Group rows by timestamp and record the batch size for each group.
    # Each group is a tuple: (timestamp, count)
    groups = []
    if rows:
        current_group_ts = rows[0][4]  # Assuming TimeStamp is at index 4
        current_group_count = 1
        for row in rows[1:]:
            ts = row[4]
            if ts == current_group_ts:
                current_group_count += 1
            else:
                groups.append((current_group_ts, current_group_count))
                # Reset for the new group.
                current_group_ts = ts
                current_group_count = 1
        # Append the final group.
        groups.append((current_group_ts, current_group_count))

    # Build a list of all batch sizes from the groups.
    batch_sizes = [count for (_, count) in groups]
    # Determine the mode (most common value) of the batch sizes.
    # This represents the typical number of parts produced per cycle.
    mode_value = Counter(batch_sizes).most_common(1)[0][0] if batch_sizes else 1

    # Compute raw cycle times from consecutive unique groups and adjust by dividing
    # by the mode_value. This gives the cycle time per part.
    times_dict = {}
    for i in range(1, len(groups)):
        # Raw cycle time is the difference between consecutive unique timestamps.
        raw_cycle = groups[i][0] - groups[i - 1][0]
        # Adjust the cycle time by the typical number of parts.
        adjusted_cycle = round(raw_cycle / mode_value)
        if include_zeros:
            if adjusted_cycle >= 0:
                times_dict[adjusted_cycle] = times_dict.get(adjusted_cycle, 0) + 1
        else:
            if adjusted_cycle > 0:
                times_dict[adjusted_cycle] = times_dict.get(adjusted_cycle, 0) + 1

    # Return the sorted list of (adjusted_cycle_time, frequency) tuples.
    return sorted(times_dict.items(), key=lambda x: x[0])

def cycle_times(request):
    context = {}
    if request.method == 'POST':
        # Capture the machine and datetime values from the request
        machine = request.POST.get('machine')
        start_datetime_str = request.POST.get('start_datetime')
        end_datetime_str = request.POST.get('end_datetime')
        part_number = request.POST.get('part_number')
        include_zeros = True  # Adjust as needed

        # Check that all required values are present
        if machine and start_datetime_str and end_datetime_str:
            # Parse the datetime strings (assuming "Y-m-d H:i" format)
            shift_start = datetime.strptime(start_datetime_str, "%Y-%m-%d %H:%M")
            shift_end = datetime.strptime(end_datetime_str, "%Y-%m-%d %H:%M")
            start_ts = int(shift_start.timestamp())
            end_ts = int(shift_end.timestamp())

            # Fetch cycle data for the shift
            res = fetch_cycle_data(machine, start_ts, end_ts, include_zeros, part_number)
            context['result'] = res
            context['machine'] = machine
            context['part_number'] = part_number
            # Pass the submitted datetime strings to the template for display
            context['start_datetime_str'] = start_datetime_str
            context['end_datetime_str'] = end_datetime_str

            # Compute cycle metrics for the shift if data exists
            if res:
                cycle_metrics = get_cycle_metrics(res)
                context['cycle_metrics'] = cycle_metrics
            else:
                context['cycle_metrics'] = None

            # Prepare ChartJS data for the histogram (bar chart)
            # Filter out cycles longer than 15 minutes (900 seconds)
            filtered_chart_data = [(ct, freq) for ct, freq in res if ct <= 900]
            chart_labels = [ct for ct, freq in filtered_chart_data]
            chart_values = [freq for ct, freq in filtered_chart_data]
            context['chartdata'] = {
                'labels': chart_labels,
                'dataset': {
                    'label': 'Cycle Occurrences',
                    'data': chart_values,
                    'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                    'borderColor': 'rgba(75, 192, 192, 1)',
                    'borderWidth': 1,
                }
            }

            # --- Now fetch data for the past year ---
            today = datetime.today().date()
            one_year_ago = today - timedelta(days=365)
            daily_dates = []
            daily_weighted_cycle = []

            # Iterate day by day over the last year
            current_day = one_year_ago
            while current_day <= today:
                day_start = datetime.combine(current_day, datetime.min.time())
                day_end = datetime.combine(current_day, datetime.max.time())
                day_start_ts = int(day_start.timestamp())
                day_end_ts = int(day_end.timestamp())

                # Fetch daily cycle data and compute metrics
                daily_data = fetch_cycle_data(machine, day_start_ts, day_end_ts, include_zeros, part_number)
                daily_metrics = get_cycle_metrics(daily_data)
                daily_wct = daily_metrics['weighted_cycle_time']

                # Compute the total occurrences for the day
                total_occurrences = sum(freq for _, freq in daily_data)
                # Include the day only if it has at least 300 total cycle occurrences
                if total_occurrences >= 300:
                    daily_dates.append(current_day.strftime("%Y-%m-%d"))
                    daily_weighted_cycle.append(daily_wct)

                current_day += timedelta(days=1)

            # Prepare ChartJS data for the yearly line chart
            context['yearly_chartdata'] = {
                'labels': daily_dates,
                'datasets': [
                    {
                        'label': 'Daily Weighted Cycle Time',
                        'data': daily_weighted_cycle,
                        'fill': False,
                        'borderColor': 'rgba(255, 99, 132, 1)',
                        'tension': 0.1,
                    },
                ]
            }
        else:
            context['error'] = "Missing machine or datetime values."

    return render(request, 'prod_query/cycle_query.html', context)



# Combined fetch data function that both views can use
def fetch_chart_data(machine, start, end, interval=5, group_by_shift=False):
    """
    Fetch chart data for a specific machine between start and end times.
    
    Parameters:
    - machine: str, identifier of the machine
    - start: int, start of the period (Unix timestamp)
    - end: int, end of the period (Unix timestamp)
    - interval: int, time interval in minutes for strokes per minute data (default is 5)
    - group_by_shift: bool, whether to group data by shift (default is False)
    
    Returns:
    - labels: list of timestamps or dates
    - data: list of counts or lists of counts for each shift
    """
    
    # Construct the SQL query based on whether data should be grouped by shift or by time intervals
    if group_by_shift:
        sql = f'SELECT DATE(FROM_UNIXTIME(TimeStamp)) as event_date, '
        sql += f'CASE '
        sql += f'WHEN HOUR(FROM_UNIXTIME(TimeStamp)) >= 7 AND HOUR(FROM_UNIXTIME(TimeStamp)) < 15 THEN "Day" '
        sql += f'WHEN HOUR(FROM_UNIXTIME(TimeStamp)) >= 15 AND HOUR(FROM_UNIXTIME(TimeStamp)) < 23 THEN "Afternoon" '
        sql += f'ELSE "Night" '
        sql += f'END AS Shift, '
        sql += f'count(*) '
        sql += f'FROM GFxPRoduction '
        sql += f'WHERE TimeStamp BETWEEN {start} AND {end} '
        sql += f'AND Machine = "{machine}" '
        sql += f'GROUP BY event_date, Shift '
        sql += f'ORDER BY event_date, Shift;'
    else:
        sql = f'SELECT DATE_ADD('
        sql += f'FROM_UNIXTIME({start}), '
        sql += f'Interval CEILING(TIMESTAMPDIFF(MINUTE, FROM_UNIXTIME({start}), '
        sql += f'FROM_UNIXTIME(TimeStamp))/{interval})*{interval} minute) as event_datetime_interval, '
        sql += f'count(*) '
        sql += f'FROM GFxPRoduction '
        sql += f'WHERE TimeStamp BETWEEN {start} AND {end} AND Machine = "{machine}" '
        sql += f'GROUP BY event_datetime_interval '
        sql += f'ORDER BY event_datetime_interval;'

    # Execute the SQL query and fetch the results
    with connections['prodrpt-md'].cursor() as c:
        c.execute(sql)
        data = c.fetchall()

    labels = []
    counts = []
    
    if group_by_shift:
        # Initialize lists for each shift
        day_counts = []
        afternoon_counts = []
        night_counts = []

        # Create an iterator for the fetched data
        data_iter = iter(data)
        row = next(data_iter, None)

        interval = 24 * 60 * 60  # Interval of 1 day

        # Iterate over each day in the specified period
        for timestamp in range(start, end, interval):
            dt = datetime.fromtimestamp(timestamp).date()

            # Initialize counts for each shift
            day_count = 0
            afternoon_count = 0
            night_count = 0

            # Accumulate counts for each shift within the current date interval
            while row and row[0] == dt:
                if row[1] == 'Day':
                    day_count = row[2]
                elif row[1] == 'Afternoon':
                    afternoon_count = row[2]
                elif row[1] == 'Night':
                    night_count = row[2]
                row = next(data_iter, None)

            # Append the results for the current date to the lists
            labels.append(dt)
            day_counts.append(day_count)
            afternoon_counts.append(afternoon_count)
            night_counts.append(night_count)
            counts.append(day_count + afternoon_count + night_count)

        return labels, day_counts, afternoon_counts, night_counts, counts
    else:
        # Create an iterator for the fetched data
        data_iter = iter(data)
        row = next(data_iter, None)
        
        # Iterate over each time interval in the specified period
        for time in range(int(start), int(end), interval * 60):
            dt = datetime.fromtimestamp(time)

            # Initialize count for the current interval
            if not row:
                row = (dt, 0)
            if row and row[0] > dt:
                labels.append(dt)
                counts.append(0)
                continue
            while row and row[0] < dt:
                row = next(data_iter, None)
            if row and row[0] == dt:
                labels.append(dt)
                counts.append(row[1] / interval)
                row = next(data_iter, None)

        return labels, counts


def prod_query(request):
    context = {}
    if request.method == 'GET':
        form = MachineInquiryForm()

    if request.method == 'POST':
        tic = time.time()

        form = MachineInquiryForm(request.POST)
        results = []

        if form.is_valid():
            # print('form valid')

            inquiry_date = form.cleaned_data.get('inquiry_date')

            times = form.cleaned_data.get('times')

            machines = form.cleaned_data.get('machines')

            machine_list = []
            for machine in machines:
                machine = machine.strip()
                machine_list.append(machine)
                machine_list.append(f'{machine}REJ')
                machine_list.append(f'{machine}AS')

            # build list of parts with quotes and commas for sql IN clause
            parts = form.cleaned_data.get('parts')

            part_list = ''
            for part in parts:
                part_list += f'"{part.strip()}", '
            part_list = part_list[:-2]

            shift_start, shift_end = shift_start_end_from_form_times(inquiry_date, times)

            shift_start_ts = datetime.timestamp(shift_start)
            
            # Initialize 'sql' to none before building it
            sql = None

            if int(times) <= 6:  # 8 hour query
                sql = 'SELECT Machine, Part, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts) + ' AND TimeStamp <= ' + \
                    str(shift_start_ts + 3600) + \
                    ' THEN 1 ELSE 0 END) as hour1, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 3600) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 7200) + \
                    ' THEN 1 ELSE 0 END) as hour2, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 7200) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 10800) + \
                    ' THEN 1 ELSE 0 END) as hour3, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 10800) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 14400) + \
                    ' THEN 1 ELSE 0 END) as hour4, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 14400) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 18000) + \
                    ' THEN 1 ELSE 0 END) as hour5, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 18000) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 21600) + \
                    ' THEN 1 ELSE 0 END) as hour6, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 21600) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 25200) + \
                    ' THEN 1 ELSE 0 END) as hour7, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts +
                                                           25200) + ' THEN 1 ELSE 0 END) AS hour8 '
                sql += 'FROM GFxPRoduction '
                sql += 'WHERE TimeStamp >= ' + \
                    str(shift_start_ts) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 28800) + ' '
                if machine:
                    sql += 'AND Machine = %s '
                if len(part_list):
                    sql += 'AND Part IN (' + part_list + ') '
                sql += 'GROUP BY Part '
                sql += 'ORDER BY Part ASC;'

            elif int(times) <= 8:  # 24 hour by shift query
                sql = 'SELECT Machine, Part, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts) + ' AND TimeStamp <= ' + \
                    str(shift_start_ts + 28800) + \
                    ' THEN 1 ELSE 0 END) as shift1, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 28800) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 57600) + \
                    ' THEN 1 ELSE 0 END) as shift2, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts +
                                                           57600) + ' THEN 1 ELSE 0 END) AS shift3 '
                sql += 'FROM GFxPRoduction '
                sql += 'WHERE TimeStamp >= ' + \
                    str(shift_start_ts) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 86400) + ' '
                if machine:
                    sql += 'AND Machine = %s '
                if len(part_list):
                    sql += 'AND Part IN (' + part_list + ') '
                sql += 'GROUP BY Part '
                sql += 'ORDER BY Part ASC;'

            elif int(times) == 9 or int(times) == 10:  # week at a time query
                sql = 'SELECT Machine, Part, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts) + ' AND TimeStamp <= ' + \
                    str(shift_start_ts + 86400) + \
                    ' THEN 1 ELSE 0 END) as mon, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 86400) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 172800) + \
                    ' THEN 1 ELSE 0 END) as tue, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 172800) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 259200) + \
                    ' THEN 1 ELSE 0 END) as wed, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 259200) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 345600) + \
                    ' THEN 1 ELSE 0 END) as thur, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 345600) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 432000) + \
                    ' THEN 1 ELSE 0 END) as fri, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 432000) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 518400) + \
                    ' THEN 1 ELSE 0 END) as sat, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + \
                    str(shift_start_ts + 518400) + \
                    ' THEN 1 ELSE 0 END) AS sun '
                sql += 'FROM GFxPRoduction '
                sql += 'WHERE TimeStamp >= ' + \
                    str(shift_start_ts) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 604800) + ' '
                if machine:
                    sql += 'AND Machine = %s '
                if len(part_list):
                    sql += 'AND Part IN (' + part_list + ') '
                sql += 'GROUP BY Part '
                sql += 'ORDER BY Part ASC;'

            elif int(times) in [11, 12]:  # Week by 8-hour shifts
                sql = 'SELECT Machine, Part, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 28800) + ' THEN 1 ELSE 0 END) as shift1, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 28800) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 57600) + ' THEN 1 ELSE 0 END) as shift2, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 57600) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 86400) + ' THEN 1 ELSE 0 END) as shift3, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 86400) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 115200) + ' THEN 1 ELSE 0 END) as shift4, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 115200) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 144000) + ' THEN 1 ELSE 0 END) as shift5, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 144000) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 172800) + ' THEN 1 ELSE 0 END) as shift6, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 172800) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 201600) + ' THEN 1 ELSE 0 END) as shift7, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 201600) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 230400) + ' THEN 1 ELSE 0 END) as shift8, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 230400) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 259200) + ' THEN 1 ELSE 0 END) as shift9, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 259200) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 288000) + ' THEN 1 ELSE 0 END) as shift10, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 288000) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 316800) + ' THEN 1 ELSE 0 END) as shift11, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 316800) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 345600) + ' THEN 1 ELSE 0 END) as shift12, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 345600) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 374400) + ' THEN 1 ELSE 0 END) as shift13, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 374400) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 403200) + ' THEN 1 ELSE 0 END) as shift14, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 403200) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 432000) + ' THEN 1 ELSE 0 END) as shift15, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 432000) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 460800) + ' THEN 1 ELSE 0 END) as shift16, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 460800) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 489600) + ' THEN 1 ELSE 0 END) as shift17, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 489600) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 518400) + ' THEN 1 ELSE 0 END) as shift18, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 518400) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 547200) + ' THEN 1 ELSE 0 END) as shift19, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 547200) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 576000) + ' THEN 1 ELSE 0 END) as shift20, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 576000) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 604800) + ' THEN 1 ELSE 0 END) as shift21 '
                sql += 'FROM GFxPRoduction '
                sql += 'WHERE TimeStamp >= ' + str(shift_start_ts) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 604800) + ' '
                if machine:
                    sql += 'AND Machine = %s '
                if len(part_list):
                    sql += 'AND Part IN (' + part_list + ') '
                sql += 'GROUP BY Part '
                sql += 'ORDER BY Part ASC;'


            # Fetch data and process results
            cursor = connections['prodrpt-md'].cursor()
            try:
                for machine in machine_list:
                    cursor.execute(sql, [machine])
                    result = cursor.fetchall()
                    for row in result:
                        machine = row[0]
                        if machine.endswith('REJ'):
                            machine = machine[:-3]
                        row = list(row)
                        row.append(sum(row[2:]))  # Calculate the total for all shifts
                        results.append(row)
            except Exception as e:
                print("Oops!", e, "occurred.")
            finally:
                cursor.close()

            # Calculate totals for each shift
            totals = [0] * (len(results[0]) - 2) if results else []  # Initialize totals list
            for row in results:
                for i, value in enumerate(row[2:], start=0):  # Start from the first shift column
                    if isinstance(value, (int, float)):
                        totals[i] += value

            # # Debug: Print totals for each shift
            # for i, total in enumerate(totals, start=1):
                # print(f"Shift {i} Total: {total}")

            # Package shifts into days if weekly shifts selected
            packaged_shifts = {}
            if int(times) in [11, 12]:  # Week by 8-hour shifts
                packaged_shifts = {
                    "Monday": totals[0:3],
                    "Tuesday": totals[3:6],
                    "Wednesday": totals[6:9],
                    "Thursday": totals[9:12],
                    "Friday": totals[12:15],
                    "Saturday": totals[15:18],
                    "Sunday": totals[18:21],
                }

            # Debug: Print the packaged shifts for each day
            # print("Packaged Shifts by Day:")
            # for day, shifts in packaged_shifts.items():
            #     print(f"{day}: {shifts}")

            # Update context
            context['packaged_shifts'] = packaged_shifts
            context['production'] = results
            context['totals'] = totals
            context['start'] = shift_start
            context['end'] = shift_end
            context['ts'] = int(shift_start_ts)
            context['times'] = int(times)
            context['is_weekly_shifts'] = int(times) in [11, 12]  # Add flag for weekly shifts

            toc = time.time()
            context['elapsed_time'] = toc - tic

    context['form'] = form

    return render(request, 'prod_query/prod_query.html', context)



def shift_start_end_from_form_times(inquiry_date, times):
    if times == '1':  # 10pm - 6am
        shift_start = datetime(
                    inquiry_date.year, inquiry_date.month, inquiry_date.day, 22, 0, 0)-timedelta(days=1)
        shift_end = shift_start + timedelta(hours=8)
    elif times == '2':  # 11pm - 7am
        shift_start = datetime(
                    inquiry_date.year, inquiry_date.month, inquiry_date.day, 23, 0, 0)-timedelta(days=1)
        shift_end = shift_start + timedelta(hours=8)
    elif times == '3':  # 6am - 2pm
        shift_start = datetime(
                    inquiry_date.year, inquiry_date.month, inquiry_date.day, 6, 0, 0)
        shift_end = shift_start + timedelta(hours=8)
    elif times == '4':  # 7am - 3pm
        shift_start = datetime(
                    inquiry_date.year, inquiry_date.month, inquiry_date.day, 7, 0, 0)
        shift_end = shift_start + timedelta(hours=8)
    elif times == '5':  # 2pm - 10pm
        shift_start = datetime(
                    inquiry_date.year, inquiry_date.month, inquiry_date.day, 14, 0, 0)
        shift_end = shift_start + timedelta(hours=8)
    elif times == '6':  # 3pm - 11pm
        shift_start = datetime(
                    inquiry_date.year, inquiry_date.month, inquiry_date.day, 15, 0, 0)
        shift_end = shift_start + timedelta(hours=8)

    elif times == '7':  # 6am - 6am
        shift_start = datetime(
                    inquiry_date.year, inquiry_date.month, inquiry_date.day, 6, 0, 0)
        shift_end = shift_start + timedelta(days=1)
    elif times == '8':  # 7am - 7am
        shift_start = datetime(
                    inquiry_date.year, inquiry_date.month, inquiry_date.day, 7, 0, 0)
        shift_end = shift_start + timedelta(days=1)

    elif times == '9':  # 11pm to 11pm week
        days_past_sunday = inquiry_date.isoweekday() % 7
        shift_start = datetime(inquiry_date.year, inquiry_date.month,
                                       inquiry_date.day, 22, 0, 0)-timedelta(days=days_past_sunday)
        shift_end = shift_start + timedelta(days=7)
    elif times == '10':  # 10pm to 10pmn week
        days_past_sunday = inquiry_date.isoweekday() % 7
        shift_start = datetime(inquiry_date.year, inquiry_date.month,
                                       inquiry_date.day, 23, 0, 0)-timedelta(days=days_past_sunday)
        shift_end = shift_start + timedelta(days=7)
    elif times == '11':  # Week by Shifts (Sunday 10pm start)
        days_past_sunday = inquiry_date.isoweekday() % 7
        shift_start = datetime(inquiry_date.year, inquiry_date.month,
                                       inquiry_date.day, 22, 0, 0)-timedelta(days=days_past_sunday)
        shift_end = shift_start + timedelta(days=7)
    elif times == '12':  # Week by Shifts (Sunday 11pm start)
        days_past_sunday = inquiry_date.isoweekday() % 7
        shift_start = datetime(inquiry_date.year, inquiry_date.month,
                                       inquiry_date.day, 23, 0, 0)-timedelta(days=days_past_sunday)
        shift_end = shift_start + timedelta(days=7)
    return shift_start,shift_end


def reject_query(request):
    context = {}
    tic = time.time()

    available_results = []
    available_sql = 'SELECT DISTINCT(CONCAT(Machine,Part)) AS cc, Part, Machine FROM 01_vw_production_rejects ORDER BY Part, Machine;'
    cursor = connections['prodrpt-md'].cursor()
    try:
        cursor.execute(available_sql)
        result = cursor.fetchall()
        for row in result:
            row = list(row[1:])
            available_results.append(row)
    except Exception as e:
        print("Oops!", e, "occurred.")
    finally:
        cursor.close()
    context['available'] = available_results

    if request.method == 'GET':
        form = MachineInquiryForm()

    if request.method == 'POST':
        tic = time.time()

        form = MachineInquiryForm(request.POST)
        results = []

        if form.is_valid():

            inquiry_date = form.cleaned_data.get('inquiry_date')
            times = form.cleaned_data.get('times')

            # build list of machines with quotes and commas
            machines = form.cleaned_data.get('machines')

            machine_list = ''
            for machine in machines:
                machine_list += f'"{machine.strip()}", '
            machine_list = machine_list[:-2]

            parts = form.cleaned_data.get('parts')

            part_list = ''
            for part in parts:
                part_list += f'"{part.strip()}", '
            part_list = part_list[:-2]

            shift_start, shift_end = shift_start_end_from_form_times(inquiry_date, times)

            shift_start_ts = datetime.timestamp(shift_start)

            if int(times) <= 6:  # 8 hour query
                sql = 'SELECT Machine, Part, Reason, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts) + ' AND TimeStamp <= ' + \
                    str(shift_start_ts + 3600) + \
                    ' THEN 1 ELSE 0 END) as hour1, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 3600) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 7200) + \
                    ' THEN 1 ELSE 0 END) as hour2, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 7200) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 10800) + \
                    ' THEN 1 ELSE 0 END) as hour3, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 10800) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 14400) + \
                    ' THEN 1 ELSE 0 END) as hour4, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 14400) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 18000) + \
                    ' THEN 1 ELSE 0 END) as hour5, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 18000) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 21600) + \
                    ' THEN 1 ELSE 0 END) as hour6, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 21600) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 25200) + \
                    ' THEN 1 ELSE 0 END) as hour7, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts +
                                                           25200) + ' THEN 1 ELSE 0 END) AS hour8 '
                sql += 'FROM `01_vw_production_rejects` '
                sql += 'WHERE TimeStamp >= ' + \
                    str(shift_start_ts) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 28800) + ' '
                if len(machine_list):
                    sql += 'AND Machine IN (' + machine_list + ') '
                if len(part_list):
                    sql += 'AND Part IN (' + part_list + ') '
                sql += 'GROUP BY Machine, Reason, Part '
                sql += 'ORDER BY Part ASC, Machine ASC, Reason ASC;'

            elif int(times) <= 8:  # 24 hour by shift query
                sql = 'SELECT Machine, Part, Reason, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts) + ' AND TimeStamp <= ' + \
                    str(shift_start_ts + 28800) + \
                    ' THEN 1 ELSE 0 END) as shift1, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 28800) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 57600) + \
                    ' THEN 1 ELSE 0 END) as shift2, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts +
                                                           57600) + ' THEN 1 ELSE 0 END) AS shift3 '
                sql += 'FROM `01_vw_production_rejects` '
                sql += 'WHERE TimeStamp >= ' + \
                    str(shift_start_ts) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 86400) + ' '
                if len(machine_list):
                    sql += 'AND Machine IN (' + machine_list + ') '
                if len(part_list):
                    sql += 'AND Part IN (' + part_list + ') '
                sql += 'GROUP BY Machine, Reason, Part '
                sql += 'ORDER BY Part ASC, Machine ASC, Reason ASC;'

            else:  # week at a time query
                sql = 'SELECT Machine, Part, Reason, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts) + ' AND TimeStamp <= ' + \
                    str(shift_start_ts + 86400) + \
                    ' THEN 1 ELSE 0 END) as mon, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 86400) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 172800) + \
                    ' THEN 1 ELSE 0 END) as tue, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 172800) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 259200) + \
                    ' THEN 1 ELSE 0 END) as wed, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 259200) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 345600) + \
                    ' THEN 1 ELSE 0 END) as thur, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 345600) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 432000) + \
                    ' THEN 1 ELSE 0 END) as fri, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + str(shift_start_ts + 432000) + \
                    ' AND TimeStamp < ' + \
                    str(shift_start_ts + 518400) + \
                    ' THEN 1 ELSE 0 END) as sat, '
                sql += 'SUM(CASE WHEN TimeStamp >= ' + \
                    str(shift_start_ts + 518400) + \
                    ' THEN 1 ELSE 0 END) AS sun '
                sql += 'FROM `01_vw_production_rejects` '
                sql += 'WHERE TimeStamp >= ' + \
                    str(shift_start_ts) + ' AND TimeStamp < ' + \
                    str(shift_start_ts + 604800) + ' '
                if len(machine_list):
                    sql += 'AND Machine IN (' + machine_list + ') '
                if len(part_list):
                    sql += 'AND Part IN (' + part_list + ') '
                sql += 'GROUP BY Machine, Reason, Part '
                sql += 'ORDER BY Part ASC, Machine ASC, Reason ASC;'

            cursor = connections['prodrpt-md'].cursor()
            print(sql)
            try:
                cursor.execute(sql)
                result = cursor.fetchall()

                for row in result:
                    row = list(row)
                    row.append(sum(row[3:]))
                    results.append(row)

            except Exception as e:
                print("Oops!", e, "occurred.")
            finally:
                cursor.close()

            context['production'] = results
            context['start'] = shift_start
            context['end'] = shift_end
            context['ts'] = shift_start_ts
            context['times'] = int(times)

            toc = time.time()
            context['elapsed_time'] = toc-tic
            logger.info(sql)
            logger.info(
                f'[{toc-tic:.3f}] machines="{machines}" parts="{parts}" times="{times}" date="{inquiry_date}" {datetime.isoformat(shift_start)} {shift_start_ts:.0f}')

    context['form'] = form
    context['title'] = 'Production'

    return render(request, 'prod_query/reject_query.html', context)


def machine_detail(request, machine, start_timestamp, times):

    tic = time.time()
    part_list = request.GET.get('parts')
    context = {}
    context['title'] = f'{machine} Detail'
    context['machine'] = machine
    context['reject_data'] = get_reject_data(
        machine, start_timestamp, times, part_list)
    
    # Remove "REJ" from machine only if it exists
    clean_machine = machine
    if "REJ" in machine:
        clean_machine = machine.replace("REJ", "")

    context['production_data'] = get_production_data(
        clean_machine, start_timestamp, times, part_list)
    context['ts'] = int(start_timestamp)
    context['times'] = int(times)
    context['elapsed'] = time.time() - tic

    if (times <= 6):
        window_length = 60*60*8
    elif (times <= 8):
        window_length = 60*60*24
    else:
        window_length = 60*60*24*7

    context['pagerprev'] = start_timestamp - window_length
    context['pagernext'] = start_timestamp + window_length
    context['start_dt'] = datetime.fromtimestamp(
        int(start_timestamp)).strftime('%Y-%m-%d %H:%M:%S')
    context['end_dt'] = datetime.fromtimestamp(
        int(start_timestamp + window_length)).strftime('%Y-%m-%d %H:%M:%S')
    
    # print(context['elapsed'])

    return render(request, 'prod_query/machine_detail.html', context)


def get_reject_data(machine, start_timestamp, times, part_list):
    if int(times) <= 6:  # 8 hour query
        sql = 'SELECT Part, Reason, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp) + ' AND TimeStamp <= ' + \
            str(start_timestamp + 3600) + ' THEN 1 ELSE 0 END) as hour1, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 3600) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 7200) + ' THEN 1 ELSE 0 END) as hour2, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 7200) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 10800) + ' THEN 1 ELSE 0 END) as hour3, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 10800) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 14400) + ' THEN 1 ELSE 0 END) as hour4, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 14400) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 18000) + ' THEN 1 ELSE 0 END) as hour5, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 18000) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 21600) + ' THEN 1 ELSE 0 END) as hour6, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 21600) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 25200) + ' THEN 1 ELSE 0 END) as hour7, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 25200) + ' THEN 1 ELSE 0 END) AS hour8 '
        sql += 'FROM `01_vw_production_rejects` '
        sql += 'WHERE TimeStamp >= ' + \
            str(start_timestamp) + ' AND TimeStamp < ' + \
            str(start_timestamp + 28800) + ' '
        if not machine.endswith("REJ"):
            machine_for_query = machine + "REJ"
        else:
            machine_for_query = machine
        sql += 'AND Machine = "' + machine_for_query + '" '

        if (part_list):
            sql += 'AND Part IN (' + part_list + ') '
        sql += 'GROUP BY Part, Reason '
        sql += 'ORDER BY Part ASC, Reason ASC;'

    elif int(times) <= 8:  # 24 hour by shift query
        sql = 'SELECT Part, Reason, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp) + ' AND TimeStamp <= ' + \
            str(start_timestamp + 28800) + ' THEN 1 ELSE 0 END) as shift1, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 28800) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 57600) + ' THEN 1 ELSE 0 END) as shift2, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 57600) + ' THEN 1 ELSE 0 END) AS shift3 '
        sql += 'FROM `01_vw_production_rejects` '
        sql += 'WHERE TimeStamp >= ' + \
            str(start_timestamp) + ' AND TimeStamp < ' + \
            str(start_timestamp + 86400) + ' '
        if not machine.endswith("REJ"):
            machine_for_query = machine + "REJ"
        else:
            machine_for_query = machine
        sql += 'AND Machine = "' + machine_for_query + '" '

        if (part_list):
            sql += 'AND Part IN (' + part_list + ') '
        sql += 'GROUP BY Part, Reason '
        sql += 'ORDER BY Part ASC, Reason ASC;'

    else:  # week at a time query
        sql = 'SELECT Part, Reason, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp) + ' AND TimeStamp <= ' + \
            str(start_timestamp + 86400) + ' THEN 1 ELSE 0 END) as mon, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 86400) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 172800) + ' THEN 1 ELSE 0 END) as tue, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 172800) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 259200) + ' THEN 1 ELSE 0 END) as wed, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 259200) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 345600) + ' THEN 1 ELSE 0 END) as thur, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 345600) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 432000) + ' THEN 1 ELSE 0 END) as fri, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 432000) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 518400) + ' THEN 1 ELSE 0 END) as sat, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + \
            str(start_timestamp + 518400) + ' THEN 1 ELSE 0 END) AS sun '
        sql += 'FROM `01_vw_production_rejects` '
        sql += 'WHERE TimeStamp >= ' + \
            str(start_timestamp) + ' AND TimeStamp < ' + \
            str(start_timestamp + 604800) + ' '
        if not machine.endswith("REJ"):
            machine_for_query = machine + "REJ"
        else:
            machine_for_query = machine
        sql += 'AND Machine = "' + machine_for_query + '" '

        if (part_list):
            sql += 'AND Part IN (' + part_list + ') '
        sql += 'GROUP BY Part, Reason '
        sql += 'ORDER BY Part ASC, Reason ASC;'

    cursor = connections['prodrpt-md'].cursor()
    # print(sql)
    try:
        cursor.execute(sql)
        result = cursor.fetchall()
        results = []
        for row in result:
            row = list(row)
            row.append(sum(row[2:]))
            results.append(row)

        if len(results):
            result_length = len(results[0])
            totals = [0] * result_length

            for row in results:
                for idx in range(2, result_length):
                    totals[idx] += row[idx]
            totals[0] = 'Totals'
            totals[1] = ''
            results.append(totals)

    except Exception as e:
        print("Oops!", e, "occurred.")
    finally:
        cursor.close()
    return results


def get_production_data(machine, start_timestamp, times, part_list):

    if int(times) <= 6:  # 8 hour query
        sql = 'SELECT Part, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp) + ' AND TimeStamp <= ' + \
            str(start_timestamp + 3600) + ' THEN 1 ELSE 0 END) as hour1, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 3600) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 7200) + ' THEN 1 ELSE 0 END) as hour2, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 7200) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 10800) + ' THEN 1 ELSE 0 END) as hour3, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 10800) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 14400) + ' THEN 1 ELSE 0 END) as hour4, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 14400) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 18000) + ' THEN 1 ELSE 0 END) as hour5, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 18000) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 21600) + ' THEN 1 ELSE 0 END) as hour6, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 21600) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 25200) + ' THEN 1 ELSE 0 END) as hour7, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp +
                                                   25200) + ' THEN 1 ELSE 0 END) AS hour8 '
        sql += 'FROM GFxPRoduction '
        sql += 'WHERE TimeStamp >= ' + \
            str(start_timestamp) + ' AND TimeStamp < ' + \
            str(start_timestamp + 28800) + ' '
        sql += 'AND Machine = "' + machine + '" '
        if (part_list):
            sql += 'AND Part IN (' + part_list + ') '
        sql += 'GROUP BY Part '
        sql += 'ORDER BY Part ASC;'

    elif int(times) <= 8:  # 24 hour by shift query
        sql = 'SELECT Part, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp) + ' AND TimeStamp <= ' + \
            str(start_timestamp + 28800) + ' THEN 1 ELSE 0 END) as shift1, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 28800) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 57600) + ' THEN 1 ELSE 0 END) as shift2, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp +
                                                   57600) + ' THEN 1 ELSE 0 END) AS shift3 '
        sql += 'FROM GFxPRoduction '
        sql += 'WHERE TimeStamp >= ' + \
            str(start_timestamp) + ' AND TimeStamp < ' + \
            str(start_timestamp + 86400) + ' '
        sql += 'AND Machine = "' + machine + '" '
        if (part_list):
            sql += 'AND Part IN (' + part_list + ') '
        sql += 'GROUP BY Part '
        sql += 'ORDER BY Part ASC;'

    else:  # week at a time query
        sql = 'SELECT Part, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp) + ' AND TimeStamp <= ' + \
            str(start_timestamp + 86400) + ' THEN 1 ELSE 0 END) as mon, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 86400) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 172800) + ' THEN 1 ELSE 0 END) as tue, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 172800) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 259200) + ' THEN 1 ELSE 0 END) as wed, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 259200) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 345600) + ' THEN 1 ELSE 0 END) as thur, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 345600) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 432000) + ' THEN 1 ELSE 0 END) as fri, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + str(start_timestamp + 432000) + \
            ' AND TimeStamp < ' + \
            str(start_timestamp + 518400) + ' THEN 1 ELSE 0 END) as sat, '
        sql += 'SUM(CASE WHEN TimeStamp >= ' + \
            str(start_timestamp + 518400) + ' THEN 1 ELSE 0 END) AS sun '
        sql += 'FROM GFxPRoduction '
        sql += 'WHERE TimeStamp >= ' + \
            str(start_timestamp) + ' AND TimeStamp < ' + \
            str(start_timestamp + 604800) + ' '
        sql += 'AND Machine = "' + machine + '" '
        if (part_list):
            sql += 'AND Part IN (' + part_list + ') '
        sql += 'GROUP BY Part '
        sql += 'ORDER BY Part ASC;'

    results = []
    cursor = connections['prodrpt-md'].cursor()
    try:
        cursor.execute(sql)
        result = cursor.fetchall()
        for row in result:
            row = list(row)
            row.append(sum(row[1:]))
            results.append(row)

    except Exception as e:
        print("Oops!", e, "occurred.")
    finally:
        cursor.close()

    return results



# #views.py


def fetch_shift_totals_by_day_and_shift(machine_number, start_date, end_date):
    """
    Fetch production totals by day and shift for a specific machine.
    
    Parameters:
    - machine_number: str, identifier of the machine
    - start_date: datetime, start of the period to fetch data for
    - end_date: datetime, end of the period to fetch data for
    
    Returns:
    - labels: list of dates
    - day_counts: list of counts for day shift
    - afternoon_counts: list of counts for afternoon shift
    - night_counts: list of counts for night shift
    - total_counts: list of total counts per day
    """

    # Convert datetime objects to Unix timestamps
    start_stamp = int(time.mktime(start_date.timetuple()))
    end_stamp = int(time.mktime(end_date.timetuple()))

    # SQL query to fetch production counts grouped by date and shift
    sql  = f'SELECT DATE(FROM_UNIXTIME(TimeStamp)) as event_date, '
    sql += f'CASE '
    sql += f'WHEN HOUR(FROM_UNIXTIME(TimeStamp)) >= 7 AND HOUR(FROM_UNIXTIME(TimeStamp)) < 15 THEN "Day" '
    sql += f'WHEN HOUR(FROM_UNIXTIME(TimeStamp)) >= 15 AND HOUR(FROM_UNIXTIME(TimeStamp)) < 23 THEN "Afternoon" '
    sql += f'ELSE "Night" '
    sql += f'END AS Shift, '
    sql += f'count(*) '
    sql += f'FROM GFxPRoduction '
    sql += f'WHERE TimeStamp BETWEEN {start_stamp} AND {end_stamp} '
    sql += f'AND Machine = "{machine_number}" '
    sql += f'GROUP BY event_date, Shift '
    sql += f'ORDER BY event_date, Shift;'

    # Execute the SQL query using the specified database connection
    with connections['prodrpt-md'].cursor() as c:
        c.execute(sql)
        data = c.fetchall()

    # Initialize lists to store results
    labels = []
    day_counts = []
    afternoon_counts = []
    night_counts = []
    total_counts = []

    # Create an iterator for the fetched data
    data_iter = iter(data)
    row = next(data_iter, None)

    interval = 24 * 60 * 60 # Interval of 1 day

    # Iterate over each day in the specified period
    for timestamp in range(start_stamp, end_stamp, interval):  # Interval of 1 day
        dt = datetime.fromtimestamp(timestamp).date()  # Convert timestamp to date

        # Initialize counts for each shift
        day_count = 0
        afternoon_count = 0
        night_count = 0

        # Accumulate counts for each shift within the current date interval
        while row and row[0] == dt:
            if row[1] == 'Day':
                day_count = row[2]
            elif row[1] == 'Afternoon':
                afternoon_count = row[2]
            elif row[1] == 'Night':
                night_count = row[2]
            row = next(data_iter, None)

        # Append the results for the current date to the lists
        labels.append(dt)
        day_counts.append(day_count)
        afternoon_counts.append(afternoon_count)
        night_counts.append(night_count)
        total_counts.append(day_count + afternoon_count + night_count)

    return labels, day_counts, afternoon_counts, night_counts, total_counts


def moving_average(data, window_size):
    """
    Calculate the moving average of a list of numbers.
    
    Parameters:
    - data: list of numbers
    - window_size: int, size of the moving average window
    
    Returns:
    - list of moving average values
    """
    return np.convolve(data, np.ones(window_size) / window_size, mode='valid').tolist()



# Updated shift_totals_view view
def shift_totals_view(request):
    context = {'form': ShiftTotalsForm()}
    if request.method == 'POST':
        form = ShiftTotalsForm(request.POST)
        if form.is_valid():
            machine_numbers = form.cleaned_data['machine_number'].split(',')
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']

            chartdata = []
            for machine_number in machine_numbers:
                machine_number = machine_number.strip()
                labels, day_counts, afternoon_counts, night_counts, total_counts = fetch_chart_data(
                    machine_number, int(time.mktime(start_date.timetuple())), int(time.mktime(end_date.timetuple())), group_by_shift=True)

                window_size = 7
                moving_avg = moving_average(total_counts, window_size)
                avg_labels = labels[window_size - 1:]

                chartdata.append({
                    'machine_number': machine_number,
                    'labels': labels,
                    'datasets': [
                        {'label': 'Day Shift', 'data': day_counts, 'borderWidth': 1, 'borderColor': 'rgba(255, 99, 132, 1)'},
                        {'label': 'Afternoon Shift', 'data': afternoon_counts, 'borderWidth': 1, 'borderColor': 'rgba(54, 162, 235, 1)'},
                        {'label': 'Night Shift', 'data': night_counts, 'borderWidth': 1, 'borderColor': 'rgba(75, 192, 192, 1)'},
                        {'label': 'Total', 'data': total_counts, 'borderWidth': 2, 'borderColor': 'rgba(0, 0, 0, 1)', 'borderDash': [5, 5]}
                    ],
                    'moving_avg': {
                        'labels': avg_labels,
                        'data': moving_avg
                    }
                })

            context.update({
                'form': form,
                'chartdata': chartdata
            })
        else:
            print("Form is invalid")
    return render(request, 'prod_query/shift_totals.html', context)











# ===================================================================
# ===================================================================
# ==================  SC Production Tool ============================
# ===================================================================
# ===================================================================


from django.shortcuts import render
from datetime import datetime
from collections import defaultdict
import MySQLdb

def get_sc_production_data(request):
    context = {}

    if request.method == 'POST':
        asset_num = request.POST.get('asset_num')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')

        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')

        db = MySQLdb.connect(
            host="10.4.1.224",
            user="stuser",
            passwd="stp383",
            db="prodrptdb"
        )
        
        cursor = db.cursor()

        query = f"""
            SELECT pdate, actual_produced, shift
            FROM sc_production1
            WHERE asset_num = {asset_num}
            AND pdate BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY pdate ASC;
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()

        cursor.close()
        db.close()

        # Initialize dictionary to store shift totals and grand totals by day
        daily_data = defaultdict(lambda: {'7am-3pm': 0, '3pm-11pm': 0, '11pm-7am': 0, 'grand_total': 0})

        for row in rows:
            pdate, actual_produced, shift = row
            daily_data[pdate][shift] += actual_produced
            daily_data[pdate]['grand_total'] += actual_produced

        # Prepare data for Chart.js
        labels = [day.strftime('%Y-%m-%d') for day in daily_data.keys()]
        data_by_shift = {
            '7am-3pm': [daily_data[day]['7am-3pm'] for day in daily_data],
            '3pm-11pm': [daily_data[day]['3pm-11pm'] for day in daily_data],
            '11pm-7am': [daily_data[day]['11pm-7am'] for day in daily_data],
            'grand_total': [daily_data[day]['grand_total'] for day in daily_data]
        }

        context.update({
            'labels': labels,
            'data_by_shift': data_by_shift,
            'asset_num': asset_num,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'show_chart': True  # Flag to show the chart
        })

    return render(request, 'prod_query/sc_production.html', context)



# ===================================================================
# ===================================================================
# ==================  SC Production ToolV2 ==========================
# ===================================================================
# ===================================================================


from django.http import JsonResponse
from django.shortcuts import render
from datetime import datetime, timedelta
import MySQLdb

def get_sc_production_data_v2(request):
    if request.method == 'POST':
        asset_num = request.POST.get('asset_num')
        selected_date = request.POST.get('selected_date')

        # Convert the selected date and find the Sunday of that week
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d')
        start_of_week = selected_date - timedelta(days=selected_date.weekday() + 1)  # Find the previous Sunday

        # The production starts from Sunday at 11pm-7am shift (so the actual production start time is 11pm Sunday)
        start_date = start_of_week + timedelta(hours=23)  # Sunday at 11pm
        end_date = start_date + timedelta(days=6, hours=23)  # End date is Saturday at 11pm

        # Connect to the database
        db = MySQLdb.connect(
            host="10.4.1.224",
            user="stuser",
            passwd="stp383",
            db="prodrptdb"
        )
        
        cursor = db.cursor()

        # Query to get the production data for the entire week starting from Sunday 11pm
        query = f"""
            SELECT pdate, actual_produced, shift
            FROM sc_production1
            WHERE asset_num = {asset_num}
            AND pdate BETWEEN '{start_date.strftime('%Y-%m-%d %H:%M:%S')}' AND '{end_date.strftime('%Y-%m-%d %H:%M:%S')}'
            ORDER BY pdate ASC;
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()

        cursor.close()
        db.close()

        # Prepare the labels and data for Chart.js
        shift_intervals = ['7am-3pm', '3pm-11pm', '11pm-7am']
        labels = []  # To store shift + date labels (e.g., '2024-10-09 7am-3pm')
        totals = []  # To store the actual production totals for each shift

        # Initialize the dictionary for shift totals
        current_day = start_date.date()  # Only consider the date part for day changes
        daily_data = {shift: 0 for shift in shift_intervals}  # Store totals for each shift per day

        for row in rows:
            pdate, actual_produced, shift = row

            # No need for .date() since pdate is already a date object
            row_date = pdate

            # Check if the day changes, if yes, append the totals for the previous day
            if row_date != current_day:
                for shift_interval in shift_intervals:
                    if not (current_day == start_of_week.date() and shift_interval in ['7am-3pm', '3pm-11pm']):
                        labels.append(f"{current_day.strftime('%Y-%m-%d')} {shift_interval}")
                        totals.append(daily_data[shift_interval])
                
                current_day = row_date  # Move to the new day
                daily_data = {shift: 0 for shift in shift_intervals}  # Reset for the new day

            # Add the production data to the correct shift
            daily_data[shift] += actual_produced

        # Append data for the final day
        for shift_interval in shift_intervals:
            if not (current_day == start_of_week.date() and shift_interval in ['7am-3pm', '3pm-11pm']):
                labels.append(f"{current_day.strftime('%Y-%m-%d')} {shift_interval}")
                totals.append(daily_data[shift_interval])

        # Return the data as JSON
        return JsonResponse({
            'selected_date': selected_date.strftime('%Y-%m-%d'),
            'labels': labels,
            'totals': totals
        })

    # If it's a GET request, render the form page
    return render(request, 'prod_query/sc_production_v2.html')





# ========================================================
# ========================================================
# =================== OA Display =========================
# ========================================================
# ========================================================



# Define lines object
lines = [
    {
        "line": "AB1V Reaction",
        "scrap_line": "AB1V Reaction",
        "operations": [
            {
                "op": "10",
                "machines": [
                    {"number": "1703R", "target": 1925},
                    {"number": "1704R", "target": 1925},
                    {"number": "616", "target": 1050},
                    {"number": "623", "target": 1050},
                    {"number": "617", "target": 1050},
                ],
            },
            {
                "op": "50",
                "machines": [
                    {"number": "659", "target": 4200},
                    {"number": "626", "target": 2800},
                ],
            },
            {
                "op": "60",
                "machines": [
                    {"number": "1712", "target": 7000},
                ],
            },
            {
                "op": "70",
                "machines": [
                    {"number": "1716L", "target": 7000},
                ],
            },
            {
                "op": "90",
                "machines": [
                    {"number": "1723", "target": 7000, "part_numbers": ["50-0450", "50-8670"]
                    }
                ]
            }

        ],
    },
        {
        "line": "AB1V Input",
        "scrap_line": "AB1V Input",
        "operations": [
            {
                "op": "10",
                "machines": [
                    {"number": "1740L", "target": 3500},
                    {"number": "1740R", "target": 3500},
                ],
            },
            {
                "op": "40",
                "machines": [
                    {"number": "1701L", "target": 3500},
                    {"number": "1701R", "target": 3500},
                ],
            },
            {
                "op": "50",
                "machines": [
                    {"number": "733", "target": 7000},
                ],
            },
            {
                "op": "60",
                "machines": [
                    {"number": "775", "target": 3500},
                    {"number": "1702", "target": 3500},
                ],
            },
            {
                "op": "70",
                "machines": [
                    {"number": "581", "target": 3500},
                    {"number": "788", "target": 3500},
                ],
            },
            {
                "op": "80",
                "machines": [
                    {"number": "1714", "target": 7000},
                ],
            },
            {
                "op": "90",
                "machines": [
                    {"number": "1717L", "target": 7000},
                ],
            },
            {
                "op": "100",
                "machines": [
                    {"number": "1706", "target": 7000},
                ],
            },
            {
                "op": "110",
                "machines": [
                    {"number": "1723", "target": 7000, "part_numbers": ["50-0447", "50-5401"]
                    }
                ]
            }

        ],
    },
        {
        "line": "AB1V Overdrive",
        "scrap_line": "AB1V Overdrive Gas",
        "operations": [
            {
                "op": "20",
                "machines": [
                    {"number": "1705L", "target": 3500},
                    {"number": "1746R", "target": 3500},
                ],
            },
            {
                "op": "25",
                "machines": [
                    {"number": "621", "target": 3500},
                    {"number": "629", "target": 3500},
                ],
            },
            {
                "op": "30",
                "machines": [
                    {"number": "785", "target": 700},
                    {"number": "1748", "target": 3150},
                    {"number": "1718", "target": 3150},
                ],
            },
            {
                "op": "35",
                "machines": [
                    {"number": "669", "target": 7000},
                ],
            },
            {
                "op": "40",
                "machines": [
                    {"number": "1726", "target": 7000},
                ],
            },
            {
                "op": "50",
                "machines": [
                    {"number": "1722", "target": 7000},
                ],
            },
            {
                "op": "60",
                "machines": [
                    {"number": "1713", "target": 7000},
                ],
            },
            {
                "op": "70",
                "machines": [
                    {"number": "1716R", "target": 7000},
                ],
            },
            {
                "op": "90",
                "machines": [
                    {"number": "1723", "target": 7000, "part_numbers": ["50-0519", "50-5404"]
                    }
                ]
            }

        ],
    },
       {
        "line": "10R80",
        "scrap_line": "10R80",
        "operations": [
            {
                "op": "10",
                "machines": [
                    {"number": "1504", "target": 6187},  
                    {"number": "1506", "target": 6187},  
                    {"number": "1519", "target": 5625},  
                    {"number": "1520", "target": 5625},
                    {"number": "1518", "target": 5625},  
                    {"number": "1521", "target": 5625},  
                    {"number": "1522", "target": 6187}, 
                    {"number": "1523", "target": 5625}, 
                ],
            },
            {
                "op": "30",
                "machines": [
                    {"number": "1502", "target": 11250}, 
                    {"number": "1507", "target": 11250},  
                    {"number": "1539", "target": 11250}, 
                    {"number": "1540", "target": 11250}, 
                ],
            },
            {
                "op": "40",
                "machines": [
                    {"number": "1501", "target": 11250},  
                    {"number": "1515", "target": 11250},  
                    {"number": "1524", "target": 11250}, 
                    {"number": "1525", "target": 11250}, 
                ],
            },
            {
                "op": "50",
                "machines": [
                    {"number": "1508", "target": 13500},  
                    {"number": "1532", "target": 15750},  
                    {"number": "1538", "target": 15750}, 
                ],
            },
            {
                "op": "60",
                "machines": [
                    {"number": "1509", "target": 22500},  
                    {"number": "1541", "target": 22500}, 
                ],
            },
            {
                "op": "70",
                "machines": [
                    {"number": "1514", "target": 22500}, 
                    {"number": "1531", "target": 22500}, 
                ],
            },
            {
                "op": "80",
                "machines": [
                    {"number": "1510", "target": 22500},  
                    {"number": "1527", "target": 22500}, 
                ],
            },
            {
                "op": "90",
                "machines": [
                    {"number": "1513", "target": 45000}, 
                ],
            },
            {
                "op": "100",
                "machines": [
                    {"number": "1503", "target": 22500},  
                    {"number": "1530", "target": 22500}, 
                ],
            },
            {
                "op": "110",
                "machines": [
                    {"number": "1511", "target": 22500},
                    {"number": "1528", "target": 22500},  
                ],
            },
            {
                "op": "120",
                "machines": [
                    {"number": "1533", "target": 45000}, 
                ],
            },
        ],
    },
 {
        "line": "10R60",
        "scrap_line": "10R60",
        "operations": [
            {
                "op": "10",
                "machines": [
                    {"number": "1800", "target": 5918},
                    {"number": "1801", "target": 5918},
                    {"number": "1802", "target": 5072},
                ],
            },
            {
                "op": "30",
                "machines": [
                    {"number": "1529", "target": 4227},
                    {"number": "776", "target": 4227},
                    {"number": "1824", "target": 4227},
                    {"number": "1543", "target": 4227},
                ],
            },
            {
                "op": "40",
                "machines": [
                    {"number": "1804", "target": 8454},
                    {"number": "1805", "target": 8454},
                ],
            },
            {
                "op": "50",
                "machines": [
                    {"number": "1806", "target": 16908},
                ],
            },
            {
                "op": "60",
                "machines": [
                    {"number": "1808", "target": 16908},
                ],
            },
            {
                "op": "70",
                "machines": [
                    {"number": "1810", "target": 16908},
                ],
            },
            {
                "op": "80",
                "machines": [
                    {"number": "1815", "target": 16908},
                ],
            },
            {
                "op": "90",
                "machines": [
                    {"number": "1542", "target": 16908},
                ],
            },
            {
                "op": "100",
                "machines": [
                    {"number": "1812", "target": 1908},
                ],
            },
                        {
                "op": "110",
                "machines": [
                    {"number": "1813", "target": 16908},
                ],
            },
                        {
                "op": "120",
                "machines": [
                    {"number": "1816", "target": 16908},
                ],
            },
        ],
    },
    {
        "line": "10R140",
        "scrap_line": "10R140",
        "operations": [
            {
                "op": "10",
                "machines": [
                    {"number": "1708L", "target": 3600},
                    {"number": "1708R", "target": 3600},
                ],
            },
            # {
            #     "op": "20",
            #     "machines": [
            #         {"number": "1709", "target": 4227},
            #     ],
            # },
            {
                "op": "30",
                "machines": [
                    {"number": "1710", "target": 7200},
                ],
            },
            {
                "op": "40",
                "machines": [
                    {"number": "1711", "target": 7200},
                ],
            },
            {
                "op": "50",
                "machines": [
                    {"number": "1715", "target": 7200},
                ],
            },
            {
                "op": "60",
                "machines": [
                    {"number": "1717R", "target": 7200},
                ],
            },
            {
                "op": "70",
                "machines": [
                    {"number": "1706", "target": 5000},
                ],
            },
            {
                "op": "80",
                "machines": [
                    {"number": "1720", "target": 5000},
                ],
            },
            {
                "op": "90",
                "machines": [
                    {"number": "748", "target": 5000},
                    {"number": "677", "target": 5000},
                ],
            },
                        {
                "op": "100",
                "machines": [
                    {"number": "1723", "target": 7200, "part_numbers": ["50-0519", "50-5404"]},
                ],
            },
                        {
                "op": "110",
                "machines": [
                    {"number": "1752", "target": 7200},
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
                    {"number": "272", "target": 27496,},
                    {"number": "273", "target": 29592,},
                    {"number": "277", "target": 57600,},
                    {"number": "278", "target": 43116,},
                    {"number": "262", "target": 43711,},
                    {"number": "240", "target": 59659,},
                    {"number": "280", "target": 49888,},
                    {"number": "242", "target": 53355,},
                    {"number": "245", "target": 50000,},
                ],
            },
        ],
    },

]


# Updated Mapping of machine numbers to downtime thresholds
MACHINE_THRESHOLDS = {
    '1703R': 5, '1703L': 5, '1704R': 5, '1704L': 5,
    '616': 5, '623': 5, '617': 5, '659': 5,
    '626': 5, '1712': 5, '1716L': 5, '1716R': 5, '1723': 5,
    '1800': 5, '1801': 5, '1802': 5, '534': 5,
    '1529': 5, '776': 5, '1824': 5, '1543': 5,
    '1804': 5, '1805': 5, '1806': 5, '1808': 5,
    '1810': 5, '1815': 5, '1542': 5, '1812': 5,
    '1813': 5, '1816': 5, '810': 5,
    '1740L': 5, '1740R': 5, '1701L': 5, '1701R': 5,
    '733': 5, '775': 5, '1702': 5, '581': 5,
    '788': 5, '1714': 5, '1717L': 5, '1706': 5,
    '1724': 5, '1725': 5, '1750': 5,
    '1705': 5, '1746': 5, '621': 5, '629': 5,
    '785': 5, '1748': 5, '1718': 5, '669': 5,
    '1726': 5, '1722': 5, '1713': 5, '1719': 5,
    '1504': 5, '1506': 5, '1519': 5, '1520': 5,
    '1502': 5, '1507': 5, '1501': 5, '1515': 5,
    '1508': 5, '1532': 5, '1509': 5, '1514': 5,
    '1510': 5, '1513': 5, '1503': 5, '1511': 5,
    '1533': 5, '1518': 5, '1521': 5, '1522': 5,
    '1523': 5, '1539': 5, '1540': 5, '1524': 5,
    '1525': 5, '1538': 5, '1541': 5, '1531': 5,
    '1527': 5, '1530': 5, '1528': 5, '1546': 5,
    '1547': 5, '1548': 5, '1549': 5, '594': 5,
    '1551': 5, '1552': 5, '751': 5, '1554': 5,
    '272': 5, '273': 5, '277': 5, '278': 5,
    '262': 5, '240': 5, '280': 5, '242': 5,
    '1705L': 5, '1705R': 5, '1746L': 5, '1746R': 5,
}


# View for rendering the template
def oa_display(request):
    return render(request, 'prod_query/oa_display.html')

# View for providing machine data
def get_machine_data(request):
    # Prepare machine targets and line-to-machine mapping dynamically
    machine_targets = {}
    line_mapping = {}

    for line in lines:
        line_name = line["line"]
        line_mapping[line_name] = []
        for operation in line["operations"]:
            for machine in operation["machines"]:
                machine_number = machine["number"]
                target = machine["target"]
                machine_targets[machine_number] = target
                line_mapping[line_name].append(machine_number)

    return JsonResponse({
        'machine_targets': machine_targets,
        'line_mapping': line_mapping
    })




# ======================================
# ========= GFX Downtime Delta =========
# ======================================

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import time  # Import the time module
from .useful_functions import *
from django.utils import timezone  # Import Django's timezone utilities
import pytz  # If using pytz for timezone handling
from django.db.models import Max
from .models import OAMachineTargets


@csrf_exempt
def gfx_downtime_and_produced_view(request):
    """
    POST Parameters expected:
      - machines: JSON list of machine numbers (e.g. ["1723", "1703R", ...])
      - line: The name of the line (e.g. "AB1V Reaction")
      - start_date: ISO8601 date string (UTC or including "Z")
    
    1) Validates the request and converts start_date to EST.
    2) Determines end_date (start_date + 5 days or now, whichever is earlier).
    3) Converts both start/end to timestamps in EST.
    4) Dynamically looks up part numbers for each machine based on the given line, 
       storing them in a dictionary: machine_parts[machine_id] = [part_1, part_2, ...].
    5) Fetches the “most recent target” for each machine from the database 
       (table: OAMachineTargets) as of that start_date.
    6) Calls your existing calculate_downtime(...) and calculate_total_produced(...)
       for each machine, passing the relevant part numbers to calculate_total_produced.
    7) Scales the machine targets for the partial week and returns all data as JSON.
    """
    if request.method == "POST":
        start_time = time.time()  # Record the start time
        
        try:
            # 1. Parse input data
            machines = json.loads(request.POST.get('machines', '[]'))
            line_name = request.POST.get('line')  # The line name
            start_date_str = request.POST.get('start_date')

            # Basic validation
            if not machines:
                return JsonResponse({'error': 'No machine numbers provided'}, status=400)
            if not start_date_str:
                return JsonResponse({'error': 'Start date is required.'}, status=400)
            if not line_name:
                return JsonResponse({'error': 'Line is required.'}, status=400)

            # 2. Parse and validate start_date (making it timezone-aware in EST)
            try:
                if start_date_str.endswith('Z'):
                    # Convert trailing 'Z' to '+00:00' if needed
                    start_date_str = start_date_str.replace('Z', '+00:00')
                start_date = datetime.fromisoformat(start_date_str)

                # If no timezone, assume it's UTC and make it aware
                if start_date.tzinfo is None:
                    start_date = timezone.make_aware(start_date, timezone=timezone.utc)

                # Convert to EST
                est_timezone = pytz.timezone('America/New_York')
                start_date_est = start_date.astimezone(est_timezone)

                # end_date = min( (start_date + 5 days), now )
                end_date_candidate = start_date_est + timedelta(days=5)
                now_est = timezone.now().astimezone(est_timezone)
                end_date_est = min(end_date_candidate, now_est)
            except ValueError:
                print(f"Invalid start date format: {start_date_str}")
                return JsonResponse({'error': 'Invalid start date format.'}, status=400)

            # Convert these to timestamps in EST
            start_timestamp = int(start_date_est.timestamp())
            end_timestamp = int(end_date_est.timestamp())

            # 3. Calculate total potential minutes
            total_potential_minutes_per_machine = (end_timestamp - start_timestamp) / 60.0

            # 4. Look up line-specific part numbers for each machine
            machine_parts = {}  # { "1723": ["50-0450","50-8670"], ... }
            matching_line = next((l for l in lines if l["line"] == line_name), None)
            if matching_line:
                # For each operation in this line, capture part_numbers for the machines in 'machines'
                for operation in matching_line["operations"]:
                    for m in operation["machines"]:
                        m_num = m["number"]
                        if m_num in machines:
                            # If the JSON has a "part_numbers" key, use it; else default to []
                            part_nums = m.get("part_numbers", [])
                            machine_parts[m_num] = part_nums
            else:
                # If line not found, machine_parts stays empty -> produced will be 0
                pass

            # 5. Query the DB for machine targets for the selected line
            machine_targets = {}
            for machine in machines:
                most_recent_target = (
                    OAMachineTargets.objects.filter(
                        machine_id=machine,
                        line=line_name,
                        effective_date_unix__lte=start_timestamp
                    )
                    .order_by('-effective_date_unix')
                    .first()
                )

                if most_recent_target:
                    machine_targets[machine] = most_recent_target.target
                else:
                    machine_targets[machine] = 0  # Default to 0 if no target found

            # 6. Loop over machines, compute downtime and produced
            downtime_results = []
            produced_results = []
            total_downtime = 0
            total_produced = 0

            with connections['prodrpt-md'].cursor() as cursor:
                for machine in machines:
                    # Downtime threshold from your dict, default 5
                    downtime_threshold = MACHINE_THRESHOLDS.get(machine, 5)

                    # a) calculate_downtime
                    #    (If you also want downtime to filter by part, pass machine_parts[machine] instead of None)
                    machine_downtime = calculate_downtime(
                        machine=machine,
                        cursor=cursor,
                        start_timestamp=start_timestamp,
                        end_timestamp=end_timestamp,
                        downtime_threshold=downtime_threshold,
                        machine_parts=None  # or machine_parts.get(machine, [])
                    )
                    downtime_results.append({'machine': machine, 'downtime': machine_downtime})
                    total_downtime += machine_downtime

                    # b) calculate_total_produced (pass the part numbers if present)
                    relevant_parts = machine_parts.get(machine, [])
                    machine_total_produced = calculate_total_produced(
                        machine=machine,
                        machine_parts=relevant_parts,
                        start_timestamp=start_timestamp,
                        end_timestamp=end_timestamp,
                        cursor=cursor
                    )
                    produced_results.append({'machine': machine, 'produced': machine_total_produced})
                    total_produced += machine_total_produced

            # 7. Prepare scaled/adjusted targets per machine
            adjusted_machine_targets = {}
            # 7200 minutes in a full week (12x5 shifts or 24x5 days, etc. in your logic)
            full_week_minutes = 7200
            scaling_factor = total_potential_minutes_per_machine / full_week_minutes

            for machine in machines:
                original_target = machine_targets.get(machine, 0)
                adjusted_original_target = original_target * scaling_factor
                adjusted_machine_targets[machine] = {
                    'original_target': original_target,
                    'adjusted_original_target': adjusted_original_target
                }

            # 8. Build final JSON response
            end_time = time.time()
            elapsed_time = end_time - start_time
            print(f"Processing complete. Total elapsed time: {elapsed_time:.2f} seconds.")

            return JsonResponse({
                'downtime_results': downtime_results,
                'total_downtime': total_downtime,
                'produced_results': produced_results,
                'total_produced': total_produced,
                'total_potential_minutes_per_machine': total_potential_minutes_per_machine,
                'elapsed_time': f"{elapsed_time:.2f} seconds",
                'machine_targets': adjusted_machine_targets,
                'start_date': start_date_est.strftime('%Y-%m-%d %H:%M:%S %Z'),  # Formatted EST start date
                'end_date': end_date_est.strftime('%Y-%m-%d %H:%M:%S %Z')       # Formatted EST end date
            })

        except Exception as e:
            # Catch any unhandled exceptions
            print(f"Unhandled error in gfx_downtime_and_produced_view: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)

    # If GET or another method, return a simple message
    return JsonResponse({'message': 'Send machine details via POST'}, status=200)



# ======================================
# ========= PR Downtime  ===============
# ======================================


# JSON map for machine numbers to pr_downtime1 machines (assetnums)
MACHINE_MAP = {
    "1703R": "1703",
    "1704R": "1704",
    "1740L": "1740",
    "1740R": "1740",
    "1701L": "1701",
    "1701R": "1701",
    "1717L": "1717",
    "1716L": "1716",
    "1705L": "1705",
    "1746R": "1746",
    "1716R": "1716",
    "1708L": "1708",
    "1708R": "1708",
    "1717R": "1717",
    "machine3": "prdowntime_machine3",
    # Add more mappings as needed
}

from .useful_functions import fetch_prdowntime1_entries

def pr_downtime_view(request):
    try:
        default_numGraphPoints = 250  # Set default number of graph points
        
        # Extract parameters from the request
        assetnum = request.GET.get('assetnum')
        called4helptime = request.GET.get('called4helptime')
        completedtime = request.GET.get('completedtime')

        # Validate input
        if not all([assetnum, called4helptime, completedtime]):
            return JsonResponse({"error": "Missing required parameters"}, status=400)

        # Map assetnum to the TKB machine, or use assetnum directly
        mapped_assetnum = MACHINE_MAP.get(assetnum, assetnum)

        # Parse incoming time strings into datetime objects
        est = pytz.timezone('US/Eastern')
        try:
            called4helptime_dt = datetime.strptime(called4helptime, "%Y-%m-%d %H:%M:%S %Z").astimezone(est)
            completedtime_dt = datetime.strptime(completedtime, "%Y-%m-%d %H:%M:%S %Z").astimezone(est)
        except Exception as e:
            return JsonResponse({"error": f"Invalid date format: {e}"}, status=400)

        # Convert datetimes to Unix timestamps
        start_timestamp = int(time.mktime(called4helptime_dt.timetuple()))
        end_timestamp = int(time.mktime(completedtime_dt.timetuple()))

        # Calculate the total duration in minutes
        total_minutes = (completedtime_dt - called4helptime_dt).total_seconds() / 60

        # Calculate the interval to display default_numGraphPoints points
        interval = max(int(total_minutes / default_numGraphPoints), 1)

        # Fetch downtime data
        data = fetch_prdowntime1_entries(mapped_assetnum, called4helptime_dt.isoformat(), completedtime_dt.isoformat())

        # Fetch chart data for Strokes Per Minute
        labels, counts = fetch_chart_data(
            machine=mapped_assetnum,
            start=start_timestamp,
            end=end_timestamp,
            interval=interval,
            group_by_shift=False
        )
        
        # Prepare chart data for JSON serialization
        chart_labels = [dt.isoformat() if isinstance(dt, datetime) else dt for dt in labels]

        # Serialize downtime data
        serialized_data = [
            {
                "problem": entry[0],
                "called4helptime": entry[1].isoformat() if entry[1] else None,
                "completedtime": entry[2].isoformat() if entry[2] else None,
            }
            for entry in data
        ]

        return JsonResponse({
            "data": serialized_data,
            "chart_data": {
                "labels": chart_labels,
                "counts": counts
            }
        }, safe=False)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)





# ======================================
# ========= Total Scrap ================
# ======================================


from django.http import JsonResponse

def total_scrap_view(request):
    try:
        # Extract and validate GET parameters
        scrap_line = request.GET.get('scrap_line')
        start_date_str = request.GET.get('start_date')

        if not scrap_line:
            return JsonResponse({'error': "Scrap line is required."}, status=400)

        if not start_date_str:
            return JsonResponse({'error': "Start date is required."}, status=400)

        try:
            # Handle ISO format with UTC 'Z'
            if start_date_str.endswith('Z'):
                start_date_str = start_date_str.replace('Z', '+00:00')
            
            start_date = datetime.fromisoformat(start_date_str)
            end_date = start_date + timedelta(days=5)
        except Exception:
            return JsonResponse({'error': "Invalid start date format."}, status=400)

        query = """
            SELECT Id, scrap_part, scrap_operation, scrap_category, scrap_amount, scrap_line, 
                   total_cost, date, date_current
            FROM tkb_scrap
            WHERE scrap_line = %s
            AND date_current BETWEEN %s AND %s
            ORDER BY date_current ASC;
        """

        # Use the Django database connection
        with connections['prodrpt-md'].cursor() as cursor:
            cursor.execute(query, [scrap_line, start_date, end_date])
            rows = cursor.fetchall()

        # Calculate total scrap amount and prepare results
        total_scrap_amount = sum(row[4] for row in rows)
        results = [
            {
                'Id': row[0],
                'Scrap Part': row[1],
                'Scrap Operation': row[2],
                'Scrap Category': row[3],
                'Scrap Amount': row[4],
                'Scrap Line': row[5],
                'Total Cost': row[6],
                'Date': row[7],
                'Date Current': row[8],
            }
            for row in rows
        ]

        return JsonResponse({'total_scrap_amount': total_scrap_amount, 'scrap_data': results})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# =======================================
# ========= OA Calculation ==============
# =======================================


def calculate_oa_metrics(data):
    """
    Calculate OA, P, A, and Q metrics from the provided data.

    :param data: Dictionary containing input data for calculation
    :return: Dictionary with OA, P, A, Q metrics or raises an exception for invalid input
    """
    try:
        # Extract variables
        total_downtime = int(data.get('totalDowntime', 0))
        total_produced = int(data.get('totalProduced', 0))
        total_target = int(data.get('totalTarget', 0))
        total_potential = int(data.get('totalPotentialMinutes', 0))
        total_scrap = int(data.get('totalScrap', 0))

        # Validate inputs
        if total_target <= 0:
            raise ValueError('Total target must be greater than 0')
        if total_potential <= 0:
            raise ValueError('Total potential must be greater than 0')

        # Calculate P, A, Q
        P = total_produced / total_target
        A = (total_potential - total_downtime) / total_potential
        Q = total_produced / (total_produced + total_scrap) if (total_produced + total_scrap) > 0 else 0

        # Calculate OA
        OA = P * A * Q

        return {'OA': OA, 'P': P, 'A': A, 'Q': Q}

    except KeyError as e:
        raise ValueError(f"Missing key in input data: {e}")
    except ValueError as e:
        raise ValueError(f"Invalid input: {e}")


@csrf_exempt
def calculate_oa(request):
    if request.method == 'POST':
        try:
            # Parse input data
            raw_body = request.body
            logger.info("Raw request body: %s", raw_body)
            data = json.loads(raw_body)
            logger.info("Parsed request data: %s", data)

            # Call utility function to calculate OA metrics
            metrics = calculate_oa_metrics(data)

            # Log results
            logger.info("Calculated OA Metrics: %s", metrics)

            return JsonResponse(metrics)

        except json.JSONDecodeError as e:
            logger.error("JSON decode error: %s", e)
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)
        except ValueError as e:
            logger.error("Validation error: %s", e)
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=405)









# =======================================================================
# =======================================================================
# =========================== OA Display V2 =============================
# =======================================================================
# =======================================================================


def oa_display_v2(request):
    """
    Render the OA Display V2 page with the lines data for the dropdown.
    """
    return render(request, 'prod_query/oa_display_v2.html', {'lines': lines})


def save_machine_target(machine_id, effective_date, target, line=None):
    """
    Save or update a machine target record in the database.

    :param machine_id: ID of the machine
    :param effective_date: Effective date in "YYYY-MM-DD" format
    :param target: Target value to save
    :param line: Line value to save
    :return: Saved or updated OAMachineTargets instance
    """
    try:
        # Convert effective_date to Unix timestamp
        date_obj = datetime.strptime(effective_date, "%Y-%m-%d")
        unix_timestamp = int(time.mktime(date_obj.timetuple()))
    except ValueError as e:
        raise ValueError(f"Invalid effective date format: {effective_date}") from e

    # Check if an entry already exists for the machine, line, and effective date
    record, created = OAMachineTargets.objects.update_or_create(
        machine_id=machine_id,
        line=line,  # Include the line in the filter criteria
        effective_date_unix=unix_timestamp,
        defaults={"target": target},
    )
    return record, created


@csrf_exempt
def update_target(request):
    """
    Handle updating the target for a machine on a specific effective date.
    """
    print("Received update_target request.")
    if request.method == "POST":
        try:
            # Parse JSON data from the request body
            data = json.loads(request.body)
            print("Data received from frontend:", data)
            
            # Retrieve the variables
            machine_id = data.get("machine_id")
            effective_date = data.get("effective_date")
            target = data.get("target")
            line = data.get("line")
            
            print(f"Machine ID: {machine_id}")
            print(f"Effective Date: {effective_date}")
            print(f"Target: {target}")
            print(f"Line: {line}")
            
            # Validate inputs
            if not machine_id or not effective_date or not target:
                print("Missing required parameters.")
                return JsonResponse({"error": "Missing required parameters."}, status=400)
            
            # Save or update the machine target
            record, created = save_machine_target(machine_id, effective_date, target, line)
            
            print("Record saved or updated:", record)
            print("Was the record newly created?", created)
            
            # Prepare the response
            response_data = {
                "message": "Target updated successfully.",
                "created": created,
                "record": {
                    "machine_id": record.machine_id,
                    "effective_date": record.effective_date_unix,
                    "target": record.target,
                    "line": record.line,  # Include line in the response
                },
            }
            return JsonResponse(response_data, status=200)
        
        except json.JSONDecodeError:
            print("Invalid JSON data received.")
            return JsonResponse({"error": "Invalid JSON data."}, status=400)
        except Exception as e:
            print("Unexpected error:", str(e))
            return JsonResponse({"error": str(e)}, status=500)
    
    print("Invalid request method.")
    return JsonResponse({"error": "Invalid request method."}, status=405)



# =======================================================================
# =======================================================================
# =========================== OA Display V3 =============================
# =======================================================================
# =======================================================================


from django.shortcuts import render
from django.http import HttpResponse
import calendar
from datetime import datetime, timedelta


def get_month_start_and_end(selected_date):
    today = datetime.now()
    first_day_of_month = selected_date.replace(day=1)
    if first_day_of_month.weekday() == 6:
        start_date = first_day_of_month.replace(hour=23, minute=0, second=0)
    else:
        start_date = (first_day_of_month - timedelta(days=1)).replace(hour=23, minute=0, second=0)
    if selected_date.year == today.year and selected_date.month == today.month:
        end_date = today.replace(second=0, microsecond=0)
    else:
        end_date = selected_date.replace(
            day=calendar.monthrange(selected_date.year, selected_date.month)[1]
        ).replace(hour=23, minute=0, second=0)

    return start_date, end_date


def get_sunday_to_friday_ranges(first_day, last_day):
    ranges = []
    first_friday = first_day
    while first_friday.weekday() != 4:
        first_friday += timedelta(days=1)
    first_friday = first_friday.replace(hour=23, minute=0, second=0)
    if first_day < first_friday:
        ranges.append((first_day, first_friday))
    current_start = first_friday + timedelta(days=2) 
    current_start = current_start.replace(hour=23, minute=0, second=0)
    while current_start + timedelta(days=5) <= last_day:
        current_end = current_start + timedelta(days=5)
        current_end = current_end.replace(hour=23, minute=0, second=0)
        ranges.append((current_start, current_end))
        current_start += timedelta(days=7)
    if last_day.weekday() != 6:
        if ranges and ranges[-1][1] < last_day:
            last_sunday = last_day
            while last_sunday.weekday() != 6:
                last_sunday -= timedelta(days=1)
            last_sunday = last_sunday.replace(hour=23, minute=0, second=0)
            if last_sunday > ranges[-1][1]:
                ranges.append((last_sunday, last_day))
    return ranges


def fetch_downtime_by_date_ranges(machine, date_ranges, downtime_threshold=5, machine_parts=None):
    downtime_results = []
    try:
        with connections['prodrpt-md'].cursor() as cursor:
            for start, end in date_ranges:
                start_timestamp = int(start.timestamp())
                end_timestamp = int(end.timestamp())
                downtime = calculate_downtime(
                    machine=machine,
                    cursor=cursor,
                    start_timestamp=start_timestamp,
                    end_timestamp=end_timestamp,
                    downtime_threshold=downtime_threshold,
                    machine_parts=machine_parts
                )
                potential_minutes = calculate_potential_minutes(start, end)
                downtime_results.append({
                    'start': start,
                    'end': end,
                    'downtime': downtime,
                    'potential_minutes': potential_minutes
                })
        return downtime_results
    except Exception as e:
        print(f"Error in fetch_downtime_by_date_ranges: {e}")  # Log the error to the console
        raise RuntimeError(f"Error fetching downtime data: {str(e)}")  # Re-raise the exception


def calculate_potential_minutes(start, end):
    return int((end - start).total_seconds() / 60)


def calculate_percentage_week(potential_minutes):
    full_week_minutes = 7200
    if potential_minutes == full_week_minutes:
        return f"{potential_minutes} (Full Week)"
    percentage = round((potential_minutes / full_week_minutes) * 100)
    return f"{potential_minutes} ({percentage}%)"


def fetch_production_by_date_ranges(machine, machine_parts, date_ranges):
    total_production = 0
    try:
        with connections['prodrpt-md'].cursor() as cursor:
            for start, end in date_ranges:
                start_timestamp = int(start.timestamp())
                end_timestamp = int(end.timestamp())
                total_production += calculate_total_produced(
                    machine=machine,
                    machine_parts=machine_parts,
                    start_timestamp=start_timestamp,
                    end_timestamp=end_timestamp,
                    cursor=cursor
                )
        return total_production
    except Exception as e:
        print(f"Error in fetch_production_by_date_ranges: {e}")  # Log the error to the console
        raise RuntimeError(f"Error fetching production data: {str(e)}")  # Re-raise the exception


def calculate_percentage_downtime(downtime, potential_minutes):
    if potential_minutes == 0:
        return "0%"
    percentage = (downtime / potential_minutes) * 100
    return f"{int(round(percentage))}%"  # Round and convert to an integer


def get_machine_part_numbers(machine_id, line_name, lines):
    for line in lines:
        if line['line'] == line_name:  # Match the correct line
            for operation in line['operations']:
                for machine in operation['machines']:
                    if machine['number'] == machine_id:
                        # Return part numbers if they exist, otherwise None
                        return machine.get('part_numbers', None)
    return None  # Return None if no match is found


def get_month_details(selected_date, machine, line_name, lines):
    first_day, last_day = get_month_start_and_end(selected_date)
    ranges = get_sunday_to_friday_ranges(first_day, last_day)

    # Fetch downtime data
    downtime_results = fetch_downtime_by_date_ranges(
        machine=machine,
        date_ranges=ranges
    )
    for result in downtime_results:
        result['potential_minutes'] = calculate_percentage_week(result['potential_minutes'])
        result['percentage_downtime'] = calculate_percentage_downtime(
            downtime=result['downtime'],
            potential_minutes=int(result['potential_minutes'].split()[0])
        )
    
    # Fetch part numbers for the machine within the specified line
    part_numbers = get_machine_part_numbers(machine, line_name, lines)

    # Fetch production data, including part numbers if available
    with connections['prodrpt-md'].cursor() as cursor:
        for result in downtime_results:
            result['produced'] = calculate_total_produced(
                machine=machine,
                machine_parts=part_numbers,  # Pass part numbers dynamically
                start_timestamp=int(result['start'].timestamp()),
                end_timestamp=int(result['end'].timestamp()),
                cursor=cursor
            )
    return {
        'first_day': first_day,
        'last_day': last_day,
        'ranges': downtime_results
    }


def get_machine_target(machine_id, selected_date_unix, line_name):
    try:
        # Fetch all target entries for the given machine and line
        all_targets = OAMachineTargets.objects.filter(
            machine_id=machine_id,
            line=line_name
        ).order_by('effective_date_unix')


        # Find the correct target entry based on the selected date
        target_entry = None
        for i, target in enumerate(all_targets):
            # Check if this target falls within the appropriate range
            if target.effective_date_unix <= selected_date_unix:
                # Check if it's the last entry or if the next entry is after the selected date
                next_entry = all_targets[i + 1] if i + 1 < len(all_targets) else None
                if not next_entry or next_entry.effective_date_unix > selected_date_unix:
                    target_entry = target
                    break


        # Return the target value or None if no valid entry is found
        return target_entry.target if target_entry else None

    except Exception as e:
        print(f"Error in get_machine_target: {e}")
        return None



def calculate_adjusted_target(target, percentage_downtime):
    """
    Calculate the adjusted target based on:
    Adjusted Target = Target - (Target * (Downtime%))

    :param target: Original target value (int)
    :param percentage_downtime: Downtime percentage as a string (e.g., "24%")
    :return: Adjusted target (int)
    """
    try:
        downtime_fraction = float(percentage_downtime.strip('%')) / 100.0
        adjusted_target = target - (target * downtime_fraction)
        adjusted_target = round(adjusted_target)
        # Debug print:
        return adjusted_target
    except Exception as e:
        print(f"Error in calculate_adjusted_target: {e}")
        # If there's an error, return original target (fallback)
        return target


def calculate_totals(grouped_results):
    for date_block, operations in grouped_results.items():
        for operation, operation_data in operations.items():
            machines = operation_data.get('machines', [])
            if not isinstance(machines, list):
                continue

            total_target = 0
            total_adjusted_target = 0
            total_produced = 0
            total_downtime = 0
            total_potential_minutes = 0
            downtime_percentages = []
            a_values = []
            p_values = []

            for machine in machines:
                target = machine.get('target', 0)
                adjusted_target = machine.get('adjusted_target', 0)
                produced = machine.get('produced', 0)
                downtime = machine.get('downtime', 0)
                potential_minutes_str = machine.get('potential_minutes', "0 (0%)")
                percentage_downtime_str = machine.get('percentage_downtime', "0%")
                p_str = machine.get('p_value', "0%").strip('%')

                try:
                    percentage_downtime_val = float(percentage_downtime_str.strip('%'))
                    downtime_percentages.append(percentage_downtime_val)

                    total_target += target
                    total_adjusted_target += adjusted_target
                    total_produced += produced
                    total_downtime += downtime

                    pm_value = int(potential_minutes_str.split()[0])
                    total_potential_minutes += pm_value

                    p_val = int(p_str) if p_str.isdigit() else 0
                    if p_val > 0:
                        p_values.append(p_val)

                    # Calculate A value for this machine
                    a_value = calculate_A(pm_value, downtime)
                    machine['a_value'] = a_value  # Store A value back to the machine dict
                    
                    a_values.append(int(a_value.strip('%')))
                except ValueError as ve:
                    print(f"[DEBUG] Error processing machine data in calculate_totals: {ve}")

            average_downtime = round(sum(downtime_percentages) / len(downtime_percentages)) if downtime_percentages else 0
            average_a = round(sum(a_values) / len(a_values)) if a_values else 0
            average_p = round(sum(p_values) / len(p_values)) if p_values else 0

            # Add the operation's aggregated totals to operation_data
            operation_data['totals'] = {
                'total_target': total_target,
                'total_adjusted_target': total_adjusted_target,
                'total_produced': total_produced,
                'total_downtime': total_downtime,
                'total_potential_minutes': total_potential_minutes,
                'average_downtime_percentage': f"{average_downtime}%",
                'average_a_value': f"{average_a}%",
                'average_p_value': f"{average_p}%"
            }


    return grouped_results


def calculate_a_and_p_averages(p_values, a_values, downtime_percentages):
    # Pop the last number off the lists if they are not empty
    if p_values:
        p_values.pop()
    if a_values:
        a_values.pop()

    average_p = round(sum(p_values) / len(p_values)) if p_values else 0
    average_a = round(sum(a_values) / len(a_values)) if a_values else 0
    average_downtime = int(round(sum(downtime_percentages) / len(downtime_percentages))) if downtime_percentages else 0

    return {
        'average_p': average_p,
        'average_a': average_a,
        'average_downtime': average_downtime
    }


def calculate_line_totals(grouped_results):
    for date_block, operations in grouped_results.items():
        line_totals = {
            'total_target': 0,
            'total_produced': 0,
            'total_downtime': 0,
            'total_potential_minutes': 0,
            'downtime_percentages': [],
            'p_values': [],
            'a_values': [],
            'total_scrap_amount': 0
        }

        # Collect P and A values from operations
        for operation, operation_data in operations.items():
            operation_totals = operation_data.get('totals', {})
            line_totals['total_target'] += operation_totals.get('total_target', 0)
            line_totals['total_produced'] += operation_totals.get('total_produced', 0)
            line_totals['total_downtime'] += operation_totals.get('total_downtime', 0)
            line_totals['total_potential_minutes'] += operation_totals.get('total_potential_minutes', 0)

            # Extract P values
            average_p_value = operation_totals.get('average_p_value', "0%").strip('%')
            try:
                line_totals['p_values'].append(int(average_p_value))
            except ValueError:
                pass

            # Extract A values
            average_a_value = operation_totals.get('average_a_value', "0%").strip('%')
            try:
                line_totals['a_values'].append(int(average_a_value))
            except ValueError:
                pass

            downtime_percentage = operation_totals.get('average_downtime_percentage', "0%")
            try:
                line_totals['downtime_percentages'].append(float(downtime_percentage.strip('%')))
            except ValueError:
                pass

            # Scrap totals (line_totals from operations dict)
            if 'line_totals' in operations:
                line_totals['total_scrap_amount'] = operations['line_totals'].get('total_scrap_amount', 0)

        # # Debug: Print raw P and A values
        # print(f"Date Block: {date_block}")
        # print(f"Raw P Values: {line_totals['p_values']}")
        # print(f"Raw A Values: {line_totals['a_values']}")

        # Calculate averages using the extracted function
        averages = calculate_a_and_p_averages(
            line_totals['p_values'],
            line_totals['a_values'],
            line_totals['downtime_percentages']
        )
        average_p = averages['average_p']
        average_a = averages['average_a']
        average_downtime = averages['average_downtime']

        # # Debug: Print calculated averages
        # print(f"Calculated Average P: {average_p}%")
        # print(f"Calculated Average A: {average_a}%")
        # print(f"Sum of P Values: {sum(line_totals['p_values'])}")
        # print(f"Number of P Values: {len(line_totals['p_values'])}")
        # print(f"Sum of A Values: {sum(line_totals['a_values'])}")
        # print(f"Number of A Values: {len(line_totals['a_values'])}")

        # Recalculate adjusted target at the line level using the aggregated downtime
        percentage_downtime_str = f"{average_downtime}%"
        total_adjusted_target = calculate_adjusted_target(line_totals['total_target'], percentage_downtime_str)

        # Ensure `line_totals` key exists
        if 'line_totals' not in operations:
            operations['line_totals'] = {}

        operations['line_totals'].update({
            'total_target': line_totals['total_target'],
            'total_adjusted_target': total_adjusted_target,  # Use recalculated adjusted target
            'total_produced': line_totals['total_produced'],
            'total_downtime': line_totals['total_downtime'],
            'total_potential_minutes': line_totals['total_potential_minutes'],
            'average_downtime_percentage': percentage_downtime_str,
            'average_p_value': f"{average_p}%",
            'average_a_value': f"{average_a}%",
            'total_scrap_amount': line_totals['total_scrap_amount'],
            # q_value will be calculated later in get_line_details after all operations are done
        })

    return grouped_results


def calculate_monthly_totals(grouped_results):
    monthly_totals = {
        'total_target': 0,
        # Remove direct summation of adjusted targets here as well
        'total_produced': 0,
        'total_downtime': 0,
        'total_potential_minutes': 0,
        'downtime_percentages': [],
        'a_values': [],  # Track A values for monthly totals
        'p_values': [],  # Track P values for monthly totals
        'total_scrap_amount': 0,
        'q_values': []
    }

    for date_block, operations in grouped_results.items():
        if 'line_totals' in operations:
            line_totals = operations['line_totals']
            monthly_totals['total_target'] += line_totals['total_target']
            # Do NOT sum total_adjusted_target from line level, recalculate after
            monthly_totals['total_produced'] += line_totals['total_produced']
            monthly_totals['total_downtime'] += line_totals['total_downtime']
            monthly_totals['total_potential_minutes'] += line_totals['total_potential_minutes']
            monthly_totals['total_scrap_amount'] += line_totals.get('total_scrap_amount', 0)

            # Collect Q values
            q_value = line_totals.get('q_value', "0%").strip('%')
            try:
                monthly_totals['q_values'].append(float(q_value))
            except ValueError:
                pass

            # Track average P values
            try:
                p_value = float(line_totals.get('average_p_value', "0%").strip('%'))
                monthly_totals['p_values'].append(p_value)
            except ValueError:
                pass

            # Track average A values
            try:
                a_value = float(line_totals.get('average_a_value', "0%").strip('%'))
                monthly_totals['a_values'].append(a_value)
            except ValueError:
                pass

            # Track downtime percentages
            try:
                downtime_percentage = float(line_totals.get('average_downtime_percentage', "0%").strip('%'))
                monthly_totals['downtime_percentages'].append(downtime_percentage)
            except ValueError:
                pass

    # Calculate averages
    average_downtime = round(sum(monthly_totals['downtime_percentages']) / len(monthly_totals['downtime_percentages'])) if monthly_totals['downtime_percentages'] else 0
    monthly_totals['average_downtime_percentage'] = f"{average_downtime}%"

    if monthly_totals['p_values']:
        average_p = round(sum(monthly_totals['p_values']) / len(monthly_totals['p_values']))
    else:
        average_p = 0
    monthly_totals['average_p_value'] = f"{average_p}%"

    if monthly_totals['a_values']:
        average_a = round(sum(monthly_totals['a_values']) / len(monthly_totals['a_values']))
    else:
        average_a = 0
    monthly_totals['average_a_value'] = f"{average_a}%"

    # Calculate average Q
    if monthly_totals['q_values']:
        average_q = round(sum(monthly_totals['q_values']) / len(monthly_totals['q_values']), 2)
    else:
        average_q = 0
    monthly_totals['average_q_value'] = f"{average_q}%"

    # Recalculate the monthly adjusted target using the monthly average downtime
    percentage_downtime_str = f"{average_downtime}%"
    monthly_adjusted_target = calculate_adjusted_target(monthly_totals['total_target'], percentage_downtime_str)

    # Update monthly_totals to include recalculated adjusted target
    monthly_totals['total_adjusted_target'] = monthly_adjusted_target

    return monthly_totals


def total_scrap_for_line(scrap_line, start_date, end_date):
    try:
        query = """
            SELECT Id, scrap_part, scrap_operation, scrap_category, scrap_amount, scrap_line, 
                   total_cost, date, date_current
            FROM tkb_scrap
            WHERE scrap_line = %s
            AND date_current BETWEEN %s AND %s
            ORDER BY date_current ASC;
        """
        with connections['prodrpt-md'].cursor() as cursor:
            cursor.execute(query, [scrap_line, start_date, end_date])
            rows = cursor.fetchall()
        total_scrap_amount = sum(row[4] for row in rows)
        results = [
            {
                'Id': row[0],
                'Scrap Part': row[1],
                'Scrap Operation': row[2],
                'Scrap Category': row[3],
                'Scrap Amount': row[4],
                'Scrap Line': row[5],
                'Total Cost': row[6],
                'Date': row[7],
                'Date Current': row[8],
            }
            for row in rows
        ]
        return {
            'total_scrap_amount': total_scrap_amount,
            'scrap_data': results
        }
    except Exception as e:
        print(f"Error in total_scrap_for_line: {e}")  # Log the error to the console
        raise RuntimeError(f"Error fetching scrap data: {str(e)}")  # Re-raise the exception


def calculate_p(total_produced, total_adjusted_target, downtime_percentage):
    if total_produced == 0 and downtime_percentage.strip('%') == "100":
        return 100  # Special case: 100% downtime means P should be 100%
    if total_adjusted_target == 0:
        return 0  # Avoid division by zero
    return round((total_produced / total_adjusted_target) * 100)  # Convert to percentage



def calculate_A(total_potential_minutes, downtime_minutes):
    if total_potential_minutes == 0:
        return "0%"  # Avoid division by zero
    a_value = round(((total_potential_minutes - downtime_minutes) / total_potential_minutes) * 100)
    return f"{a_value}%"  # Return percentage as a string


def calculate_Q(total_produced_last_op, scrap_total):
    if total_produced_last_op + scrap_total == 0:
        return "0%"
    q_value = round((total_produced_last_op / (total_produced_last_op + scrap_total) * 100), 2)
    return f"{q_value}%"


def get_total_produced_last_op_for_block(operations):
    try:
        valid_operations = [op for op in operations.keys() if op != 'line_totals']
        if valid_operations:
            try:
                # Sort using numeric values if possible, fallback to string sorting
                last_op = sorted(valid_operations, key=lambda x: int(x) if x.isdigit() else x)[-1]
            except ValueError as ve:
                print(f"ValueError during sorting operations: {ve}")
                last_op = sorted(valid_operations, key=str)[-1]  # Fallback to string sorting

            produced = 0
            if 'totals' in operations[last_op]:
                produced = operations[last_op]['totals'].get('total_produced', 0)
            return produced
        return 0
    except Exception as e:
        print(f"Error in get_total_produced_last_op_for_block: {e}")
        return 0


def get_line_details(selected_date, selected_line, lines):
    """
    Fetch detailed data for a line on a given date, including adjusted targets
    based on the percentage downtime.
    """
    try:
        selected_date_unix = int(selected_date.timestamp())
        line_data = next((line for line in lines if line['line'] == selected_line), None)
        if not line_data:
            raise ValueError(f"Invalid line selected: {selected_line}")

        grouped_results = {}
        for operation in line_data['operations']:
            for machine in operation['machines']:
                machine_number = machine['number']
                machine_target = get_machine_target(machine_number, selected_date_unix, selected_line)
                if machine_target is None:
                    continue

                machine_details = get_month_details(selected_date, machine_number, selected_line, lines)
                for block in machine_details['ranges']:
                    date_block = (block['start'], block['end'])
                    if date_block not in grouped_results:
                        grouped_results[date_block] = {}
                    if operation['op'] not in grouped_results[date_block]:
                        grouped_results[date_block][operation['op']] = {'machines': []}

                    # Calculate adjusted target using percentage_downtime from block
                    # block['percentage_downtime'] should be something like "24%"
                    adjusted_target = calculate_adjusted_target(
                        target=machine_target,
                        percentage_downtime=block['percentage_downtime']
                    )

                    p_value = f"{calculate_p(block['produced'], adjusted_target, block['percentage_downtime'])}%"
                    machine_data = {
                        'machine_number': machine_number,
                        'target': machine_target,
                        'adjusted_target': adjusted_target,
                        'produced': block['produced'],
                        'downtime': block['downtime'],
                        'potential_minutes': block['potential_minutes'],
                        'percentage_downtime': block['percentage_downtime'],
                        'p_value': p_value
                    }
                    grouped_results[date_block][operation['op']]['machines'].append(machine_data)

        grouped_results = calculate_totals(grouped_results)

        # Add scrap info and line totals
        for date_block, operations in grouped_results.items():
            start_date, end_date = date_block
            scrap_data = total_scrap_for_line(scrap_line=selected_line, start_date=start_date, end_date=end_date)
            total_scrap_amount = scrap_data['total_scrap_amount']
            if 'line_totals' not in operations:
                operations['line_totals'] = {}
            operations['line_totals']['total_scrap_amount'] = total_scrap_amount

        grouped_results = calculate_line_totals(grouped_results)
        for date_block, operations in grouped_results.items():
            if 'line_totals' in operations:
                scrap_total = operations['line_totals'].get('total_scrap_amount', 0)
                total_produced_last_op = get_total_produced_last_op_for_block(operations)
                operations['line_totals']['q_value'] = calculate_Q(total_produced_last_op, scrap_total)

        monthly_totals = calculate_monthly_totals(grouped_results)
        return {
            'line_name': selected_line,
            'grouped_results': grouped_results,
            'monthly_totals': monthly_totals
        }
    except Exception as e:
        print(f"Error in get_line_details: {e}")
        raise


def get_all_lines(lines):
    return [line['line'] for line in lines]


def get_month_and_year(date_str):
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
        return date.strftime('%B %Y')  # Format to "Month Year"
    except ValueError:
        return None  # Return None if the date is invalid


def oa_byline2(request):
    context = {'lines': get_all_lines(lines)}  # Load all available lines
    if request.method == 'POST':
        selected_date_str = request.POST.get('date')
        selected_line = request.POST.get('line')
        
        # Add selected date and line to the context for persistence
        context['selected_date'] = selected_date_str
        context['selected_line'] = selected_line

        try:
            # Parse the selected date
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d')
            today = datetime.now()

            if selected_date > today:
                context['error'] = "The selected date is in the future. Please select a valid date."
            else:
                # Call the function to get line details for the selected date and line
                line_details = get_line_details(selected_date, selected_line, lines)
                context.update(line_details)
                context['selected_date'] = selected_date  # Add selected date in datetime format
                # Get the month and year for the title
                month_year = get_month_and_year(selected_date_str)
                if month_year:
                    context['month_year'] = month_year
        except ValueError:
            # Handle invalid date errors
            context['error'] = "Invalid date or error processing the date."

    return render(request, 'prod_query/oa_display_v3.html', context)






# =======================================================================
# =======================================================================
# =========================== OA Drilldown ==============================
# =======================================================================
# =======================================================================


def find_first_sunday(start_date):
    """
    Adjust the start date to the first Sunday at 11 PM.
    
    Parameters:
        start_date (datetime): The starting date and time to adjust from.
        
    Returns:
        datetime: The first Sunday after or on the given start_date,
                  adjusted to 11 PM (23:00:00).
                  
    Example:
        If start_date is 2025-01-01 10:00:00 (a Wednesday),
        the function will return 2025-01-05 23:00:00 (the next Sunday at 11 PM).
    """
    # Initialize first_sunday with the start_date
    first_sunday = start_date

    # Loop until the day of the week is Sunday (weekday() returns 6 for Sunday)
    while first_sunday.weekday() != 6:
        first_sunday += timedelta(days=1)  # Add one day at a time until Sunday is reached

    # Replace the time part of the datetime to set it to 11 PM
    return first_sunday.replace(hour=23, minute=0, second=0)


def add_partial_block_to_friday(start_date, ranges):
    """
    Add a partial time block from the given start_date (adjusted to 11 PM) 
    to the upcoming Friday at 11 PM, and append it to the provided ranges list.

    Parameters:
        start_date (datetime): The starting date and time to adjust from.
        ranges (list): A list of tuples representing start and end datetime ranges.

    Returns:
        datetime: The next Sunday at 11 PM (23:00:00), following the calculated Friday.
        
    Example:
        If start_date is 2025-01-01 10:00:00 (a Wednesday),
        and ranges is an empty list, the function will:
        - Append the block (2025-01-01 23:00:00, 2025-01-03 23:00:00) to ranges.
        - Return 2025-01-05 23:00:00 (the next Sunday at 11 PM).
    """
    # Adjust the start_date to 11 PM by setting the time component
    start_date = start_date.replace(hour=23, minute=0, second=0, microsecond=0)

    # Initialize upcoming_friday to the start_date
    upcoming_friday = start_date

    # Loop until the day of the week is Friday (weekday() returns 4 for Friday)
    while upcoming_friday.weekday() != 4:
        upcoming_friday += timedelta(days=1)  # Increment by one day until Friday is reached

    # Set the time on upcoming_friday to 11 PM
    upcoming_friday = upcoming_friday.replace(hour=23, minute=0, second=0)

    # Check if the block has a meaningful duration (start_date is before upcoming_friday)
    if start_date < upcoming_friday:
        # Append the time block as a tuple (start_date, upcoming_friday) to the ranges list
        ranges.append((start_date, upcoming_friday))

    # Calculate the next Sunday (two days after Friday)
    next_sunday = upcoming_friday + timedelta(days=2)

    # Return the next Sunday with time adjusted to 11 PM
    return next_sunday.replace(hour=23, minute=0, second=0)


def calculate_full_blocks(current_start, end_date, ranges):
    """
    Calculate and add full blocks of time from Sunday 11 PM to Friday 11 PM 
    within the given date range. 

    Each block starts at Sunday 11 PM and ends at the following Friday 11 PM. 
    These blocks are appended to the provided `ranges` list.

    Parameters:
        current_start (datetime): The starting Sunday at 11 PM.
        end_date (datetime): The end date (exclusive) up to which blocks are calculated.
        ranges (list): A list to which the calculated blocks (tuples) will be appended.

    Returns:
        datetime: The next start date (Sunday at 11 PM) after the last valid block.
        
    Example:
        If current_start is 2025-01-05 23:00:00 (a Sunday),
        and end_date is 2025-01-20 23:00:00, ranges will include:
        - (2025-01-05 23:00:00, 2025-01-10 23:00:00)
        - (2025-01-12 23:00:00, 2025-01-17 23:00:00)
        The function will return 2025-01-19 23:00:00 (the next Sunday after the last block).
    """
    # Loop to calculate blocks until the end_date is reached
    while current_start + timedelta(days=5) <= end_date:
        # Calculate the current block's end time (Friday 11 PM)
        current_end = current_start + timedelta(days=5)
        current_end = current_end.replace(hour=23, minute=0, second=0)

        # Append the block (current_start, current_end) to the ranges list
        ranges.append((current_start, current_end))

        # Move to the next block's start time (the following Sunday at 11 PM)
        current_start += timedelta(days=7)

    # Return the next Sunday at 11 PM after the last valid block
    return current_start


def handle_remaining_days(current_start, end_date, ranges):
    """
    Handle the remaining days if the interval ends before the next Sunday.

    This function calculates the last partial block from the most recent Sunday 
    (at 11 PM) before `current_start` to the `end_date` (adjusted to 11 PM), 
    and appends it to the `ranges` list.

    Parameters:
        current_start (datetime): The current start time to evaluate.
        end_date (datetime): The end date of the range to handle.
        ranges (list): A list to which the partial block (tuple) will be appended.

    Returns:
        None. The function modifies the `ranges` list in place.

    Example:
        If current_start is 2025-01-19 23:00:00 (Sunday),
        and end_date is 2025-01-23 23:00:00 (Wednesday), 
        the function will append:
        - (2025-01-19 23:00:00, 2025-01-23 23:00:00) to the ranges list.
    """
    # Check if there is a valid range to handle
    if current_start <= end_date:
        # Find the most recent Sunday before or on current_start
        last_sunday = current_start
        while last_sunday.weekday() != 6:  # weekday() == 6 means Sunday
            last_sunday -= timedelta(days=1)  # Move backward one day at a time

        # Adjust the last Sunday's time to 11 PM
        last_sunday = last_sunday.replace(hour=23, minute=0, second=0)

        # Add the partial block if the range is valid (last_sunday is before or on end_date)
        if last_sunday <= end_date:
            ranges.append((last_sunday, end_date.replace(hour=23, minute=0, second=0)))


def get_sunday_to_friday_ranges_custom(start_date, end_date):
    """
    Generates Sunday 11 PM to Friday 11 PM blocks for a given time interval.

    Args:
        start_date (datetime): The start of the interval.
        end_date (datetime): The end of the interval.

    Returns:
        list of tuples: Each tuple contains the start and end of a time block.
    """
    ranges = []

    # Check if the start date is within a Sunday-to-Friday block
    if start_date.weekday() <= 4:  # If it's between Sunday and Friday
        # Add a partial block to the upcoming Friday
        current_start = add_partial_block_to_friday(start_date, ranges)
    else:
        # Find the first Sunday at 11 PM if start_date is outside a Sunday-to-Friday range
        current_start = find_first_sunday(start_date)

    # Calculate full Sunday-to-Friday blocks
    current_start = calculate_full_blocks(current_start, end_date, ranges)

    # Handle any remaining days
    handle_remaining_days(current_start, end_date, ranges)

    return ranges


def calculate_average_downtime(metrics):
    """
    Calculate the average percentage downtime for each machine across the time blocks.

    Args:
        metrics (dict): Metrics returned by `fetch_line_metrics`.

    Returns:
        dict: Average percentage downtime for each machine.
    """
    machine_downtime_data = {}

    # Collect percentage downtime for each machine across time blocks
    for block in metrics['details']:
        for machine in block['machines']:
            machine_id = machine['machine_id']
            percentage_downtime = machine['percentage_downtime']

            # Remove '%' and convert to integer
            percentage_downtime_value = int(percentage_downtime.strip('%'))

            if machine_id not in machine_downtime_data:
                machine_downtime_data[machine_id] = []

            machine_downtime_data[machine_id].append(percentage_downtime_value)

    # Calculate average percentage downtime for each machine
    average_downtime = {}
    for machine_id, downtimes in machine_downtime_data.items():
        average = sum(downtimes) / len(downtimes) if downtimes else 0
        average_downtime[machine_id] = average

        # Debugging: Print the calculated average downtime for each machine
        # print(f"[DEBUG] Machine {machine_id}: Average Downtime = {average}% (from downtimes: {downtimes})")

    return average_downtime


def fetch_line_metrics(line_name, time_blocks, lines):
    """
    Fetch metrics for a line and time blocks, including total produced, target, adjusted target,
    potential minutes, downtime, percentage downtime, P value, and A value.
    """
    aggregated_metrics = {
        'total_produced': 0,
        'total_target': 0,
        'total_adjusted_target': 0,
        'total_potential_minutes': 0,
        'total_downtime': 0,
        'details': []  # Detailed breakdown per block and machine
    }

    try:
        # Find the line data
        line_data = next((line for line in lines if line['line'] == line_name), None)
        if not line_data:
            print(f"[ERROR] Line not found: {line_name}")
            raise ValueError(f"Invalid line selected: {line_name}")

        with connections['prodrpt-md'].cursor() as cursor:
            # Iterate over time blocks
            for block_start, block_end in time_blocks:
                # print(f"[INFO] Processing time block: {block_start} to {block_end}")
                block_metrics = {
                    'block_start': block_start,
                    'block_end': block_end,
                    'machines': []
                }

                # Iterate over operations in the line
                for operation in line_data['operations']:
                    for machine in operation['machines']:
                        machine_id = machine['number']
                        machine_parts = get_machine_part_numbers(machine_id, line_name, lines)

                        try:
                            # Fetch downtime data
                            downtime_data = fetch_downtime_by_date_ranges(
                                machine=machine_id,
                                date_ranges=[(block_start, block_end)],
                                machine_parts=machine_parts
                            )
                            if not downtime_data or 'downtime' not in downtime_data[0]:
                                print(f"[WARNING] Missing downtime data for machine {machine_id}")
                            downtime_entry = downtime_data[0] if downtime_data else {}
                            downtime = downtime_entry.get('downtime', 0)
                            potential_minutes = downtime_entry.get('potential_minutes', 0)

                            # Calculate percentage downtime
                            percentage_downtime = calculate_percentage_downtime(
                                downtime=downtime,
                                potential_minutes=potential_minutes
                            )

                            # Fetch production data
                            produced = fetch_production_by_date_ranges(
                                machine=machine_id,
                                machine_parts=machine_parts,
                                date_ranges=[(block_start, block_end)]
                            )

                            # Fetch target data
                            target = get_machine_target(
                                machine_id=machine_id,
                                selected_date_unix=int(block_start.timestamp()),
                                line_name=line_name
                            )

                            # Highlight potential issues in fetched data
                            if produced is None or target is None:
                                print(f"[WARNING] Produced or target is None for machine {machine_id}")

                            # Calculate metrics
                            adjusted_target = calculate_adjusted_target(
                                target=target if target else 0,
                                percentage_downtime=percentage_downtime
                            )
                            p_value = calculate_p(
                                total_produced=produced or 0,
                                total_adjusted_target=adjusted_target,
                                downtime_percentage=percentage_downtime
                            )
                            a_value = calculate_A(
                                total_potential_minutes=potential_minutes or 0,
                                downtime_minutes=downtime or 0
                            )

                            # Update aggregated metrics
                            aggregated_metrics['total_produced'] += produced or 0
                            aggregated_metrics['total_target'] += target or 0
                            aggregated_metrics['total_adjusted_target'] += adjusted_target or 0
                            aggregated_metrics['total_potential_minutes'] += potential_minutes or 0
                            aggregated_metrics['total_downtime'] += downtime or 0

                            # Add machine metrics
                            machine_metrics = {
                                'machine_id': machine_id,
                                'produced': produced,
                                'target': target,
                                'adjusted_target': adjusted_target,
                                'total_downtime': downtime,
                                'total_potential_minutes': potential_minutes,
                                'percentage_downtime': percentage_downtime,
                                'p_value': f"{p_value}%",
                                'a_value': a_value
                            }
                            block_metrics['machines'].append(machine_metrics)

                        except Exception as machine_error:
                            print(f"[ERROR] Error processing machine {machine_id}: {machine_error}")

                aggregated_metrics['details'].append(block_metrics)

        return aggregated_metrics

    except Exception as e:
        print(f"[ERROR] Error in fetch_line_metrics: {e}")
        raise RuntimeError(f"Error fetching line metrics: {str(e)}")


def aggregate_machine_metrics(machine, aggregated_data):
    """
    Aggregate metrics for a single machine across multiple time blocks.

    Args:
        machine (dict): Metrics for the machine from a time block.
        aggregated_data (dict): Dictionary to update with aggregated values for the machine.

    Returns:
        None: Updates the aggregated_data in place.
    """
    machine_id = machine['machine_id']
    try:
        if machine_id not in aggregated_data:
            # Initialize the data for this machine
            aggregated_data[machine_id] = {
                'machine_id': machine_id,
                'total_produced': 0,
                'total_target': 0,
                'total_adjusted_target': 0,  # To sum adjusted targets across blocks
                'total_downtime': 0,
                'total_potential_minutes': 0
            }

        # Update aggregated values by summing them
        aggregated_data[machine_id]['total_produced'] += machine.get('produced', 0)
        aggregated_data[machine_id]['total_target'] += machine.get('target', 0)
        aggregated_data[machine_id]['total_adjusted_target'] += machine.get('adjusted_target', 0)
        aggregated_data[machine_id]['total_downtime'] += machine.get('total_downtime', 0)
        aggregated_data[machine_id]['total_potential_minutes'] += machine.get('total_potential_minutes', 0)

        if aggregated_data[machine_id]['total_produced'] is None:
            print(f"[WARNING] Total produced is None for machine {machine_id}")

    except TypeError as e:
        print(f"[ERROR] Issue aggregating data for machine {machine_id}: {e}")


def aggregate_line_metrics(metrics):
    """
    Aggregate metrics across all time blocks for a line.

    Args:
        metrics (dict): Metrics returned by `fetch_line_metrics`.

    Returns:
        list: Aggregated metrics for each machine.
    """
    aggregated_data = {}
    # print("[INFO] Starting aggregation of line metrics")

    for block in metrics['details'][:10]:  # Only process the first 10 blocks for debugging
        for machine in block['machines']:
            try:
                aggregate_machine_metrics(machine, aggregated_data)
            except KeyError as e:
                print(f"[WARNING] Missing data for machine: {machine.get('machine_id', 'Unknown')} - {e}")

    # print("[INFO] Aggregated data for first 10 blocks:", aggregated_data)
    return list(aggregated_data.values())




def recalculate_adjusted_targets(aggregated_metrics, average_downtime):
    """
    Recalculate total adjusted targets for machines using average percentage downtime.

    Args:
        aggregated_metrics (list): Aggregated metrics for machines.
        average_downtime (dict): Average downtime percentages for machines.

    Returns:
        list: Updated aggregated metrics with recalculated adjusted targets.
    """
    for machine in aggregated_metrics:
        machine_id = machine['machine_id']
        if machine_id in average_downtime:
            # Truncate average downtime percentage to 2 decimal places
            average_downtime_percentage = float(f"{average_downtime[machine_id] / 100:.2f}")
            total_target = machine['total_target']

            # Debugging: Print values before calculation
            # print(f"[DEBUG] Machine {machine_id}: Total Target = {total_target}, Average Downtime = {average_downtime[machine_id]}%")

            # Adjusted target calculation
            adjusted_target = int(total_target * (1 - average_downtime_percentage))

            # Debugging: Print the adjusted target calculation step
            # print(f"[DEBUG] Machine {machine_id}: Adjusted Target Calculation = {total_target} * (1 - {average_downtime_percentage}) = {adjusted_target}")

            # Assign the calculated adjusted target
            machine['total_adjusted_target'] = adjusted_target
        else:
            # Debugging: If no downtime data is found for a machine
            print(f"[DEBUG] Machine {machine_id}: No Average Downtime Found. Using Total Target = {machine['total_target']}")
    return aggregated_metrics


def drilldown_calculate_P(total_produced, total_adjusted_target, downtime):
    """
    Calculate the P value (percentage) for a machine.

    Args:
        total_produced (int): Total items produced by the machine.
        total_adjusted_target (int): Total adjusted target for the machine.
        downtime (str): Downtime percentage as a string (e.g., "85%").

    Returns:
        str: P value as a percentage (e.g., "85%").
    """
    # Convert downtime to numeric value for comparison
    downtime_percentage = float(downtime.strip('%'))

    # If downtime is 100%, return P as 100%
    if downtime_percentage == 100.0:
        return "100%"

    # Avoid division by zero
    if total_adjusted_target == 0:
        return "0%"

    # Calculate P value
    p_value = round((total_produced / total_adjusted_target) * 100)
    return f"{p_value}%"



def deep_dive(request):
    """
    View to handle detailed downtime data sent from the frontend.
    It receives machine_id, start_date, and end_date, fetches entries, calculates downtime, and returns them as JSON.
    """
    if request.method == 'POST':
        try:
            # Parse the incoming JSON data
            data = json.loads(request.body)
            
            # Extract the required fields
            machine_id = data.get('machine_id')
            start_date = data.get('start_date')
            end_date = data.get('end_date')

            # Determine the machine to query
            query_machine_id = MACHINE_MAP.get(machine_id, machine_id)

            # Fetch entries using the mapped machine_id
            raw_entries = fetch_prdowntime1_entries(query_machine_id, start_date, end_date)

            # Process entries to calculate downtime
            processed_entries = []
            for entry in raw_entries:
                problem = entry[0]
                called4helptime = entry[1]
                completedtime = entry[2]

                # Calculate downtime in minutes
                if completedtime:
                    downtime_minutes = round((completedtime - called4helptime).total_seconds() / 60)
                else:
                    downtime_minutes = "In Progress"

                processed_entries.append({
                    "problem": problem,
                    "called4helptime": called4helptime.isoformat(),
                    "completedtime": completedtime.isoformat() if completedtime else None,
                    "downtime_minutes": downtime_minutes
                })

            # Print the start and end times in timestamp format
            start_timestamp = datetime.fromisoformat(start_date).timestamp()
            end_timestamp = datetime.fromisoformat(end_date).timestamp()
            # print(f"[INFO] Start Date (Timestamp): {int(start_timestamp)}, End Date (Timestamp): {int(end_timestamp)}")

            # Fetch chart data with machine hardcoded to '1703'
            labels, *data_series = fetch_chart_data(
                machine=machine_id,
                start=int(start_timestamp),
                end=int(end_timestamp),
                interval=5,
                group_by_shift=False
            )

            # Print the first 10 datapoints from the function
            # print(f"[INFO] First 10 Datapoints from fetch_chart_data:")
            # for label, *data in zip(labels[:10], *[series[:10] for series in data_series]):
            #     print(f"Label: {label}, Data: {data}")

            # Return the processed entries and chart data in the JSON response
            return JsonResponse({
                'message': 'Data received successfully',
                'entries': processed_entries,
                'chart_data': {
                    'labels': labels,
                    'data_series': data_series
                }
            }, status=200)
        
        except json.JSONDecodeError as e:
            # Handle JSON parsing errors
            print(f"[ERROR] Failed to decode JSON: {e}")
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            # Handle other exceptions
            print(f"[ERROR] Exception in deep_dive: {e}")
            return JsonResponse({'error': str(e)}, status=500)
    
    # If the request method is not POST, return a 405 Method Not Allowed response
    print("[ERROR] Invalid request method received. Only POST is allowed.")
    return JsonResponse({'error': 'Invalid request method'}, status=405)


def oa_drilldown(request):
    context = {'lines': get_all_lines(lines)}  # Load all available lines

    if request.method == 'POST':
        start_date_str = request.POST.get('start_date', '')
        end_date_str = request.POST.get('end_date', '')
        selected_line = request.POST.get('line', '')

        try:
            # Ensure valid input
            if not selected_line:
                return JsonResponse({'error': 'Please select a line.'}, status=400)
            if not start_date_str or not end_date_str:
                return JsonResponse({'error': 'Start and end dates are required.'}, status=400)

            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            now = datetime.now()

            if start_date > now or end_date > now:
                return JsonResponse({'error': 'Dates cannot be in the future.'}, status=400)
            if start_date > end_date:
                return JsonResponse({'error': 'Start date cannot be after end date.'}, status=400)

            # Generate time blocks
            time_blocks = get_sunday_to_friday_ranges_custom(start_date, end_date)

            # Fetch metrics for the line and time blocks
            metrics = fetch_line_metrics(line_name=selected_line, time_blocks=time_blocks, lines=lines)

            # Aggregate metrics across all time blocks
            aggregated_metrics = aggregate_line_metrics(metrics)

            # Calculate average downtime for machines
            average_downtime = calculate_average_downtime(metrics)

            # Recalculate total adjusted targets
            aggregated_metrics = recalculate_adjusted_targets(aggregated_metrics, average_downtime)

            # Calculate A value and P value for each machine
            # print("[DEBUG] Aggregated Metrics (Per Machine):")
            for machine in aggregated_metrics:
                total_potential_minutes = machine['total_potential_minutes']
                total_downtime = machine['total_downtime']
                total_produced = machine['total_produced']
                total_adjusted_target = machine.get('total_adjusted_target', 0)
                avg_downtime = average_downtime.get(machine['machine_id'], 0)

                # Calculate A value
                a_value = calculate_A(total_potential_minutes, total_downtime)
                machine['a_value'] = a_value

                # Calculate P value
                p_value = drilldown_calculate_P(total_produced, total_adjusted_target, f"{avg_downtime}%")
                machine['p_value'] = p_value

                # Print debug info
                # print(f"Machine ID: {machine['machine_id']}, "
                #       f"Total Produced: {total_produced}, "
                #       f"Total Adjusted Target: {total_adjusted_target}, "
                #       f"Average Downtime: {avg_downtime}%, "
                #       f"A Value: {a_value}, "
                #       f"P Value: {p_value}")

            return JsonResponse({'aggregated_metrics': aggregated_metrics, 'average_downtime': average_downtime}, status=200)

        except Exception as e:
            print(f"[ERROR] Exception in oa_drilldown: {e}")
            return JsonResponse({'error': str(e)}, status=500)

    return render(request, 'prod_query/oa_drilldown.html', context)






# ==================================================================
# ==================================================================
# ===================== Downtime Frequency =========================
# ==================================================================
# ==================================================================


def get_distinct_machines(lines):
    """
    Extract all distinct machine numbers from the lines object.
    """
    machines = set()  # Use a set to ensure uniqueness
    for line in lines:
        for operation in line.get("operations", []):
            for machine in operation.get("machines", []):
                machines.add(machine["number"])
    return sorted(machines)  # Return sorted list of machine numbers


def parse_dates(start_date_str, end_date_str):
    """
    Convert start and end dates from strings to timestamps.
    """
    try:
        # Use the directly imported datetime
        start_timestamp = int(time.mktime(datetime.strptime(start_date_str, '%Y-%m-%d').timetuple()))
        end_timestamp = int(time.mktime(datetime.strptime(end_date_str, '%Y-%m-%d').timetuple()))
        return start_timestamp, end_timestamp
    except (ValueError, TypeError):
        return None, None





def validate_threshold(threshold):
    """
    Ensure the downtime threshold is a valid integer, defaulting to 5 if invalid.
    """
    try:
        return int(threshold)
    except (ValueError, TypeError):
        return 5


def fetch_downtime_results(machine, start_timestamp, end_timestamp, downtime_threshold):
    """
    Calculate downtime and threshold breach count for the given parameters.
    The threshold is in seconds, while results return downtime in minutes.
    """
    try:
        with connections['prodrpt-md'].cursor() as cursor:
            return calculate_downtime_and_threshold_count(
                machine=machine,
                cursor=cursor,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                downtime_threshold=downtime_threshold
            )
    except Exception as e:
        print(f"[ERROR] Failed to calculate downtime: {e}")
        return "Error: Could not retrieve downtime data.", "Error"



def downtime_frequency_view(request):
    """
    View to render the downtime frequency page with debugging to trace discrepancies.
    Updated to handle downtime thresholds in seconds.
    """
    machine_numbers = get_distinct_machines(lines)
    downtime_result = None
    threshold_breach_count = None
    interval_results = []  # Store results for each interval

    if request.method == "GET":
        # Get form inputs
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        selected_machine = request.GET.get('machine')
        downtime_threshold = request.GET.get('downtime_threshold', 0)  # Threshold in seconds
        view_interval = request.GET.get('view_interval', 60)  # Default interval is 60 minutes

        if start_date and end_date and selected_machine:
            # Parse inputs
            start_timestamp, end_timestamp = parse_dates(start_date, end_date)
            downtime_threshold = int(downtime_threshold)  # Already in seconds

            try:
                view_interval = int(view_interval) * 60  # Convert minutes to seconds
            except ValueError:
                view_interval = 3600  # Default to 1 hour (3600 seconds)

            if start_timestamp and end_timestamp:
                # Calculate total downtime for the full range
                downtime_result, threshold_breach_count = fetch_downtime_results(
                    selected_machine, start_timestamp, end_timestamp, downtime_threshold
                )

                # Split the time range into intervals and calculate for each
                interval_count = ceil((end_timestamp - start_timestamp) / view_interval)
                current_start = start_timestamp

                for i in range(interval_count):
                    current_end = min(current_start + view_interval, end_timestamp)
                    interval_downtime, interval_breaches = fetch_downtime_results(
                        selected_machine, current_start, current_end, downtime_threshold
                    )
                    # Append only if downtime or breaches > 0
                    if interval_downtime > 0 or interval_breaches > 0:
                        interval_results.append({
                            'start_time': datetime.fromtimestamp(current_start).strftime('%Y-%m-%d %H:%M:%S'),
                            'end_time': datetime.fromtimestamp(current_end).strftime('%Y-%m-%d %H:%M:%S'),
                            'downtime': interval_downtime,  # Downtime is in minutes
                            'breaches': interval_breaches
                        })
                    current_start = current_end  # Move to the next interval

    return render(request, 'prod_query/downtime_frequency.html', {
        'machines': machine_numbers,
        'downtime_result': downtime_result,
        'threshold_breach_count': threshold_breach_count,
        'interval_results': interval_results,  # Pass filtered interval data to the template
    })






# =================================================================
# =================================================================
# ================== Press OEE With PR Downtime ===================
# =================================================================
# =================================================================




def get_custom_time_blocks(start_date, end_date):
    """
    Generates time blocks based on the given start and end dates.
    
    If the range is a full week or more, it uses Sunday 11 PM to Friday 11 PM logic.
    If the range is shorter, it uses start_date 11 PM to end_date 11 PM.
    It also ensures no future dates are included.

    Args:
        start_date (datetime): The start date selected.
        end_date (datetime): The end date selected.

    Returns:
        list of tuples: Each tuple contains (start_time, end_time) for the block.
        OR
        str: "That's in the future" if the date range includes future dates.
    """
    now = datetime.now()

    # Ensure no future dates
    if start_date > now or end_date > now:
        return "That's in the future"

    # Adjust start and end times to 11 PM
    start_date = start_date.replace(hour=23, minute=0, second=0, microsecond=0)
    end_date = end_date.replace(hour=23, minute=0, second=0, microsecond=0)

    # If the range is less than a full week, return only that block
    if (end_date - start_date).days < 6:
        return [(start_date, end_date)]

    # Otherwise, use full Sunday-to-Friday blocks
    return get_sunday_to_friday_ranges_custom(start_date, end_date)


def fetch_production_count(machine, cursor, start_timestamp, end_timestamp):
    """
    Returns the number of production entries for a given machine within the time window.
    
    Args:
        machine (str): The machine/asset number.
        cursor: Database cursor.
        start_timestamp (int): The starting timestamp (in seconds).
        end_timestamp (int): The ending timestamp (in seconds).
    
    Returns:
        int: The number of production entries.
    """
    query = """
        SELECT COUNT(*) 
        FROM GFxPRoduction
        WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s;
    """
    cursor.execute(query, (machine, start_timestamp, end_timestamp))
    result = cursor.fetchone()
    return result[0] if result else 0






def calculate_downtime_press(machine, cursor, start_timestamp, end_timestamp, downtime_threshold=5, machine_parts=None):
    """
    Calculate the total downtime for a specific machine over a given time period.

    Also returns individual downtime events that exceed the threshold.
    """
    machine_downtime = 0  # Accumulate total downtime
    prev_timestamp = start_timestamp  # For interval calculations
    downtime_events = []  # List to hold individual downtime events

    # Build the query based on machine parts provided
    if not machine_parts:
        query = """
            SELECT TimeStamp
            FROM GFxPRoduction
            WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s
            ORDER BY TimeStamp ASC;
        """
        params = [machine, start_timestamp, end_timestamp]
    else:
        placeholders = ','.join(['%s'] * len(machine_parts))
        query = f"""
            SELECT TimeStamp
            FROM GFxPRoduction
            WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s AND Part IN ({placeholders})
            ORDER BY TimeStamp ASC;
        """
        params = [machine, start_timestamp, end_timestamp] + machine_parts

    cursor.execute(query, params)  # Execute the query

    timestamps_fetched = False
    for row in cursor:
        timestamps_fetched = True
        current_timestamp = row[0]
        # Calculate the time difference (in minutes)
        time_delta = (current_timestamp - prev_timestamp) / 60
        if time_delta > downtime_threshold:
            downtime_minutes = round(time_delta)
            downtime_events.append({
                'start': prev_timestamp,
                'end': current_timestamp,
                'duration': downtime_minutes
            })
            machine_downtime += downtime_minutes


        prev_timestamp = current_timestamp

    if not timestamps_fetched:
        # No production timestamps: entire period is downtime
        total_potential_minutes = (end_timestamp - start_timestamp) / 60
        return round(total_potential_minutes), [{
            'start': start_timestamp,
            'end': end_timestamp,
            'duration': round(total_potential_minutes)
        }]

    # Handle downtime from last production timestamp to the end of the period
    remaining_time = (end_timestamp - prev_timestamp) / 60
    if remaining_time > 0:
        downtime_events.append({
            'start': prev_timestamp,
            'end': end_timestamp,
            'duration': round(remaining_time)
        })
        machine_downtime += remaining_time

    return round(machine_downtime), downtime_events





def fetch_press_prdowntime1_entries(assetnum, called4helptime, completedtime):
    """
    Fetches downtime entries based on the given parameters using raw SQL.

    :param assetnum: The asset number of the machine.
    :param called4helptime: The start of the time window (ISO 8601 format).
    :param completedtime: The end of the time window (ISO 8601 format).
    :return: List of rows matching the criteria.
    """
    try:
        # Parse the dates to ensure they are in datetime format
        called4helptime = datetime.fromisoformat(called4helptime)
        completedtime = datetime.fromisoformat(completedtime)

        # Dynamically import `get_db_connection` from settings.py
        settings_path = os.path.join(
            os.path.dirname(__file__), '../pms/settings.py'
        )
        spec = importlib.util.spec_from_file_location("settings", settings_path)
        settings = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(settings)
        get_db_connection = settings.get_db_connection

        # Get database connection
        conn = get_db_connection()
        cursor = conn.cursor()

        # Raw SQL query to fetch the required data
        query = """
        SELECT problem, called4helptime, completedtime, idnumber
        FROM pr_downtime1
        WHERE assetnum = %s
        AND down = 'Yes_Down'
        AND (
            -- Entries that start before the window and bleed into the window
            (called4helptime < %s AND (completedtime >= %s OR completedtime IS NULL))
            -- Entries that start within the window
            OR (called4helptime >= %s AND called4helptime <= %s)
            -- Entries that start in the window and bleed out
            OR (called4helptime >= %s AND called4helptime <= %s AND (completedtime > %s OR completedtime IS NULL))
            -- Entries that bleed both before and after the window
            OR (called4helptime < %s AND (completedtime > %s OR completedtime IS NULL))
        )
        """

        # Execute the query
        cursor.execute(query, (
            assetnum,
            called4helptime, called4helptime,
            called4helptime, completedtime,
            called4helptime, completedtime, completedtime,
            called4helptime, completedtime
        ))

        # Fetch all rows
        rows = cursor.fetchall()

        # Close the cursor and connection
        cursor.close()
        conn.close()

        return rows

    except Exception as e:
        return {"error": str(e)}



def compute_overlap_label(detail_start, detail_end, pr_entries):
    for pr in pr_entries:
        pr_start = pr['start_time']
        # If pr_end is None, treat it as an ongoing event by using datetime.max
        pr_end = pr['end_time'] or datetime.max
        pr_id = pr.get('idnumber')
        
        # Check for no overlap
        if detail_end <= pr_start or detail_start >= pr_end:
            continue

        # Determine the type of overlap and return along with the idnumber
        if detail_start >= pr_start and detail_end <= pr_end:
            return {"overlap": "WITHIN PR", "pr_id": pr_id}
        elif detail_start <= pr_start and detail_end >= pr_end:
            return {"overlap": "CONTAINS PR", "pr_id": pr_id}
        elif detail_start < pr_start and detail_end > pr_start and detail_end < pr_end:
            return {"overlap": "OVERLAP LEFT", "pr_id": pr_id}
        elif detail_start > pr_start and detail_start < pr_end and detail_end > pr_end:
            return {"overlap": "OVERLAP RIGHT", "pr_id": pr_id}
    return {"overlap": "No Overlap", "pr_id": None}





def attach_spm_chart_data_to_blocks(time_blocks, machine, interval=5):
    """
    For each time block in the provided list, fetch the strokes per minute chart data 
    using the given machine and time block start/end times, and attach it to the block.

    Args:
        time_blocks (list of dict): Each dict should include at least 'block_start' and 'block_end'.
            If available, 'raw_block_start' and 'raw_block_end' should contain datetime objects.
        machine (str): The machine identifier used to fetch the SPM data.
        interval (int): Interval (in minutes) for calculating strokes per minute data. Default is 5.
        
    Returns:
        list of dict: The original list, with each block now including:
                      - 'chart_labels': list of timestamps (for ChartJS labels)
                      - 'chart_counts': list of stroke rates (for ChartJS data)
    """

    for block in time_blocks:
        # Use raw datetime objects if available; otherwise, parse the formatted strings.
        if 'raw_block_start' in block and 'raw_block_end' in block:
            block_start_dt = block['raw_block_start']
            block_end_dt = block['raw_block_end']
        else:
            block_start_dt = datetime.strptime(block['block_start'], '%Y-%m-%d %H:%M:%S')
            block_end_dt = datetime.strptime(block['block_end'], '%Y-%m-%d %H:%M:%S')
            
        start_ts = int(block_start_dt.timestamp())
        end_ts = int(block_end_dt.timestamp())
        
        # Get the chart data using your existing strokes_per_minute_chart_data function
        labels, counts = strokes_per_minute_chart_data(machine, start_ts, end_ts, interval)
        
        # Attach the fetched chart data to the block dictionary
        block['chart_labels'] = labels
        block['chart_counts'] = counts
        
    return time_blocks







def fetch_press_changeovers(machine_id, start_timestamp, end_timestamp):
    """
    Fetch entries from the 'Press_Changeovers' table for the given asset (machine_id)
    where called4helptime is between start_timestamp and end_timestamp.

    If no entries are found, the time window is doubled up to 5 times or until 
    the search window reaches a maximum of 1 year.

    Returns:
        A list of tuples:
          (asset, part_no, ideal_cycle_time, called4helptime, completedtime, downtime, code)
        where part_no is the last 9 characters of the problem field and ideal_cycle_time 
        is retrieved from AssetCycleTimes if available.
    """
    MAX_DAYS = 365  # Maximum search window in days
    SECONDS_IN_A_DAY = 86400  # Seconds per day
    MAX_EXPANSIONS = 5  # Stop after 5 expansions

    press_changeover_records = []  # This will hold our results

    try:
        connection = mysql.connector.connect(
            host=settings.DAVE_HOST,
            user=settings.DAVE_USER,
            password=settings.DAVE_PASSWORD,
            database=settings.DAVE_DB
        )
        cursor = connection.cursor()

        original_window = end_timestamp - start_timestamp
        max_window = MAX_DAYS * SECONDS_IN_A_DAY
        current_window = original_window
        expansion_count = 0  # Track how many times we expand the window

        # Keep expanding the window until we get at least one record, capped at 5 expansions or 1 year
        while current_window <= max_window and expansion_count < MAX_EXPANSIONS:
            query = """
                SELECT asset, problem, called4helptime, completedtime, Downtime, Code
                FROM Press_Changeovers
                WHERE asset = %s
                AND UNIX_TIMESTAMP(called4helptime) BETWEEN %s AND %s
                ORDER BY called4helptime ASC
            """
            cursor.execute(query, (machine_id, start_timestamp, end_timestamp))
            records = cursor.fetchall()

            if records:
                for rec in records:
                    asset = rec[0]
                    problem_full = rec[1] if rec[1] is not None else ""
                    part_no = problem_full[-9:] if len(problem_full) >= 9 else problem_full

                    # Query the AssetCycleTimes for the given part number.
                    cycle_record = AssetCycleTimes.objects.filter(
                        part__part_number=part_no
                    ).order_by("-effective_date").first()
                    
                    # Use the cycle_time if a record exists, else set a default value.
                    ideal_cycle_time = cycle_record.cycle_time if cycle_record else "N/A"

                    called4helptime = rec[2]
                    completedtime = rec[3] if rec[3] else "na"
                    downtime = rec[4]
                    code = rec[5]

                    # Append the new tuple with the ideal_cycle_time inserted
                    press_changeover_records.append(
                        (asset, part_no, ideal_cycle_time, called4helptime, completedtime, downtime, code)
                    )

                break  # Exit the loop when records are found

            # If no records, double the window (expand search window backward)
            new_window = min(current_window * 2, max_window)
            extension = new_window - current_window
            start_timestamp -= extension
            current_window = new_window
            expansion_count += 1  # Increment expansion counter

            # print(f"[DEBUG] Expansion {expansion_count}: New range: {start_timestamp} - {end_timestamp}")

        # if expansion_count >= MAX_EXPANSIONS:
        #     print(f"[DEBUG] No records found after {MAX_EXPANSIONS} expansions, stopping search.")

        return press_changeover_records

    except Exception as e:
        print(f"[ERROR] Error fetching press changeovers: {e}")
        return []
    finally:
        if 'connection' in locals():
            connection.close()



def calculate_runtime_press(machine, cursor, start_timestamp, end_timestamp, running_threshold=5):
    """
    Calculate the running intervals for a specific machine over a given time period.
    A running interval is defined as a contiguous series of production timestamps where
    the gap between consecutive timestamps does not exceed the running_threshold (in minutes).

    Args:
        machine (str): The machine/asset number.
        cursor: Database cursor.
        start_timestamp (int): The starting timestamp (in seconds).
        end_timestamp (int): The ending timestamp (in seconds).
        running_threshold (int): Maximum gap (in minutes) to consider production as continuous.

    Returns:
        list of dict: Each dictionary contains:
                      - 'start': start time of the running interval (timestamp)
                      - 'end': end time of the running interval (timestamp)
                      - 'duration': duration in minutes (rounded)
    """
    query = """
        SELECT TimeStamp
        FROM GFxPRoduction
        WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s
        ORDER BY TimeStamp ASC;
    """
    cursor.execute(query, (machine, start_timestamp, end_timestamp))
    rows = cursor.fetchall()
    
    if not rows:
        # If there are no production timestamps, there are no running intervals.
        return []
    
    running_intervals = []
    # Start the first running interval at the first production timestamp.
    run_start = rows[0][0]
    previous_ts = run_start

    for row in rows[1:]:
        current_ts = row[0]
        # If the gap between the current and previous production timestamp is larger than threshold,
        # finish the current running interval.
        if (current_ts - previous_ts) / 60 > running_threshold:
            run_end = previous_ts
            duration = round((run_end - run_start) / 60)
            if duration > 0:
                running_intervals.append({
                    'start': run_start,
                    'end': run_end,
                    'duration': duration
                })
            # Start a new running interval.
            run_start = current_ts
        previous_ts = current_ts

    # Add the final running interval.
    run_end = previous_ts
    duration = round((run_end - run_start) / 60)
    if duration > 0:
        running_intervals.append({
            'start': run_start,
            'end': run_end,
            'duration': duration
        })
    
    return running_intervals


def get_fallback_part_from_sc_production(machine, running_start_ts):
    """
    Fallback lookup for an active part from the sc_production1 table.
    It returns the last record (before the running interval starts) for the given asset,
    but only if the part number is exactly 9 characters long.
    
    Args:
        machine (str): The asset number.
        running_start_ts (int): The running interval start timestamp.
        
    Returns:
        str or None: The part number if found and valid, otherwise None.
    """
    running_start_dt = datetime.fromtimestamp(running_start_ts)
    query = """
        SELECT partno, updatedtime FROM sc_production1
        WHERE asset_num = %s AND updatedtime < %s
        ORDER BY updatedtime DESC
        LIMIT 1;
    """
    with connections['prodrpt-md'].cursor() as cursor:
        cursor.execute(query, (machine, running_start_dt))
        row = cursor.fetchone()
        if row:
            partno = row[0]
            if partno and len(partno.strip()) == 9:
                return partno.strip()
    return None



def get_cycle_time_for_part(part_no):
    """
    Attempts to look up the ideal cycle time for a given part number
    using the AssetCycleTimes table. Returns the cycle time if found,
    otherwise "N/A".
    
    Args:
        part_no (str): The part number to look up.
    
    Returns:
        cycle_time (float or str): The ideal cycle time in seconds, or "N/A".
    """
    try:
        cycle_record = AssetCycleTimes.objects.filter(
            part__part_number=part_no
        ).order_by("-effective_date").first()
        if cycle_record:
            return cycle_record.cycle_time
    except Exception as e:
        print(f"[ERROR] Looking up cycle time for part {part_no}: {e}")
    return "N/A"

def get_active_part(running_interval, changeover_records, machine):
    """
    Determines which part is active for a given running interval for a specific machine.
    It first checks changeover records (ensuring the record's asset matches the machine).
    If no record is found, it falls back to querying the sc_production1 table.
    If the fallback finds a valid part number, it also looks up its cycle time.
    
    Args:
        running_interval (dict): Contains at least the 'start' key (timestamp in seconds).
        changeover_records (list of tuples): Each tuple is
            (asset, part_no, ideal_cycle_time, called4helptime, completedtime, downtime, code).
        machine (str): The machine asset identifier.
    
    Returns:
        dict: A dictionary with:
            - 'part': The active part number or "N/A"
            - 'cycle_time': The ideal cycle time for that part or "N/A"
    """
    running_start_ts = running_interval['start']
    active_record = None
    for record in changeover_records:
        # Only consider records for the specified machine.
        if str(record[0]).strip() != machine.strip():
            continue
        completedtime = record[4]
        if completedtime != "na" and isinstance(completedtime, datetime):
            if completedtime.timestamp() <= running_start_ts:
                if active_record is None or completedtime.timestamp() > active_record[4].timestamp():
                    active_record = record
    if active_record:
        return {'part': active_record[1], 'cycle_time': active_record[2]}
    else:
        # Fallback: query the sc_production1 table.
        fallback_part = get_fallback_part_from_sc_production(machine, running_start_ts)
        if fallback_part:
            cycle_time = get_cycle_time_for_part(fallback_part)
            return {'part': fallback_part, 'cycle_time': cycle_time}
        else:
            return {'part': "N/A", 'cycle_time': "N/A"}




def compute_press_pa_oee(total_potential_minutes, planned_minutes_down, unplanned_minutes_down, total_minutes_up, cycle_time, actual_parts, total_target):
    """
    Calculates production effectiveness metrics for a press using the following formulas:

      1. Planned Production Time (PPT):
         PPT = total_potential_minutes - planned_minutes_down

      2. Total Downtime:
         total_downtime = planned_minutes_down + unplanned_minutes_down

      3. Run Time:
         run_time = PPT - total_downtime

      4. Target Parts:
         target_parts = PPT / cycle_time

      5. Availability:
         availability = run_time / PPT

      6. Performance:
         performance = (cycle_time * actual_parts) / run_time

      7. Quality:
         quality = 1.0  (assumed)

      8. Overall Equipment Effectiveness (OEE):
         oee = availability * performance * quality

    Args:
      total_potential_minutes (float): e.g., 7200 minutes (theoretical full-time)
      planned_minutes_down (float): Planned downtime in minutes (y)
      unplanned_minutes_down (float): Unplanned downtime in minutes (the rest of total downtime)
      total_minutes_up (float): Total minutes running (not used directly in these calculations)
      cycle_time (float): Ideal cycle time (in seconds) for one part (b)
      actual_parts (float): Actual parts produced (a)
      total_target (float): Provided target parts (will be recalculated)

    Returns:
      dict: A dictionary with keys:
         - planned_production_time (PPT)
         - run_time
         - target_parts
         - availability
         - performance
         - quality
         - oee
    """
    try:
        total_potential_minutes = float(total_potential_minutes)
    except:
        total_potential_minutes = 0.0
    try:
        planned_minutes_down = float(planned_minutes_down)
    except:
        planned_minutes_down = 0.0
    try:
        unplanned_minutes_down = float(unplanned_minutes_down)
    except:
        unplanned_minutes_down = 0.0
    try:
        total_minutes_up = float(total_minutes_up)
    except:
        total_minutes_up = 0.0
    try:
        cycle_time = float(cycle_time)
    except:
        cycle_time = 0.0
    try:
        actual_parts = float(actual_parts)
    except:
        actual_parts = 0.0

    # 1. Planned Production Time (PPT)
    planned_production_time = total_potential_minutes - planned_minutes_down

    # 2. Total downtime and Run Time
    total_downtime = planned_minutes_down + unplanned_minutes_down
    run_time = planned_production_time - total_downtime

    # Check if run_time is less than 0, and adjust if necessary
    if run_time < 0:
        run_time = total_minutes_up


    # 3. Target Parts (recalculated)
    target_parts = ((planned_production_time * 60)  / cycle_time) if cycle_time > 0 else 0.0

    # Calculate availability
    availability = (run_time / planned_production_time) if planned_production_time > 0 else 0.0

   

    # 5. Performance
    performance = ((cycle_time * actual_parts) / (run_time * 60)) if run_time > 0 else 0.0

    # 6. Quality is assumed to be 100%
    quality = 1.0

    # 7. Overall Equipment Effectiveness (OEE)
    oee = availability * performance * quality

    return {
        "planned_production_time": planned_production_time,
        "run_time": run_time,
        "target_parts": target_parts,
        "availability": availability,
        "performance": performance,
        "quality": quality,
        "oee": oee
    }





def summarize_contiguous_intervals(intervals, downtime_details, human_readable_format='%Y-%m-%d %H:%M:%S'):
    """
    Aggregates contiguous intervals by part number and adds:
      - 'planned_minutes_down': Sum of downtime events (in whole minutes) that are >= 240 minutes 
          and do NOT overlap with a PR downtime.
      - 'unplanned_minutes_down': Sum of the remaining downtime events within the group.
      - 'minutes_down': The sum of planned and unplanned downtime.
      - 'total_potential_minutes': Total minutes up (duration) plus minutes_down.
      - 'target': Calculated as (total_potential_minutes * 60) / cycle_time for the group.
      - Additional PA/OEE metrics are computed by calling compute_press_pa_oee.
    
    The downtime events (downtime_details) are expected to be a list of dicts with keys:
      'start', 'end', 'duration', 'overlap'
    where the times are formatted as strings using human_readable_format.
    
    Returns:
      A list of dictionaries (one per contiguous group) with the aggregated values and PA/OEE metrics.
    """
    if not intervals:
        return []
    
    summaries = []
    # Start with the first interval as the current group.
    current_group = intervals[0].copy()
    try:
        current_group['duration'] = int(current_group['duration'])
    except:
        pass
    try:
        current_group['parts_produced'] = int(current_group['parts_produced']) if current_group['parts_produced'] != "N/A" else "N/A"
    except:
        pass
    try:
        current_group['target'] = int(current_group['target']) if current_group['target'] != "N/A" else "N/A"
    except:
        pass

    for interval in intervals[1:]:
        if interval['part'] == current_group['part']:
            # Same part, so update the current group.
            current_group['end'] = interval['end']
            try:
                current_group['duration'] += int(interval['duration'])
            except:
                current_group['duration'] = "N/A"
            if current_group['parts_produced'] != "N/A" and interval['parts_produced'] != "N/A":
                current_group['parts_produced'] += int(interval['parts_produced'])
            else:
                current_group['parts_produced'] = "N/A"
            if current_group['target'] != "N/A" and interval['target'] != "N/A":
                current_group['target'] += int(interval['target'])
            else:
                current_group['target'] = "N/A"
        else:
            # Compute downtime metrics for the current group.
            try:
                group_start = datetime.strptime(current_group['start'], human_readable_format)
                group_end = datetime.strptime(current_group['end'], human_readable_format)
            except Exception:
                group_start = group_end = None
            planned = 0
            unplanned = 0
            if group_start and group_end:
                for dt_event in downtime_details:
                    try:
                        event_start = datetime.strptime(dt_event['start'], human_readable_format)
                        event_end = datetime.strptime(dt_event['end'], human_readable_format)
                    except Exception:
                        continue
                    # Only include downtime events that fall completely within the group's boundaries.
                    if event_start >= group_start and event_end <= group_end:
                        if dt_event['duration'] >= 240 and dt_event['overlap'] == "No Overlap":
                            planned += dt_event['duration']
                        else:
                            unplanned += dt_event['duration']
            current_group['planned_minutes_down'] = planned
            current_group['unplanned_minutes_down'] = unplanned
            current_group['minutes_down'] = planned + unplanned
            if isinstance(current_group.get('duration'), int):
                current_group['total_potential_minutes'] = current_group['duration'] + current_group['minutes_down']
            else:
                current_group['total_potential_minutes'] = "N/A"
            # Recalculate target using total potential minutes:
            try:
                cycle_time = float(current_group.get('cycle_time'))
            except Exception:
                cycle_time = None
            if (isinstance(current_group.get('total_potential_minutes'), int) and cycle_time and cycle_time > 0):
                current_group['target'] = int((current_group['total_potential_minutes'] * 60) / cycle_time)
            else:
                current_group['target'] = "N/A"
            # Call compute_press_pa_oee to get PA/OEE metrics and update the group.
            pa_oee_data = compute_press_pa_oee(
                total_potential_minutes=current_group.get('total_potential_minutes', 0),
                planned_minutes_down=current_group.get('planned_minutes_down', 0),
                unplanned_minutes_down=current_group.get('unplanned_minutes_down', 0),
                total_minutes_up=current_group.get('duration', 0),
                cycle_time=current_group.get('cycle_time', 0),
                actual_parts=current_group.get('parts_produced', 0),
                total_target=current_group.get('target', 0)
            )
            current_group.update(pa_oee_data)
            summaries.append(current_group)
            # Start a new group for the next part.
            current_group = interval.copy()
            try:
                current_group['duration'] = int(current_group['duration'])
            except:
                pass
            try:
                current_group['parts_produced'] = int(current_group['parts_produced']) if current_group['parts_produced'] != "N/A" else "N/A"
            except:
                pass
            try:
                current_group['target'] = int(current_group['target']) if current_group['target'] != "N/A" else "N/A"
            except:
                pass

    # Process final group.
    try:
        group_start = datetime.strptime(current_group['start'], human_readable_format)
        group_end = datetime.strptime(current_group['end'], human_readable_format)
    except Exception:
        group_start = group_end = None
    planned = 0
    unplanned = 0
    if group_start and group_end:
        for dt_event in downtime_details:
            try:
                event_start = datetime.strptime(dt_event['start'], human_readable_format)
                event_end = datetime.strptime(dt_event['end'], human_readable_format)
            except Exception:
                continue
            if event_start >= group_start and event_end <= group_end:
                if dt_event['duration'] >= 240 and dt_event['overlap'] == "No Overlap":
                    planned += dt_event['duration']
                else:
                    unplanned += dt_event['duration']
    current_group['planned_minutes_down'] = planned
    current_group['unplanned_minutes_down'] = unplanned
    current_group['minutes_down'] = planned + unplanned
    if isinstance(current_group.get('duration'), int):
        current_group['total_potential_minutes'] = current_group['duration'] + current_group['minutes_down']
    else:
        current_group['total_potential_minutes'] = "N/A"
    try:
        cycle_time = float(current_group.get('cycle_time'))
    except Exception:
        cycle_time = None
    if (isinstance(current_group.get('total_potential_minutes'), int) and cycle_time and cycle_time > 0):
        current_group['target'] = int((current_group['total_potential_minutes'] * 60) / cycle_time)
    else:
        current_group['target'] = "N/A"
    pa_oee_data = compute_press_pa_oee(
        total_potential_minutes=current_group.get('total_potential_minutes', 0),
        planned_minutes_down=current_group.get('planned_minutes_down', 0),
        unplanned_minutes_down=current_group.get('unplanned_minutes_down', 0),
        total_minutes_up=current_group.get('duration', 0),
        cycle_time=current_group.get('cycle_time', 0),
        actual_parts=current_group.get('parts_produced', 0),
        total_target=current_group.get('target', 0)
    )
    current_group.update(pa_oee_data)
    summaries.append(current_group)
    return summaries





def press_runtime_wrapper(request):
    # Get parameters from POST or, if not provided, from GET (with defaults)
    start_date_str = request.POST.get('start_date') or request.GET.get('start_date', '')
    end_date_str = request.POST.get('end_date') or request.GET.get('end_date', '')
    machine_input = (request.POST.get('machine_id') or request.GET.get('machine_id', '272')).strip()
    machine_ids = [m.strip() for m in machine_input.split(',') if m.strip()]

    # This dictionary will hold each machine's data grouped nicely.
    machines_data = {}

    # Process if start and end dates are provided (via POST or URL)
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

            # If start date and end date are the same, subtract 24 hours from start date
            if start_date == end_date:
                start_date -= timedelta(hours=24)

            time_blocks = get_custom_time_blocks(start_date, end_date)
            if isinstance(time_blocks, str):
                return render(request, 'prod_query/press_oee.html', {'error_message': time_blocks})

            human_readable_format = '%Y-%m-%d %H:%M:%S'
            
            # Initialize groups for each machine
            for machine in machine_ids:
                machines_data[machine] = {
                    'part_numbers_data': [],
                    'downtime_events': [],
                    'downtime_entries': [],
                    'running_events': [],
                }
            
            with connections['prodrpt-md'].cursor() as cursor:
                for block_start, block_end in time_blocks:
                    start_ts = int(block_start.timestamp())
                    end_ts = int(block_end.timestamp())
                    block_start_str = block_start.strftime(human_readable_format)
                    block_end_str = block_end.strftime(human_readable_format)
                    
                    for machine in machine_ids:
                        # Fetch and store press changeover records per machine
                        part_records = fetch_press_changeovers(machine, start_ts, end_ts)
                        machines_data[machine]['part_numbers_data'].append({
                            'machine': machine,
                            'block_start': block_start_str,
                            'block_end': block_end_str,
                            'raw_block_start': block_start,
                            'raw_block_end': block_end,
                            'part_records': part_records
                        })

                        produced = fetch_production_count(machine, cursor, start_ts, end_ts)
                        total_downtime, downtime_details = calculate_downtime_press(machine, cursor, start_ts, end_ts)
                        
                        # Fetch PR downtime entries
                        called4helptime_iso = block_start.isoformat()
                        completedtime_iso = block_end.isoformat()
                        pr_entries_for_block = []
                        try:
                            raw_downtime_data = fetch_press_prdowntime1_entries(machine, called4helptime_iso, completedtime_iso)
                            if not (isinstance(raw_downtime_data, dict) and 'error' in raw_downtime_data):
                                for entry in raw_downtime_data:
                                    problem = entry[0]
                                    pr_start_time = entry[1]  # assumed datetime
                                    pr_end_time = entry[2]    # assumed datetime
                                    pr_idnumber = entry[3]
                                    if pr_end_time is not None:
                                        duration_minutes = int((pr_end_time - pr_start_time).total_seconds() / 60)
                                    else:
                                        duration_minutes = "Ongoing"
                                    pr_entry = {
                                        'machine': machine,
                                        'problem': problem,
                                        'start_time': pr_start_time,
                                        'end_time': pr_end_time,
                                        'duration_minutes': duration_minutes,
                                        'idnumber': pr_idnumber
                                    }
                                    pr_entries_for_block.append(pr_entry)
                                    machines_data[machine]['downtime_entries'].append(pr_entry)
                        except Exception as e:
                            print(f"[ERROR] Exception while fetching PR downtime entries for machine {machine}: {e}")
                        
                        # Process downtime details and aggregate annotated downtime events
                        annotated_details = []
                        non_overlap_total = 0
                        overlap_total = 0
                        for detail in downtime_details:
                            dt_start = datetime.fromtimestamp(detail['start'])
                            dt_end = datetime.fromtimestamp(detail['end'])
                            overlap_info = compute_overlap_label(dt_start, dt_end, pr_entries_for_block)
                            annotated_detail = {
                                'start': dt_start.strftime(human_readable_format),
                                'end': dt_end.strftime(human_readable_format),
                                'duration': detail['duration'],
                                'overlap': overlap_info['overlap'],
                                'pr_id': overlap_info['pr_id']
                            }
                            annotated_details.append(annotated_detail)
                            if overlap_info['overlap'] == "No Overlap":
                                if detail['duration'] < 240:
                                    overlap_total += detail['duration']
                                else:
                                    non_overlap_total += detail['duration']
                            else:
                                overlap_total += detail['duration']
                        
                        if total_downtime > 5:
                            machines_data[machine]['downtime_events'].append({
                                'machine': machine,
                                'block_start': block_start_str,
                                'block_end': block_end_str,
                                'produced': produced,
                                'downtime_minutes': total_downtime,
                                'non_overlap_minutes': non_overlap_total,
                                'overlap_minutes': overlap_total,
                                'details': annotated_details
                            })

                        # Calculate running intervals for this machine in this block
                        runtime_intervals = calculate_runtime_press(machine, cursor, start_ts, end_ts, running_threshold=5)
                        formatted_runtime_intervals = []
                        for interval in runtime_intervals:
                            active_info = get_active_part(interval, part_records, machine)
                            parts_produced = fetch_production_count(machine, cursor, interval['start'], interval['end'])
                            try:
                                cycle_time = float(active_info['cycle_time'])
                            except Exception:
                                cycle_time = None
                            target = int((interval['duration'] * 60) / cycle_time) if cycle_time and cycle_time > 0 else "N/A"
                            formatted_interval = {
                                'start': datetime.fromtimestamp(interval['start']).strftime(human_readable_format),
                                'end': datetime.fromtimestamp(interval['end']).strftime(human_readable_format),
                                'duration': interval['duration'],
                                'part': active_info['part'],
                                'cycle_time': active_info['cycle_time'],
                                'parts_produced': parts_produced,
                                'target': target
                            }
                            formatted_runtime_intervals.append(formatted_interval)
                        
                        aggregated_summary = summarize_contiguous_intervals(formatted_runtime_intervals, annotated_details, human_readable_format)
                        machines_data[machine]['running_events'].append({
                            'machine': machine,
                            'block_start': block_start_str,
                            'block_end': block_end_str,
                            'running_intervals': formatted_runtime_intervals,
                            'summary': aggregated_summary
                        })
            
            # Optionally, attach SPM chart data if needed (update part_numbers_data accordingly)
            for machine in machine_ids:
                machines_data[machine]['part_numbers_data'] = attach_spm_chart_data_to_blocks(
                    machines_data[machine]['part_numbers_data'], machine, interval=5
                )
            
        except Exception as e:
            print(f"[ERROR] Error processing time blocks: {e}")
    
    return render(request, 'prod_query/press_oee.html', {
        'machines_data': machines_data,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'machine_id': machine_input,
    })



def press_runtime_wrapper2(request):
    # First, try to get dates from the URL (GET parameters)
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    
    # If the form is submitted via POST, override with POST data
    if request.method == 'POST':
        start_date_str = request.POST.get('start_date', start_date_str)
        end_date_str = request.POST.get('end_date', end_date_str)
    
    machine_ids = ['272', '273', '277', '278']
    machines_data = {}

    if (request.method == 'POST' or start_date_str and end_date_str):
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

            # If start date and end date are the same, subtract 24 hours from start date
            if start_date == end_date:
                start_date -= timedelta(hours=24)

            time_blocks = get_custom_time_blocks(start_date, end_date)
            if isinstance(time_blocks, str):
                return render(request, 'prod_query/press_oee2.html', {'error_message': time_blocks})
            
            human_readable_format = '%Y-%m-%d %H:%M:%S'
            # Initialize groups for each machine
            for machine in machine_ids:
                machines_data[machine] = {
                    'part_numbers_data': [],
                    'downtime_events': [],
                    'downtime_entries': [],
                    'running_events': [],
                }
            
            with connections['prodrpt-md'].cursor() as cursor:
                for block_start, block_end in time_blocks:
                    start_ts = int(block_start.timestamp())
                    end_ts = int(block_end.timestamp())
                    block_start_str = block_start.strftime(human_readable_format)
                    block_end_str = block_end.strftime(human_readable_format)
                    
                    for machine in machine_ids:
                        # Fetch press changeover records
                        part_records = fetch_press_changeovers(machine, start_ts, end_ts)
                        machines_data[machine]['part_numbers_data'].append({
                            'machine': machine,
                            'block_start': block_start_str,
                            'block_end': block_end_str,
                            'raw_block_start': block_start,
                            'raw_block_end': block_end,
                            'part_records': part_records
                        })
                        
                        produced = fetch_production_count(machine, cursor, start_ts, end_ts)
                        total_downtime, downtime_details = calculate_downtime_press(machine, cursor, start_ts, end_ts)
                        
                        # Fetch PR downtime entries
                        called4helptime_iso = block_start.isoformat()
                        completedtime_iso = block_end.isoformat()
                        pr_entries_for_block = []
                        try:
                            raw_downtime_data = fetch_press_prdowntime1_entries(machine, called4helptime_iso, completedtime_iso)
                            if not (isinstance(raw_downtime_data, dict) and 'error' in raw_downtime_data):
                                for entry in raw_downtime_data:
                                    problem = entry[0]
                                    pr_start_time = entry[1]
                                    pr_end_time = entry[2]
                                    pr_idnumber = entry[3]
                                    if pr_end_time is not None:
                                        duration_minutes = int((pr_end_time - pr_start_time).total_seconds() / 60)
                                    else:
                                        duration_minutes = "Ongoing"
                                    pr_entry = {
                                        'machine': machine,
                                        'problem': problem,
                                        'start_time': pr_start_time,
                                        'end_time': pr_end_time,
                                        'duration_minutes': duration_minutes,
                                        'idnumber': pr_idnumber
                                    }
                                    pr_entries_for_block.append(pr_entry)
                                    machines_data[machine]['downtime_entries'].append(pr_entry)
                        except Exception as e:
                            print(f"[ERROR] Exception while fetching PR downtime entries for machine {machine}: {e}")
                        
                        # Process downtime details and aggregate annotated downtime events
                        annotated_details = []
                        non_overlap_total = 0
                        overlap_total = 0
                        for detail in downtime_details:
                            dt_start = datetime.fromtimestamp(detail['start'])
                            dt_end = datetime.fromtimestamp(detail['end'])
                            overlap_info = compute_overlap_label(dt_start, dt_end, pr_entries_for_block)
                            annotated_detail = {
                                'start': dt_start.strftime(human_readable_format),
                                'end': dt_end.strftime(human_readable_format),
                                'duration': detail['duration'],
                                'overlap': overlap_info['overlap'],
                                'pr_id': overlap_info['pr_id']
                            }
                            annotated_details.append(annotated_detail)
                            if overlap_info['overlap'] == "No Overlap":
                                if detail['duration'] < 240:
                                    overlap_total += detail['duration']
                                else:
                                    non_overlap_total += detail['duration']
                            else:
                                overlap_total += detail['duration']
                        
                        if total_downtime > 5:
                            machines_data[machine]['downtime_events'].append({
                                'machine': machine,
                                'block_start': block_start_str,
                                'block_end': block_end_str,
                                'produced': produced,
                                'downtime_minutes': total_downtime,
                                'non_overlap_minutes': non_overlap_total,
                                'overlap_minutes': overlap_total,
                                'details': annotated_details
                            })
                        
                        # Calculate running intervals for this machine in this block
                        runtime_intervals = calculate_runtime_press(machine, cursor, start_ts, end_ts, running_threshold=5)
                        formatted_runtime_intervals = []
                        for interval in runtime_intervals:
                            active_info = get_active_part(interval, part_records, machine)
                            parts_produced = fetch_production_count(machine, cursor, interval['start'], interval['end'])
                            try:
                                cycle_time = float(active_info['cycle_time'])
                            except Exception:
                                cycle_time = None
                            target = int((interval['duration'] * 60) / cycle_time) if cycle_time and cycle_time > 0 else "N/A"
                            formatted_interval = {
                                'start': datetime.fromtimestamp(interval['start']).strftime(human_readable_format),
                                'end': datetime.fromtimestamp(interval['end']).strftime(human_readable_format),
                                'duration': interval['duration'],
                                'part': active_info['part'],
                                'cycle_time': active_info['cycle_time'],
                                'parts_produced': parts_produced,
                                'target': target
                            }
                            formatted_runtime_intervals.append(formatted_interval)
                        
                        aggregated_summary = summarize_contiguous_intervals(formatted_runtime_intervals, annotated_details, human_readable_format)
                        machines_data[machine]['running_events'].append({
                            'machine': machine,
                            'block_start': block_start_str,
                            'block_end': block_end_str,
                            'running_intervals': formatted_runtime_intervals,
                            'summary': aggregated_summary
                        })
            
            # Optionally, attach SPM chart data if needed

        except Exception as e:
            print(f"[ERROR] Error processing time blocks: {e}")
    
    return render(request, 'prod_query/press_oee2.html', {
        'machines_data': machines_data,
        'start_date': start_date_str,
        'end_date': end_date_str,
    })




def aggregate_machine_groups(machines_data, group_definitions):
    """
    Aggregates machine totals for defined groups and returns a dictionary of aggregated totals.
    
    Args:
        machines_data (dict): Original machine data with each machine having a 'totals' dictionary.
        group_definitions (dict): Mapping from group label to a list of machine IDs to aggregate.
            Example: {'1500T': ['272', '273']}
    
    Returns:
        dict: A dictionary mapping each group label to a totals dictionary that mirrors the structure
              of an individual machine's totals.
    """
    aggregated = {}
    for group_label, machine_list in group_definitions.items():
        total_minutes_up = 0
        total_unplanned_down = 0
        total_planned_down = 0
        total_potential_minutes = 0
        total_parts_produced = 0
        total_target = 0
        weighted_cycle_sum = 0  # Sum of (machine weighted cycle * machine potential minutes)
        potential_for_weight = 0  # Sum of potential minutes (to weight the cycle time)
        block_range = ""
        
        for m in machine_list:
            machine_totals = machines_data.get(m, {}).get('totals')
            if machine_totals:
                total_minutes_up += machine_totals.get('total_minutes_up', 0)
                total_unplanned_down += machine_totals.get('total_unplanned_down', 0)
                total_planned_down += machine_totals.get('total_planned_down', 0)
                tp = machine_totals.get('total_potential_minutes', 0)
                total_potential_minutes += tp
                total_parts_produced += machine_totals.get('total_parts_produced', 0)
                tot_target = machine_totals.get('total_target', 0)
                if isinstance(tot_target, (int, float)):
                    total_target += tot_target
                # Use each machine's potential minutes as weight for its cycle time
                wc = machine_totals.get('weighted_cycle', 0)
                if isinstance(wc, (int, float)) and tp:
                    weighted_cycle_sum += wc * tp
                    potential_for_weight += tp
                # Use the block range from the first machine (if available)
                if not block_range:
                    block_range = machine_totals.get('block', "")
        
        if potential_for_weight:
            weighted_cycle = weighted_cycle_sum / potential_for_weight
        else:
            weighted_cycle = "N/A"
        
        # Compute availability, performance, and OEE
        availability = (total_minutes_up / total_potential_minutes) if total_potential_minutes else 0
        performance = (total_parts_produced / total_target) if total_target else 0
        oee = availability * performance
        
        aggregated[group_label] = {
            'block': block_range,
            'total_minutes_up': total_minutes_up,
            'total_unplanned_down': total_unplanned_down,
            'total_planned_down': total_planned_down,
            'total_potential_minutes': total_potential_minutes,
            'weighted_cycle': round(weighted_cycle, 2) if isinstance(weighted_cycle, (int, float)) else weighted_cycle,
            'total_parts_produced': total_parts_produced,
            'total_target': total_target,
            'availability': round(availability, 2),
            'performance': round(performance, 2),
            'oee': round(oee, 2)
        }
    return aggregated




def press_runtime_wrapper3(request):
    # Get parameters from POST (or default values)
    start_date_str = request.POST.get('start_date', '')
    end_date_str = request.POST.get('end_date', '')
    machine_ids = ['272', '273', '277', '278']

    # This dictionary will hold each machine's data grouped nicely.
    machines_data = {}

    if request.method == 'POST' and start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

            # If start date and end date are the same, subtract 24 hours from start date
            if start_date == end_date:
                start_date -= timedelta(hours=24)

            time_blocks = get_custom_time_blocks(start_date, end_date)
            if isinstance(time_blocks, str):
                return render(request, 'prod_query/press_oee3.html', {'error_message': time_blocks})

            human_readable_format = '%Y-%m-%d %H:%M:%S'
            
            # Initialize groups for each individual machine
            for machine in machine_ids:
                machines_data[machine] = {
                    'part_numbers_data': [],
                    'downtime_events': [],
                    'downtime_entries': [],
                    'running_events': [],
                    'totals': {}
                }
            
            with connections['prodrpt-md'].cursor() as cursor:
                for block_start, block_end in time_blocks:
                    start_ts = int(block_start.timestamp())
                    end_ts = int(block_end.timestamp())
                    block_start_str = block_start.strftime(human_readable_format)
                    block_end_str = block_end.strftime(human_readable_format)
                    
                    for machine in machine_ids:
                        # Fetch and store press changeover records per machine
                        part_records = fetch_press_changeovers(machine, start_ts, end_ts)
                        machines_data[machine]['part_numbers_data'].append({
                            'machine': machine,
                            'block_start': block_start_str,
                            'block_end': block_end_str,
                            'raw_block_start': block_start,
                            'raw_block_end': block_end,
                            'part_records': part_records
                        })

                        produced = fetch_production_count(machine, cursor, start_ts, end_ts)
                        total_downtime, downtime_details = calculate_downtime_press(machine, cursor, start_ts, end_ts)
                        
                        # Fetch PR downtime entries
                        called4helptime_iso = block_start.isoformat()
                        completedtime_iso = block_end.isoformat()
                        pr_entries_for_block = []
                        try:
                            raw_downtime_data = fetch_press_prdowntime1_entries(machine, called4helptime_iso, completedtime_iso)
                            if not (isinstance(raw_downtime_data, dict) and 'error' in raw_downtime_data):
                                for entry in raw_downtime_data:
                                    problem = entry[0]
                                    pr_start_time = entry[1]  # assumed datetime
                                    pr_end_time = entry[2]    # assumed datetime
                                    pr_idnumber = entry[3]
                                    if pr_end_time is not None:
                                        duration_minutes = int((pr_end_time - pr_start_time).total_seconds() / 60)
                                    else:
                                        duration_minutes = "Ongoing"
                                    pr_entry = {
                                        'machine': machine,
                                        'problem': problem,
                                        'start_time': pr_start_time,
                                        'end_time': pr_end_time,
                                        'duration_minutes': duration_minutes,
                                        'idnumber': pr_idnumber
                                    }
                                    pr_entries_for_block.append(pr_entry)
                                    machines_data[machine]['downtime_entries'].append(pr_entry)
                        except Exception as e:
                            print(f"[ERROR] Exception while fetching PR downtime entries for machine {machine}: {e}")
                        
                        # Process downtime details and aggregate annotated downtime events
                        annotated_details = []
                        non_overlap_total = 0
                        overlap_total = 0
                        for detail in downtime_details:
                            dt_start = datetime.fromtimestamp(detail['start'])
                            dt_end = datetime.fromtimestamp(detail['end'])
                            overlap_info = compute_overlap_label(dt_start, dt_end, pr_entries_for_block)
                            annotated_detail = {
                                'start': dt_start.strftime(human_readable_format),
                                'end': dt_end.strftime(human_readable_format),
                                'duration': detail['duration'],
                                'overlap': overlap_info['overlap'],
                                'pr_id': overlap_info['pr_id']
                            }
                            annotated_details.append(annotated_detail)
                            if overlap_info['overlap'] == "No Overlap":
                                if detail['duration'] < 240:
                                    overlap_total += detail['duration']
                                else:
                                    non_overlap_total += detail['duration']
                            else:
                                overlap_total += detail['duration']
                        
                        if total_downtime > 5:
                            machines_data[machine]['downtime_events'].append({
                                'machine': machine,
                                'block_start': block_start_str,
                                'block_end': block_end_str,
                                'produced': produced,
                                'downtime_minutes': total_downtime,
                                'non_overlap_minutes': non_overlap_total,
                                'overlap_minutes': overlap_total,
                                'details': annotated_details
                            })

                        # Calculate running intervals for this machine in this block
                        runtime_intervals = calculate_runtime_press(machine, cursor, start_ts, end_ts, running_threshold=5)
                        formatted_runtime_intervals = []
                        for interval in runtime_intervals:
                            active_info = get_active_part(interval, part_records, machine)
                            parts_produced = fetch_production_count(machine, cursor, interval['start'], interval['end'])
                            try:
                                cycle_time = float(active_info['cycle_time'])
                            except Exception:
                                cycle_time = None
                            target = int((interval['duration'] * 60) / cycle_time) if cycle_time and cycle_time > 0 else "N/A"
                            formatted_interval = {
                                'start': datetime.fromtimestamp(interval['start']).strftime(human_readable_format),
                                'end': datetime.fromtimestamp(interval['end']).strftime(human_readable_format),
                                'duration': interval['duration'],
                                'part': active_info['part'],
                                'cycle_time': cycle_time,
                                'parts_produced': parts_produced,
                                'target': target,
                                'unplanned_minutes_down': sum(d['duration'] for d in annotated_details if d['overlap'] != "No Overlap"),
                                'planned_minutes_down': sum(d['duration'] for d in annotated_details if d['overlap'] == "No Overlap")
                            }
                            formatted_runtime_intervals.append(formatted_interval)
                        
                        aggregated_summary = summarize_contiguous_intervals(formatted_runtime_intervals, annotated_details, human_readable_format)
                        machines_data[machine]['running_events'].append({
                            'machine': machine,
                            'block_start': block_start_str,
                            'block_end': block_end_str,
                            'running_intervals': formatted_runtime_intervals,
                            'summary': aggregated_summary
                        })
            
            # After processing all blocks, compute totals for each machine
            for machine, data in machines_data.items():
                total_minutes_up = 0
                total_unplanned_down = 0
                total_planned_down = 0
                total_potential_minutes = 0
                total_parts_produced = 0
                total_target = 0
                weighted_cycle_sum = 0

                for event in data.get('running_events', []):
                    summaries = event.get('summary')
                    if summaries:
                        for summary in summaries:
                            total_minutes_up += summary.get('duration', 0)
                            total_unplanned_down += summary.get('unplanned_minutes_down', 0)
                            total_planned_down += summary.get('planned_minutes_down', 0)
                            total_potential_minutes += summary.get('total_potential_minutes', 0)
                            total_parts_produced += summary.get('parts_produced', 0)
                            target_val = summary.get('target')
                            if isinstance(target_val, (int, float)):
                                total_target += target_val
                            cycle_time = summary.get('cycle_time')
                            potential = summary.get('total_potential_minutes', 0)
                            if cycle_time and potential:
                                weighted_cycle_sum += cycle_time * potential

                if total_potential_minutes > 0:
                    weighted_cycle = weighted_cycle_sum / total_potential_minutes
                    weighted_cycle = round(weighted_cycle, 2)
                else:
                    weighted_cycle = None

                overall_availability = total_minutes_up / total_potential_minutes if total_potential_minutes else 0
                overall_performance = total_parts_produced / total_target if total_target else 0
                overall_oee = overall_availability * overall_performance

                machines_data[machine]['totals'] = {
                    'block': f"{start_date_str} - {end_date_str}",
                    'total_minutes_up': total_minutes_up,
                    'total_unplanned_down': total_unplanned_down,
                    'total_planned_down': total_planned_down,
                    'total_potential_minutes': total_potential_minutes,
                    'weighted_cycle': weighted_cycle if weighted_cycle is not None else "N/A",
                    'total_parts_produced': total_parts_produced,
                    'total_target': total_target,
                    'availability': overall_availability,
                    'performance': overall_performance,
                    'oee': overall_oee
                }
            
            # --- Aggregate groups ---
            group_definitions = {
                '1500T': ['272', '273']  # The group for 1500T aggregates these machines.
            }
            aggregated_groups = aggregate_machine_groups(machines_data, group_definitions)
            # Add the aggregated group rows into machines_data and mark them with a flag (group=True)
            for group_label, totals in aggregated_groups.items():
                machines_data[group_label] = {'totals': totals, 'group': True}
            
            # Build a list of machine entries for sorted display.
            # Order: first Press 272 and 273, then group "1500T", then the rest.
            sorted_machines_data = []
            for machine in ['272', '273']:
                if machine in machines_data:
                    sorted_machines_data.append({'machine': machine, 'data': machines_data[machine]})
            if '1500T' in machines_data:
                sorted_machines_data.append({'machine': '1500T', 'data': machines_data['1500T']})
            for machine in ['277', '278']:
                if machine in machines_data:
                    sorted_machines_data.append({'machine': machine, 'data': machines_data[machine]})


        except Exception as e:
            print(f"[ERROR] Error processing time blocks: {e}")
    
    return render(request, 'prod_query/press_oee3.html', {
        'sorted_machines_data': sorted_machines_data if 'sorted_machines_data' in locals() else [],
        'start_date': start_date_str,
        'end_date': end_date_str,
    })





def compute_cycle_time(timestamps):
    """
    Computes the cycle time based on the differences between sorted timestamps.
    Uses a weighted average of the top 3 most frequent cycle times.
    """
    if len(timestamps) < 2:
        return 0  # No production, cycle time should be 0

    timestamps = np.sort(timestamps)  # Ensure timestamps are sorted
    time_diffs = np.diff(timestamps)  # Compute time differences
    time_diffs = np.round(time_diffs).astype(int)  # Round to nearest second

    unique_times, counts = np.unique(time_diffs, return_counts=True)  # Find unique cycle times and occurrences
    sorted_indices = np.argsort(counts)[::-1]  # Sort occurrences in descending order

    # Get top 3 cycle times
    top_3_times = unique_times[sorted_indices[:5]]
    top_3_counts = counts[sorted_indices[:5]]

    print(f'Top 3 times:  {top_3_times}')
    print(f'Top 3 counts: {top_3_counts}')

    # Compute weighted average cycle time
    weighted_cycle_time = np.sum(top_3_times * top_3_counts) / np.sum(top_3_counts)

    return weighted_cycle_time

def production_from_cycletime(cycle_time):
    """
    Calculates theoretical production for an hour based on the cycle time.
    """
    if cycle_time == 0:
        return 0  # No production if cycle time is zero
    return int(3600 / cycle_time)  # How many parts could be made in 1 hour

def fetch_timestamps_for_timeblocks():
    """
    Fetches timestamps, computes cycle time for every hour, and prints debugging information.
    """
    asset_num = '272'
    start_date = datetime(2025, 2, 15)
    end_date = datetime(2025, 3, 1)

    # Get custom time blocks
    time_blocks = get_custom_time_blocks(start_date, end_date)

    if isinstance(time_blocks, str):
        print("Error:", time_blocks)
        return

    query = """
        SELECT TimeStamp 
        FROM GFxPRoduction
        WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s
        ORDER BY TimeStamp ASC;
    """

    all_hourly_timestamps = []

    print("\n=== DEBUGGING TIMESTAMP COUNT, CYCLE TIME & THEORETICAL PRODUCTION PER HOUR ===")

    with connections['prodrpt-md'].cursor() as cursor:
        for block_start, block_end in time_blocks:
            print(f"\nTime Block: {block_start} to {block_end}")

            current_hour = block_start

            while current_hour < block_end:
                next_hour = current_hour + timedelta(hours=1)
                if next_hour > block_end:
                    next_hour = block_end

                start_timestamp = int(current_hour.timestamp())
                end_timestamp = int(next_hour.timestamp())

                # Fetch all timestamps
                cursor.execute(query, (asset_num, start_timestamp, end_timestamp))
                timestamps = [row[0] for row in cursor.fetchall()]
                
                # Store fetched timestamps
                all_hourly_timestamps.append(timestamps)

                print(f"\n⏳ Hour: {current_hour.strftime('%Y-%m-%d %H:%M:%S')} - {next_hour.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  🔍 Raw Timestamps: {timestamps}")

                # Compute cycle time
                cycle_time = compute_cycle_time(np.array(timestamps))

                # Compute theoretical production
                theoretical_production = int(3600 / cycle_time) if cycle_time > 0 else 0

                # Print summary
                print(f"  ✅ Entries: {len(timestamps)}")
                print(f"  ⏳ Cycle Time: {cycle_time:.2f} seconds")
                print(f"  🏭 Theoretical Production: {theoretical_production} parts")

                current_hour = next_hour

    print("\n=== END OF DEBUGGING OUTPUT ===")
    
    return all_hourly_timestamps  # Returning for further processing





def test_view(request):
    """
    Django view that calls fetch_timestamps_for_timeblocks and returns the data as JSON.
    """
    try:
        timestamps = fetch_timestamps_for_timeblocks()
        return JsonResponse({"timestamps": timestamps})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# I used that to make the press runtime wrapper which can handle multiple machines much better

# def press_runtime(request):
#     time_blocks = []
#     downtime_events = []      # Calculated machine downtime events (over 5 min)
#     downtime_entries = []     # PR downtime entries (with pre-calculated duration)
#     part_numbers_data = []    # To store part numbers data for each time block
#     running_events = []       # New list for running intervals

#     # Initialize these variables with default values
#     start_date_str = ""
#     end_date_str = ""
#     machine_input = ""
#     header = "Generated Time Blocks"    # Default header

#     if request.method == 'POST':
#         start_date_str = request.POST.get('start_date', '')
#         end_date_str = request.POST.get('end_date', '')
#         machine_input = request.POST.get('machine_id', '').strip()  # Get the machine number(s)

#         if not machine_input:
#             machine_input = '272'

#         machine_ids = [m.strip() for m in machine_input.split(',') if m.strip()]
#         header_parts = []
#         for m in machine_ids:
#             if m in ['272', '273']:
#                 header_parts.append(f"1500T Press {m}")
#             else:
#                 header_parts.append(f"Press {m}")
#         header = "Generated Time Blocks for " + ", ".join(header_parts)

#         try:
#             if start_date_str and end_date_str:
#                 start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
#                 end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

#                 # Get custom time blocks (assumed to be defined elsewhere)
#                 time_blocks = get_custom_time_blocks(start_date, end_date)
#                 if isinstance(time_blocks, str):
#                     return render(request, 'prod_query/press_oee.html', {'error_message': time_blocks})

#                 human_readable_format = '%Y-%m-%d %H:%M:%S'

#                 with connections['prodrpt-md'].cursor() as cursor:
#                     for block_start, block_end in time_blocks:
#                         start_timestamp = int(block_start.timestamp())
#                         end_timestamp = int(block_end.timestamp())

#                         for machine in machine_ids:
#                             # Fetch press changeover records for the machine
#                             part_records = fetch_press_changeovers(machine, start_timestamp, end_timestamp)
#                             part_numbers_data.append({
#                                 'machine': machine,
#                                 'block_start': block_start.strftime(human_readable_format),
#                                 'block_end': block_end.strftime(human_readable_format),
#                                 'raw_block_start': block_start,
#                                 'raw_block_end': block_end,
#                                 'part_records': part_records
#                             })

#                             produced = fetch_production_count(machine, cursor, start_timestamp, end_timestamp)
#                             total_downtime, downtime_details = calculate_downtime_press(machine, cursor, start_timestamp, end_timestamp)

#                             block_start_str = block_start.strftime(human_readable_format)
#                             block_end_str = block_end.strftime(human_readable_format)

#                             # Fetch PR downtime entries (existing logic)
#                             called4helptime_iso = block_start.isoformat()
#                             completedtime_iso = block_end.isoformat()
#                             pr_entries_for_block = []
#                             try:
#                                 raw_downtime_data = fetch_press_prdowntime1_entries(machine, called4helptime_iso, completedtime_iso)
#                                 if isinstance(raw_downtime_data, dict) and 'error' in raw_downtime_data:
#                                     print(f"[ERROR] Error fetching PR downtime entries: {raw_downtime_data['error']}")
#                                 else:
#                                     for entry in raw_downtime_data:
#                                         problem = entry[0]
#                                         pr_start_time = entry[1]  # assumed datetime
#                                         pr_end_time = entry[2]    # assumed datetime
#                                         pr_idnumber = entry[3]
#                                         if pr_end_time is not None:
#                                             duration_minutes = int((pr_end_time - pr_start_time).total_seconds() / 60)
#                                         else:
#                                             duration_minutes = "Ongoing"
#                                         pr_entry = {
#                                             'machine': machine,
#                                             'problem': problem,
#                                             'start_time': pr_start_time,
#                                             'end_time': pr_end_time,
#                                             'duration_minutes': duration_minutes,
#                                             'idnumber': pr_idnumber
#                                         }
#                                         pr_entries_for_block.append(pr_entry)
#                                         downtime_entries.append(pr_entry)
#                             except Exception as e:
#                                 print(f"[ERROR] Exception while fetching PR downtime entries for machine {machine}: {e}")

#                             annotated_details = []
#                             non_overlap_total = 0
#                             overlap_total = 0
#                             for detail in downtime_details:
#                                 dt_start = datetime.fromtimestamp(detail['start'])
#                                 dt_end = datetime.fromtimestamp(detail['end'])
#                                 overlap_info = compute_overlap_label(dt_start, dt_end, pr_entries_for_block)
#                                 annotated_detail = {
#                                     'start': dt_start.strftime(human_readable_format),
#                                     'end': dt_end.strftime(human_readable_format),
#                                     'duration': detail['duration'],
#                                     'overlap': overlap_info['overlap'],
#                                     'pr_id': overlap_info['pr_id']
#                                 }
#                                 annotated_details.append(annotated_detail)

#                                 if overlap_info['overlap'] == "No Overlap":
#                                     if detail['duration'] < 240:
#                                         overlap_total += detail['duration']
#                                     else:
#                                         non_overlap_total += detail['duration']
#                                 else:
#                                     overlap_total += detail['duration']

#                             if total_downtime > 5:
#                                 downtime_events.append({
#                                     'machine': machine,
#                                     'block_start': block_start_str,
#                                     'block_end': block_end_str,
#                                     'produced': produced,
#                                     'downtime_minutes': total_downtime,
#                                     'non_overlap_minutes': non_overlap_total,
#                                     'overlap_minutes': overlap_total,
#                                     'details': annotated_details
#                                 })

#                             # ----- New: Calculate running intervals for this machine in this block -----
#                             runtime_intervals = calculate_runtime_press(machine, cursor, start_timestamp, end_timestamp, running_threshold=5)
#                            # ... within your loop for each time block and machine ...
#                         formatted_runtime_intervals = []
#                         for interval in runtime_intervals:
#                             active_info = get_active_part(interval, part_records, machine)
#                             parts_produced = fetch_production_count(machine, cursor, interval['start'], interval['end'])
                            
#                             try:
#                                 cycle_time = float(active_info['cycle_time'])
#                             except Exception:
#                                 cycle_time = None
#                             if cycle_time and cycle_time > 0:
#                                 target = int((interval['duration'] * 60) / cycle_time)
#                             else:
#                                 target = "N/A"
                            
#                             formatted_interval = {
#                                 'start': datetime.fromtimestamp(interval['start']).strftime(human_readable_format),
#                                 'end': datetime.fromtimestamp(interval['end']).strftime(human_readable_format),
#                                 'duration': interval['duration'],
#                                 'part': active_info['part'],
#                                 'cycle_time': active_info['cycle_time'],
#                                 'parts_produced': parts_produced,
#                                 'target': target
#                             }
#                             formatted_runtime_intervals.append(formatted_interval)

#                         # Aggregate contiguous intervals by part number
#                         aggregated_summary = summarize_contiguous_intervals(formatted_runtime_intervals, annotated_details, human_readable_format)

#                         running_events.append({
#                             'machine': machine,
#                             'block_start': block_start_str,
#                             'block_end': block_end_str,
#                             'running_intervals': formatted_runtime_intervals,
#                             'summary': aggregated_summary  # Include the summary in the data passed to the template
#                         })

#         except Exception as e:
#             print(f"[ERROR] Error processing time blocks: {e}")

#         # --- Attach SPM chart data to each time block ---
#         part_numbers_data = attach_spm_chart_data_to_blocks(part_numbers_data, machine_input, interval=5)

#     return render(request, 'prod_query/press_oee.html', {
#         'time_blocks': time_blocks,
#         'downtime_events': downtime_events,
#         'downtime_entries': downtime_entries,
#         'part_numbers_data': part_numbers_data,
#         'running_events': running_events,  # Pass the new running events data to the template
#         'header': header,
#         'start_date': start_date_str,
#         'end_date': end_date_str,
#         'machine_id': machine_input,
#     })
















# =============================================================================
# =============================================================================
# ================================ OA By Day ==================================
# =============================================================================
# =============================================================================



# Global mapping for scrap lines.
line_scrap_mapping = {
    "AB1V Reaction": ["AB1V Reaction", "AB1V Reaction Gas"],
    "AB1V Input": ["AB1V Input", "AB1V Input Gas"],
    "AB1V Overdrive": ["AB1V Overdrive", "AB1V Overdrive Gas"],
    "10R80": ["10R80"],
    "10R60": ["10R60"],
    "10R140": ["10R140"],
    "Presses": ["Compact"],
}

# --- Helper Functions ---

def oa_by_day(request):
    """
    Render the production data page with an inline range calendar.
    The default is set so that the start_date is yesterday at 7am and the end_date is today at 7am.
    """
    import datetime
    from datetime import timedelta

    # Set defaults: start at 7am yesterday, end at 7am today.
    now = datetime.datetime.now()
    default_end = now.replace(hour=7, minute=0, second=0, microsecond=0)
    # If now is before 7am today, adjust default_end to 7am of today already passed
    if now < default_end:
        default_end -= timedelta(days=1)
    default_start = default_end - timedelta(days=1)

    start_date_str = request.GET.get('start_date', default_start.strftime('%Y-%m-%d %H:%M'))
    end_date_str = request.GET.get('end_date', default_end.strftime('%Y-%m-%d %H:%M'))

    # For display in header, compute previous_day (for example, the day before start_date)
    start_date_obj = datetime.datetime.strptime(start_date_str, '%Y-%m-%d %H:%M')
    previous_day_str = (start_date_obj.date() - timedelta(days=0)).strftime('%Y-%m-%d')

    context = {
        'start_date': start_date_str,  # e.g. "2025-04-07 07:00"
        'end_date': end_date_str,      # e.g. "2025-04-08 07:00"
        'previous_day': previous_day_str,
        'lines': lines  # your global structure for lines/operations/machines
    }
    return render(request, 'prod_query/oa_by_day.html', context)


def stip_weekends(start_date_str, end_date_str):
    """
    Given two date strings, remove any portions that fall between Friday 23:00 and Sunday 23:00.
    The expected format is "Y-m-d H:i". If the string doesn't include a time, defaults to midnight.
    Returns a list of (start_datetime, end_datetime) tuples.
    """
    import datetime
    from datetime import timedelta, time

    dt_format = "%Y-%m-%d %H:%M"
    date_only_format = "%Y-%m-%d"

    def parse_date(date_str):
        # Try the full date-time format.
        try:
            return datetime.datetime.strptime(date_str, dt_format)
        except ValueError:
            # Fall back to date-only format and assume a default time.
            try:
                date_only = datetime.datetime.strptime(date_str, date_only_format)
                # You might choose a different default time.
                return datetime.datetime.combine(date_only.date(), time(0, 0))
            except ValueError as e:
                raise ValueError(f"Invalid date format for {date_str}") from e

    start = parse_date(start_date_str)
    end = parse_date(end_date_str)

    def is_in_weekend(dt):
        # Define weekend as from Friday 23:00 to Sunday 23:00.
        if dt.weekday() == 4 and dt.time() >= time(23, 0):
            return True
        if dt.weekday() == 5:  # Saturday all day
            return True
        if dt.weekday() == 6 and dt.time() < time(23, 0):
            return True
        return False

    intervals = []
    current = start
    while current < end:
        if is_in_weekend(current):
            # Skip ahead to the end of the weekend.
            if current.weekday() == 4:
                weekend_start = datetime.datetime.combine(current.date(), time(23, 0))
            else:
                days_back = current.weekday() - 4  # Saturday:1, Sunday:2
                friday_date = current.date() - timedelta(days=days_back)
                weekend_start = datetime.datetime.combine(friday_date, time(23, 0))
            weekend_end = weekend_start + timedelta(days=2)  # Until Sunday 23:00
            current = weekend_end
            continue
        else:
            # Determine the next upcoming weekend.
            if current.weekday() == 4 and current.time() < time(23, 0):
                upcoming_weekend = datetime.datetime.combine(current.date(), time(23, 0))
            else:
                days_until_friday = (4 - current.weekday()) % 7
                upcoming_friday = current.date() + timedelta(days=days_until_friday)
                upcoming_weekend = datetime.datetime.combine(upcoming_friday, time(23, 0))
            block_end = min(end, upcoming_weekend)
            intervals.append((current, block_end))
            current = block_end
    return intervals


def compute_oee_metrics(
    totals_by_line,
    overall_total_produced,
    overall_total_target,
    overall_total_potential_minutes,
    overall_unplanned_downtime_minutes,
    overall_planned_downtime_minutes,
    overall_scrap_total,
    scrap_totals_by_line,
    potential_minutes_by_line,
    planned_downtime_totals_by_line,
    unplanned_downtime_totals_by_line
):
    """
    Compute OEE metrics overall and by line using the following formulas:
    
      1. Planned Production Time (PPT) = total_potential_minutes - planned_downtime
      2. Run Time = PPT - (unplanned_downtime)
      3. ideal_cycle_time = PPT / target_parts  (target_parts is overall_total_target or per-line target)
      4. Availability = run_time / PPT
      5. Performance = (ideal_cycle_time * actual_parts) / run_time
      6. Quality = (total produced - scrap) / total produced
      7. OEE = Availability * Performance * Quality
    """
    # Convert overall parameters to floats to avoid type issues
    overall_total_produced = float(overall_total_produced)
    overall_total_target = float(overall_total_target)
    overall_total_potential_minutes = float(overall_total_potential_minutes)
    overall_unplanned_downtime_minutes = float(overall_unplanned_downtime_minutes)
    overall_planned_downtime_minutes = float(overall_planned_downtime_minutes)
    overall_scrap_total = float(overall_scrap_total)

    # overall_total_produced = 500
    # overall_total_target = 1000
    # overall_total_potential_minutes = 480
    # overall_unplanned_downtime_minutes = 120
    # overall_planned_downtime_minutes = 120
    # overall_scrap_total = 0
    
    # Overall metrics calculations
    overall_ppt = overall_total_potential_minutes - overall_planned_downtime_minutes
    overall_run_time = overall_ppt - (overall_unplanned_downtime_minutes)
    overall_ideal_cycle_time = overall_ppt / overall_total_target if overall_total_target > 0 else 0.0


    overall_runtime = overall_total_potential_minutes - overall_planned_downtime_minutes - overall_unplanned_downtime_minutes
    overall_uptime_ratio = overall_runtime / overall_total_potential_minutes


    overall_adjusted_target = overall_total_target * overall_uptime_ratio


    overall_availability = overall_run_time / overall_ppt if overall_ppt > 0 else 0.0
    # overall_performance = (overall_ideal_cycle_time * overall_total_produced) / overall_run_time if overall_run_time > 0 else 0.0

    if overall_adjusted_target == 0:
        performance = 0
    else:
        overall_performance = overall_total_produced / overall_adjusted_target
    
    overall_quality = (overall_total_produced - overall_scrap_total) / overall_total_produced if overall_total_produced > 0 else 0.0
    overall_oee = overall_availability * overall_performance * overall_quality

    lines_metrics = {}
    # By-line metrics calculations
    for line, totals in totals_by_line.items():
        produced = float(totals.get("total_produced", 0))
        target = float(totals.get("total_target", 0))
        potential = float(potential_minutes_by_line.get(line, 0))
        planned_downtime = float(planned_downtime_totals_by_line.get(line, 0))
        unplanned_downtime = float(unplanned_downtime_totals_by_line.get(line, 0))
        scrap = float(scrap_totals_by_line.get(line, 0))

        # produced = 500
        # target = 1000
        # potential = 7200
        # planned_downtime = 1800
        # unplanned_downtime = 1800
        # scrap = 0
        
        ppt = potential - planned_downtime
        run_time = ppt - (unplanned_downtime)
        ideal_cycle_time = ppt / target if target > 0 else 0.0
        

        runtime = potential - unplanned_downtime - planned_downtime
        uptime_ratio = runtime / potential


        adjusted_target = target * uptime_ratio

        availability = run_time / ppt if ppt > 0 else 0.0
        # performance = (ideal_cycle_time * produced) / run_time if run_time > 0 else 0.0
        if adjusted_target == 0:
            performance = 0
        else:
            performance = produced / adjusted_target
        quality = (produced - scrap) / produced if produced > 0 else 0.0
        oee = availability * performance * quality
        
        lines_metrics[line] = {
            "ppt": ppt,
            "run_time": run_time,
            "ideal_cycle_time": ideal_cycle_time,
            "A": availability,
            "P": performance,
            "Q": quality,
            "OEE": oee
        }
        
    overall_metrics = {
        "ppt": overall_ppt,
        "run_time": overall_run_time,
        "ideal_cycle_time": overall_ideal_cycle_time,
        "A": overall_availability,
        "P": overall_performance,
        "Q": overall_quality,
        "OEE": overall_oee
    }
    
    return {"overall": overall_metrics, "lines": lines_metrics}


def fetch_prdowntime1_entries_with_id(assetnum, called4helptime, completedtime):
    """
    A copy of `fetch_prdowntime1_entries` that also fetches the `idnumber` column.
    
    :param assetnum: The asset number of the machine.
    :param called4helptime: The start of the time window (ISO 8601 format).
    :param completedtime: The end of the time window (ISO 8601 format).
    :return: List of rows matching the criteria, each row shaped like:
             [idnumber, problem, called4helptime, completedtime].
    """
    import re
    import datetime, os, importlib
    from datetime import datetime

    try:
        # Strip trailing letters from assetnum (e.g., "1703R" or "1703L" becomes "1703")
        assetnum = re.sub(r'[A-Za-z]+$', '', assetnum)

        # Parse the dates to ensure they are in datetime format.
        called4helptime = datetime.fromisoformat(called4helptime)
        completedtime = datetime.fromisoformat(completedtime)

        # Dynamically import `get_db_connection` from settings.py.
        settings_path = os.path.join(os.path.dirname(__file__), '../pms/settings.py')
        spec = importlib.util.spec_from_file_location("settings", settings_path)
        settings = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(settings)
        get_db_connection = settings.get_db_connection

        # Get database connection.
        conn = get_db_connection()
        cursor = conn.cursor()

        # Raw SQL query to fetch the required data, now including `idnumber`.
        query = """
        SELECT
            idnumber,
            problem,
            called4helptime,
            completedtime
        FROM pr_downtime1
        WHERE assetnum = %s
          AND (
            -- Entries that start before the window and bleed into the window.
            (called4helptime < %s AND (completedtime >= %s OR completedtime IS NULL))
            -- Entries that start within the window.
            OR (called4helptime >= %s AND called4helptime <= %s)
            -- Entries that start in the window and bleed out.
            OR (called4helptime >= %s AND called4helptime <= %s AND (completedtime > %s OR completedtime IS NULL))
            -- Entries that bleed both before and after the window.
            OR (called4helptime < %s AND (completedtime > %s OR completedtime IS NULL))
          )
        """

        # Execute the query.
        cursor.execute(query, (
            assetnum,
            called4helptime, called4helptime,
            called4helptime, completedtime,
            called4helptime, completedtime, completedtime,
            called4helptime, completedtime
        ))

        # Fetch all rows.
        rows = cursor.fetchall()

        # Close the cursor and connection.
        cursor.close()
        conn.close()

        return rows

    except Exception as e:
        return {"error": str(e)}


def fetch_machine_target(machine_id, line_name, effective_timestamp):
    """
    Fetches the most recent target for a given machine and line from the OAMachineTargets table.
    Only targets with effective_date_unix less than or equal to the effective_timestamp are considered.
    Returns the target value if found, or None otherwise.
    """
    target_record = (
        OAMachineTargets.objects.filter(
            machine_id=machine_id,
            line=line_name,
            effective_date_unix__lte=effective_timestamp
        )
        .order_by('-effective_date_unix')
        .first()
    )
    return target_record.target if target_record else None


def fetch_daily_scrap_data(cursor, start_time, end_time):
    """
    Fetches scrap totals from the tkb_scrap table for the given time window.
    Aggregates scrap_amount by production line using line_scrap_mapping.
    
    Assumes that the `date_current` column is stored as a datetime.
    """
    start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
    end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
    
    query = """
        SELECT scrap_line, SUM(scrap_amount)
        FROM tkb_scrap
        WHERE date_current BETWEEN %s AND %s
        GROUP BY scrap_line;
    """
    cursor.execute(query, [start_time_str, end_time_str])
    rows = cursor.fetchall()

    # Initialize totals for each production line defined in our mapping.
    scrap_totals_by_line = {line: 0 for line in line_scrap_mapping.keys()}
    for scrap_line, total in rows:
        for prod_line, valid_values in line_scrap_mapping.items():
            if scrap_line in valid_values:
                scrap_totals_by_line[prod_line] += total

    overall_scrap_total = sum(scrap_totals_by_line.values())
    return scrap_totals_by_line, overall_scrap_total


def parse_date_range(request):
    import datetime, os, importlib, json
    """Parses start_date and end_date from the request and returns computed values."""
    default_date_str = datetime.datetime.today().strftime('%Y-%m-%d')
    start_date_str = request.GET.get('start_date', default_date_str)
    end_date_str = request.GET.get('end_date', default_date_str)
    
    try:
        start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d %H:%M')
        end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d %H:%M')
        auto_subtract = False
    except ValueError:
        start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d')
        auto_subtract = True

    if auto_subtract:
        start_date = start_date.replace(hour=7, minute=0, second=0)
        end_date = end_date.replace(hour=7, minute=0, second=0)
        start_time = start_date - datetime.timedelta(days=1)
    else:
        start_time = start_date

    end_time = end_date
    start_timestamp = int(start_time.timestamp())
    end_timestamp = int(end_time.timestamp())
    queried_minutes = (end_timestamp - start_timestamp) / 60
    previous_day_str = (start_date.date() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    
    return start_time, end_time, start_timestamp, end_timestamp, queried_minutes, previous_day_str


def get_production_data_for_machine(cursor, machine, machine_number, start_timestamp, end_timestamp, op, queried_minutes, line_name):
    import datetime
    """Fetches production parts data and target for a given machine."""
    target_val = fetch_machine_target(machine_number, line_name, start_timestamp)
    target = int(target_val * (queried_minutes / 7200)) if target_val is not None else None

    if machine.get("part_numbers") and isinstance(machine.get("part_numbers"), list) and machine["part_numbers"]:
        placeholders = ", ".join(["%s"] * len(machine["part_numbers"]))
        query_str = f"""
            SELECT Part, COUNT(*)
            FROM GFxPRoduction
            WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s
            AND Part IN ({placeholders})
            GROUP BY Part;
        """
        params = [machine_number, start_timestamp, end_timestamp] + machine["part_numbers"]
        cursor.execute(query_str, params)
        produced_parts_by_part = {}
        row = cursor.fetchone()
        while row is not None:
            produced_parts_by_part[row[0]] = row[1]
            row = cursor.fetchone()
        total_produced = sum(produced_parts_by_part.values())
        production_entry = {
            "operation": op,
            "target": target,
            "produced_parts": total_produced,
            "produced_parts_by_part": produced_parts_by_part,
            "part_numbers": machine["part_numbers"],
        }
    else:
        query_str = """
            SELECT COUNT(*)
            FROM GFxPRoduction
            WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s;
        """
        cursor.execute(query_str, (machine_number, start_timestamp, end_timestamp))
        # Process the single result row.
        row = cursor.fetchone()
        total_produced = row[0] if row and row[0] is not None else 0
        production_entry = {
            "operation": op,
            "target": target,
            "produced_parts": total_produced,
            "part_numbers": None,
        }
    return production_entry


def calculate_downtime_events(cursor, machine_number, start_timestamp, end_timestamp):
    import datetime
    """Calculates downtime events (gaps >5 minutes) based on production timestamps."""
    query_ts = """
        SELECT TimeStamp
        FROM GFxPRoduction
        WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s
        ORDER BY TimeStamp ASC;
    """
    cursor.execute(query_ts, (machine_number, start_timestamp, end_timestamp))
    
    downtime_seconds = 0
    downtime_events = []
    previous_ts = start_timestamp

    # Iterate row-by-row using fetchone() to save memory.
    row = cursor.fetchone()
    while row is not None:
        ts = row[0]
        gap = ts - previous_ts
        if gap > 300:  # Only consider gaps > 5 minutes
            downtime_seconds += gap
            event_minutes = int(gap / 60)
            event_start_str = datetime.datetime.fromtimestamp(previous_ts).strftime("%Y-%m-%d %H:%M")
            event_end_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            downtime_events.append({
                "start": event_start_str,
                "end": event_end_str,
                "minutes_down": event_minutes
            })
        previous_ts = ts
        row = cursor.fetchone()

    # Check the final gap between the last timestamp and the end of the period.
    gap = end_timestamp - previous_ts
    if gap > 300:
        downtime_seconds += gap
        event_minutes = int(gap / 60)
        event_start_str = datetime.datetime.fromtimestamp(previous_ts).strftime("%Y-%m-%d %H:%M")
        event_end_str = datetime.datetime.fromtimestamp(end_timestamp).strftime("%Y-%m-%d %H:%M")
        downtime_events.append({
            "start": event_start_str,
            "end": event_end_str,
            "minutes_down": event_minutes
        })

    return downtime_seconds, downtime_events


def get_pr_downtime_entries(machine_number, start_time, end_time):
    import datetime, os, importlib, json
    """Fetches and processes PR downtime entries for a machine."""
    pr_entries = fetch_prdowntime1_entries_with_id(machine_number, start_time.isoformat(), end_time.isoformat())
    pr_downtime_entries = []
    for entry in pr_entries:
        pr_id = entry[0]
        problem = entry[1]
        called = entry[2]
        completed = entry[3] if len(entry) > 3 else None

        try:
            dt_called = datetime.datetime.fromisoformat(called) if isinstance(called, str) else called
        except Exception:
            dt_called = None
        try:
            dt_completed = datetime.datetime.fromisoformat(completed) if (completed and isinstance(completed, str)) else completed
        except Exception:
            dt_completed = None

        minutes_down = int((dt_completed - dt_called).total_seconds() / 60) if dt_called and dt_completed else "N/A"
        pr_entry = {
            "idnumber": pr_id,
            "problem": problem,
            "start_time": dt_called,
            "end_time": dt_completed,
            "minutes_down": minutes_down,
        }
        pr_downtime_entries.append(pr_entry)
    return pr_downtime_entries


def calculate_planned_downtime(downtime_events, pr_downtime_entries):
    import datetime, os, importlib, json
    """
    Calculates planned downtime as the sum of downtime event minutes
    that do not overlap any PR downtime entry and are longer than 240 minutes.
    """
    planned_downtime_minutes = 0
    pr_intervals = []
    for pr in pr_downtime_entries:
        if pr["start_time"] and pr["end_time"]:
            pr_intervals.append((pr["start_time"], pr["end_time"]))
    
    for event in downtime_events:
        dt_event_start = datetime.datetime.strptime(event["start"], "%Y-%m-%d %H:%M")
        dt_event_end = datetime.datetime.strptime(event["end"], "%Y-%m-%d %H:%M")
        overlap_found = any(dt_event_start < pr_end and pr_start < dt_event_end for pr_start, pr_end in pr_intervals)
        if not overlap_found and event["minutes_down"] > 240:
            planned_downtime_minutes += event["minutes_down"]
    return planned_downtime_minutes


def calculate_unplanned_downtime(total_downtime_minutes, planned_downtime_minutes):
    """
    Calculates unplanned downtime as the difference between total downtime
    and planned downtime.
    """
    return total_downtime_minutes - planned_downtime_minutes




def compute_machine_oee(machine_data, queried_minutes):
    """
    Calculate Availability (A) and Performance (P) for a single machine.
    
    Assumptions:
      - Each machine's potential minutes equals the queried_minutes.
      - Planned downtime and unplanned downtime are provided in minutes.
    
    Formulas:
      PPT (Planned Production Time) = potential_minutes - planned_downtime
      Run Time = PPT - (unplanned_downtime)
      Ideal Cycle Time = PPT / target  (if target > 0)
      Availability = Run Time / PPT   (if PPT > 0)
      Performance = (Ideal Cycle Time * produced_parts) / Run Time   (if Run Time > 0)
    """
    produced = float(machine_data.get("produced_parts", 0))
    target = float(machine_data.get("target", 0))
    planned_downtime = float(machine_data.get("planned_downtime_minutes", 0))
    unplanned_downtime = float(machine_data.get("unplanned_downtime_minutes", 0))

    # produced = 500
    # target = 1000
    # planned_downtime = 0
    # unplanned_downtime = 3600
    
    # For each machine, potential minutes is simply the queried minutes.
    potential = queried_minutes
    ppt = potential - planned_downtime
    run_time = ppt - (unplanned_downtime)

    downtime_total = planned_downtime + unplanned_downtime

    if potential == 0 or downtime_total == 0:
        adjusted_target = target
    else:
        runtime = potential - unplanned_downtime - planned_downtime
        uptime_ratio = runtime /potential     
        adjusted_target = target * uptime_ratio
        # adjusted_target = target / ((unplanned_downtime + planned_downtime) / potential)

    ideal_cycle_time = ppt / target if target > 0 else 0.0
    availability = run_time / ppt if ppt > 0 else 0.0
    # performance = (ideal_cycle_time * produced) / run_time if run_time > 0 else 0.0
    if adjusted_target == 0:
        performance = 0
    else:
        performance = produced / adjusted_target
    
    return {"A": availability, "P": performance}


# --- Helper Color Gradient Functions ---

def get_color_for_ratio(ratio):
    """
    Maps a normalized ratio (0 to 1) to a color in a gradient, then applies a brightness factor:
      0   => dark red   (darker than full red #FF0000)
      0.5 => dark yellow
      1   => dark green
    The brightness factor scales down the computed RGB values.
    """
    if ratio <= 0.5:
        # Interpolate from red to yellow.
        factor = ratio / 0.5  # Normalized factor between 0 and 1.
        red = 255
        green = int(255 * factor)
    else:
        # Interpolate from yellow to green.
        factor = (ratio - 0.5) / 0.5  # Normalized factor between 0 and 1.
        red = int(255 * (1 - factor))
        green = 255
    blue = 0

    # Apply brightness factor to darken the color.
    brightness = 0.7  # Adjust this value between 0 and 1 for desired brightness.
    red = int(red * brightness)
    green = int(green * brightness)
    blue = int(blue * brightness)
    color_hex = '#{:02X}{:02X}{:02X}'.format(red, green, blue)
    return color_hex


def apply_color_gradient_to_line(machine_metrics, metric_key, color_key):
    """
    Applies a color gradient to machines in a single line based on their ranking,
    ensuring an even distribution of colors (red for worst, green for best).

    :param machine_metrics: Dict with machine IDs as keys and metric dictionaries as values.
    :param metric_key: The key for the metric (e.g., "P", "A", or "adjusted_downtime_percentage").
    :param color_key: The key to store the resulting color hex (e.g., "P_color", "A_color", or "downtime_percentage_color").
    """
    # Gather (machine_id, value) pairs for machines that have the metric.
    items = [(machine_id, data[metric_key]) for machine_id, data in machine_metrics.items() if data.get(metric_key) is not None]
    if not items:
        print(f"[apply_color_gradient_to_line] No values found for metric key: '{metric_key}'.")
        return

    # Sort the list by metric value (ascending).
    items.sort(key=lambda x: x[1])
    total = len(items)

    # Assign each machine a normalized ratio based on its rank.
    for rank, (machine_id, value) in enumerate(items):
        # Normalize rank from 0 to 1. If total is 1, default to 0.5.
        ratio = rank / (total - 1) if total > 1 else 0.5
        color_hex = get_color_for_ratio(ratio)
        machine_metrics[machine_id][color_key] = color_hex





# --- New Helper Function ---
def compute_machine_downtime_percentage(machine_data):
    """
    Calculate the downtime percentage for a given machine.
    
    The downtime percentage is computed as the ratio of downtime minutes to the total queried minutes,
    multiplied by 100 to yield a percentage value. If total queried minutes is zero, the percentage will be zero.
    
    Parameters:
      machine_data (dict): Dictionary containing machine performance data. Expected keys include:
                           - "downtime_minutes" (int): The machine's downtime in minutes.
                           - "total_queried_minutes" (int): The total minutes that were queried for the machine.
    
    Returns:
      dict: A dictionary with the key "downtime_percentage" and the computed percentage as its value.
    """
    total_minutes = machine_data.get("total_queried_minutes", 0)
    downtime_minutes = machine_data.get("downtime_minutes", 0)
    if total_minutes > 0:
        percentage = (downtime_minutes / total_minutes) * 100
    else:
        percentage = 0
    return {"downtime_percentage": percentage}




def calculate_operaton_P_and_A_from_totals(
        line_name, op_name, produced_parts, target, downtime_minutes,
        planned_downtime, unplanned_downtime, total_queried_minutes):
    """
    Calculate the Availability (A) and Performance (P) for an operation,
    using aggregated totals for all machines in the operation.
    
    Assumptions:
      - The operation's potential minutes equals the total queried minutes.
      - Downtime values are aggregated from all machines.
    
    Parameters:
      line_name (str): Identifier for the production line.
      op_name (str): The operation name or number.
      produced_parts (int or float): Total produced parts for the operation.
      target (int or float): Total target for the operation.
      downtime_minutes (int or float): Total downtime minutes (aggregated, not used directly).
      planned_downtime (int or float): Aggregated planned downtime minutes.
      unplanned_downtime (int or float): Aggregated unplanned downtime minutes.
      total_queried_minutes (int or float): Total potential minutes for the operation.
    
    Formulas:
      potential = total_queried_minutes
      Planned Production Time (PPT) = potential - planned_downtime
      Run Time = PPT - unplanned_downtime
      If potential > 0 and total downtime > 0, then:
          uptime_ratio = (potential - (planned_downtime + unplanned_downtime)) / potential
          adjusted_target = target * uptime_ratio
      Else:
          adjusted_target = target
      Availability (A) = Run Time / PPT    (if PPT > 0)
      Performance (P) = produced_parts / adjusted_target    (if adjusted_target > 0)
    
    Returns:
      dict: A dictionary with the following keys:
            "line": line_name,
            "op": op_name,
            "A": calculated Availability,
            "P": calculated Performance
    """
    potential = total_queried_minutes
    ppt = potential - planned_downtime
    run_time = ppt - unplanned_downtime
    downtime_total = planned_downtime + unplanned_downtime

    if potential == 0 or downtime_total == 0:
        adjusted_target = target
    else:
        runtime = potential - downtime_total
        uptime_ratio = runtime / potential
        adjusted_target = target * uptime_ratio

    availability = run_time / ppt if ppt > 0 else 0.0
    if adjusted_target == 0:
        performance = 0
    else:
        performance = produced_parts / adjusted_target

    return {
        "line": line_name,
        "op": op_name,
        "A": availability,
        "P": performance
    }



# --- Main Function ---
def fetch_combined_oee_production_data(request):
    """
    A unified view that always excludes weekends from the production data...
    """
    from django.http import JsonResponse
    import datetime, os, importlib
    from datetime import timedelta

    # Get date range from GET parameters.
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    if not start_date_str or not end_date_str:
        return JsonResponse({"error": "start_date and end_date must be provided in GET parameters."})
    
    try:
        start_date_obj = datetime.datetime.strptime(start_date_str, "%Y-%m-%d %H:%M")
    except ValueError:
        start_date_obj = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
    previous_day_str = (start_date_obj.date() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Set up the database connection.
    settings_path = os.path.join(os.path.dirname(__file__), '../pms/settings.py')
    spec = importlib.util.spec_from_file_location("settings", settings_path)
    settings = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(settings)
    get_db_connection = settings.get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()

    # Initialize accumulators and data structures.
    production_data = {}   # { line_name: { machine_number: { ... } } }
    downtime_totals_by_line = {}
    planned_downtime_totals_by_line = {}
    unplanned_downtime_totals_by_line = {}
    totals_by_line = {}
    scrap_totals_by_line = {}
    potential_minutes_by_line = {}

    overall_total_produced = 0
    overall_total_target = 0
    overall_planned_downtime_minutes = 0
    overall_unplanned_downtime_minutes = 0
    overall_downtime_seconds = 0
    overall_scrap_total = 0
    overall_total_potential_minutes = 0

    # A new data structure to store per-operation metrics.
    # You can choose a list of dicts or a dict keyed by line. Here we use a list.
    operation_oee_metrics = []

    global lines
    for line in lines:
        line_name = line["line"]
        production_data.setdefault(line_name, {})
        downtime_totals_by_line.setdefault(line_name, 0)
        planned_downtime_totals_by_line.setdefault(line_name, 0)
        unplanned_downtime_totals_by_line.setdefault(line_name, 0)
        totals_by_line.setdefault(line_name, {"total_produced": 0, "total_target": 0})
        scrap_totals_by_line.setdefault(line_name, 0)
        potential_minutes_by_line.setdefault(line_name, 0)

    # Always exclude weekends: split the date range into valid intervals.
    intervals = stip_weekends(start_date_str, end_date_str)
    if not intervals:
        cursor.close()
        conn.close()
        return JsonResponse({"error": "No valid time blocks remain after excluding weekends."})
    
    # Loop through each non-weekend interval.
    for block_start, block_end in intervals:
        block_queried_minutes = int((block_end - block_start).total_seconds() / 60)
        block_start_timestamp = int(block_start.timestamp())
        block_end_timestamp = int(block_end.timestamp())
        
        # Update potential minutes per line.
        for line in lines:
            line_name = line["line"]
            machine_count = sum(len(op.get("machines", [])) for op in line.get("operations", []))
            potential_minutes_by_line[line_name] += machine_count * block_queried_minutes

        # Process production and downtime per machine for this interval.
        for line in lines:
            line_name = line["line"]

            # Initialize line-level accumulators.
            line_total_parts = 0
            line_total_target = 0
            line_total_downtime_minutes = 0
            line_total_planned_downtime = 0
            line_total_unplanned_downtime = 0
            line_total_queried_minutes = 0

            # Loop through each operation on the current line.
            for operation in line.get("operations", []):
                op_name = operation["op"]

                # Initialize operation-level accumulators.
                op_total_parts = 0
                op_total_target = 0
                op_total_downtime_minutes = 0
                op_total_planned_downtime = 0
                op_total_unplanned_downtime = 0
                op_total_queried_minutes = 0

                # Process each machine within the operation.
                for machine in operation.get("machines", []):
                    machine_number = machine["number"]

                    # Initialize machine data if not already present.
                    machine_data = production_data[line_name].setdefault(
                        machine_number, {
                            "produced_parts": 0,
                            "target": 0,
                            "downtime_seconds": 0,
                            "downtime_minutes": 0,
                            "pr_downtime_entries": [],
                            "downtime_events": [],
                            "planned_downtime_minutes": 0,
                            "unplanned_downtime_minutes": 0,
                            "total_queried_minutes": 0,
                        }
                    )

                    # Increment total queried minutes.
                    machine_data["total_queried_minutes"] += block_queried_minutes
                    op_total_queried_minutes += block_queried_minutes
                    line_total_queried_minutes += block_queried_minutes

                    # Fetch production data.
                    prod_data = get_production_data_for_machine(
                        cursor, machine, machine_number,
                        block_start_timestamp, block_end_timestamp,
                        op_name, block_queried_minutes, line_name
                    )
                    produced = prod_data.get("produced_parts", 0)
                    target = prod_data.get("target", 0)

                    # Update machine's production values.
                    machine_data["produced_parts"] += produced
                    machine_data["target"] += target

                    # Accumulate production data for operation and line.
                    op_total_parts += produced
                    op_total_target += target
                    line_total_parts += produced
                    line_total_target += target

                    # Calculate downtime events.
                    downtime_seconds, downtime_events = calculate_downtime_events(
                        cursor, machine_number, block_start_timestamp, block_end_timestamp
                    )
                    downtime_minutes = int(downtime_seconds / 60)
                    machine_data["downtime_seconds"] += downtime_seconds
                    machine_data["downtime_minutes"] += downtime_minutes
                    op_total_downtime_minutes += downtime_minutes
                    line_total_downtime_minutes += downtime_minutes

                    downtime_totals_by_line[line_name] += downtime_seconds

                    # Retrieve PR downtime entries.
                    pr_entries = get_pr_downtime_entries(machine_number, block_start, block_end)
                    machine_data["pr_downtime_entries"].extend(pr_entries)

                    # Annotate downtime events with overlap info.
                    for event in downtime_events:
                        try:
                            detail_start = datetime.datetime.strptime(event["start"], "%Y-%m-%d %H:%M")
                            detail_end = datetime.datetime.strptime(event["end"], "%Y-%m-%d %H:%M")
                            overlap_info = compute_overlap_label(detail_start, detail_end, pr_entries)
                            event["overlap"] = overlap_info["overlap"]
                            event["pr_id"] = overlap_info["pr_id"]
                        except Exception as e:
                            print(f"Error annotating downtime event {event}: {e}")
                    machine_data["downtime_events"].extend(downtime_events)

                    # Calculate planned downtime.
                    planned = calculate_planned_downtime(downtime_events, pr_entries)
                    machine_data["planned_downtime_minutes"] += planned
                    op_total_planned_downtime += planned
                    line_total_planned_downtime += planned

                    # Calculate unplanned downtime.
                    total_downtime = downtime_minutes
                    unplanned = calculate_unplanned_downtime(total_downtime, planned)
                    machine_data["unplanned_downtime_minutes"] += unplanned
                    op_total_unplanned_downtime += unplanned
                    line_total_unplanned_downtime += unplanned

                    # Update overall downtime accumulators.
                    planned_downtime_totals_by_line[line_name] += planned
                    unplanned_downtime_totals_by_line[line_name] += unplanned
                    overall_planned_downtime_minutes += planned
                    overall_unplanned_downtime_minutes += unplanned

                # After processing all machines for the current operation, compute its OEE factors.
                results = calculate_operaton_P_and_A_from_totals(
                    line_name=line_name,
                    op_name=op_name,
                    produced_parts=op_total_parts,
                    target=op_total_target,
                    downtime_minutes=op_total_downtime_minutes,
                    planned_downtime=op_total_planned_downtime,
                    unplanned_downtime=op_total_unplanned_downtime,
                    total_queried_minutes=op_total_queried_minutes
                )
                # (Optional) Augment the result with additional details if desired.
                results.update({
                    "produced_parts": op_total_parts,
                    "target": op_total_target,
                    "downtime_minutes": op_total_downtime_minutes,
                    "planned_downtime_minutes": op_total_planned_downtime,
                    "unplanned_downtime_minutes": op_total_unplanned_downtime,
                    "total_queried_minutes": op_total_queried_minutes,
                })
                # Append the operation metrics to our list.
                operation_oee_metrics.append(results)

            # (Optional) You might also want to update line-level totals here.
            # For example, update totals_by_line or similar structures.
        
        # Fetch and accumulate scrap data for the interval.
        scrap_by_line, scrap_total = fetch_daily_scrap_data(cursor, block_start, block_end)
        for line_name, scrap_val in scrap_by_line.items():
            scrap_totals_by_line[line_name] += scrap_val
        overall_scrap_total += scrap_total

    # Aggregate production totals per line.
    for line_name, machines in production_data.items():
        for machine_number, machine_data in machines.items():
            totals_by_line[line_name]["total_produced"] += machine_data.get("produced_parts", 0)
            totals_by_line[line_name]["total_target"] += machine_data.get("target", 0)
            overall_total_produced += machine_data.get("produced_parts", 0)
            overall_total_target += machine_data.get("target", 0)

    overall_downtime_minutes = int(overall_downtime_seconds + sum(downtime_totals_by_line.values()) / 60)
    overall_total_potential_minutes = sum(potential_minutes_by_line.values())

    # Compute machine-level OEE metrics for each machine.
    for line_name, machines in production_data.items():
        for machine_number, machine_data in machines.items():
            machine_metrics = compute_machine_oee(
                machine_data,
                machine_data.get("total_queried_minutes", 0)
            )
            machine_data.update(machine_metrics)
    
    # Compute machine downtime percentage for each machine.
    for line_name, machines in production_data.items():
        for machine_number, machine_data in machines.items():
            downtime_metrics = compute_machine_downtime_percentage(machine_data)
            machine_data.update(downtime_metrics)
            machine_data["adjusted_downtime_percentage"] = 100 - machine_data.get("downtime_percentage", 0)

    # Apply color gradients.
    for line_name, machines in production_data.items():
        apply_color_gradient_to_line(machines, "P", "P_color")
        apply_color_gradient_to_line(machines, "A", "A_color")
        apply_color_gradient_to_line(machines, "adjusted_downtime_percentage", "downtime_percentage_color")

    # Compute the overall OEE metrics.
    oee_metrics = compute_oee_metrics(
        totals_by_line,
        overall_total_produced,
        overall_total_target,
        overall_total_potential_minutes,
        overall_unplanned_downtime_minutes,
        overall_planned_downtime_minutes,
        overall_scrap_total,
        scrap_totals_by_line,
        potential_minutes_by_line,
        planned_downtime_totals_by_line,
        unplanned_downtime_totals_by_line
    )

    # Build the response payload, including our new operation-level OEE metrics.
    response_data = {
        "production_data": production_data,
        "totals_by_line": totals_by_line,
        "overall_totals": {
            "total_produced": overall_total_produced,
            "total_target": overall_total_target,
        },
        "downtime_totals_by_line": downtime_totals_by_line,
        "overall_downtime": {
            "downtime_minutes": overall_downtime_minutes,
            "planned_downtime_minutes": overall_planned_downtime_minutes,
            "unplanned_downtime_minutes": overall_unplanned_downtime_minutes,
        },
        "potential_minutes_by_line": potential_minutes_by_line,
        "overall_potential_minutes": overall_total_potential_minutes,
        "scrap_totals_by_line": scrap_totals_by_line,
        "overall_scrap_total": overall_scrap_total,
        "previous_day": previous_day_str,
        "planned_downtime_totals_by_line": planned_downtime_totals_by_line,
        "unplanned_downtime_totals_by_line": unplanned_downtime_totals_by_line,
        "oee_metrics": oee_metrics,
        "operation_oee_metrics": operation_oee_metrics,  # <---- New key for op-level metrics.
    }
    cursor.close()
    conn.close()
    return JsonResponse(response_data)