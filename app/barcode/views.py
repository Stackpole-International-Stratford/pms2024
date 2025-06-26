from loguru import logger as loguru_logger
import re
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import BarcodeScanForm, BatchBarcodeScanForm, UnlockCodeForm
from barcode.models import LaserMark, LaserMarkDuplicateScan, BarCodePUN
import time
from .email_config import generate_and_send_code
import random
import logging
import datetime
import json
from django.urls import reverse
import humanize
from django.utils.timezone import localtime, make_aware, is_naive
import requests
from .models import DuplicateBarcodeEvent
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now as timezone_now
import loguru
from datetime import timedelta, datetime
from django.http import JsonResponse
from .models import LaserMark, LaserMarkDuplicateScan
import MySQLdb
from django.http import Http404
from django.db import connections






# Configure loguru to log to a file
loguru_logger.remove()  # Remove any existing handlers
loguru_logger.add("app/logs/duplicate_barcode_logs/duplicate_barcodes.log", level="INFO")

# Standard logging for other views
logger = logging.getLogger(__name__)


def sub_index(request):
    return redirect('barcode:barcode_index') 


def barcode_index_view(request):
    context = {}
    context["main_heading"] = "Barcode Index"
    context["title"] = "Barcode Index - pmsdata12"
    return render(request, f'barcode/index_barcode.html', context)


"""
Duplicate Scanning:
This code provides a check that barcodes are valid for the current part number and that the barcode has not been 
scanned previously.  
Parts are scanned as they are packed.  The scan is automatically submitted by pressing enter.  The scanner 
automatically adds Enter to the end of the scanned barcode.  
The scan is verified to contain the correct data for the part type and that all variable sections contain sane data.  
If any of the data is no good, an error screen is displayed to the operator.  
The the time and date of each scan is saved in the database.  If the same barcode is scanned a second time an error 
screen is displayed to the operator.  
If the barcode is valid, the screen refreshes so the operator can enter the next code.  A running count is 
maintained.  The running count resets automatically if the operator changes the part type and scans the next part. 
The running count can be set to any value using the Set Counter button.  Pressing the Set Counter button without
entering a new value sets the counter to zero.  

# - TODO: *SIGNAL* Create duplicate scan signal so it can be reacted to possible email notification etc
"""

# Does not return processed barcode

def verify_barcode(part_id, barcode):
    """Verify a barcode against a part’s PUN regex, record it, and detect duplicates.

    This will:
    1. Look up the BarCodePUN record to get the expected regex (PUN) and part_number.
    2. Check the barcode string against that regex, marking it "malformed" if it fails.
    3. Get or create a LaserMark record for this barcode, marking "created" on first insert.
    4. Check the LaserMark’s grade—if not A, B or C, mark "failed_grade".
    5. Get or create a LaserMarkDuplicateScan; if it already exists, mark "duplicate" and
       return the original scan timestamp.

    Args:
        part_id (int): Primary key of the BarCodePUN entry to fetch the expected regex.
        barcode (str): The barcode value to verify and record.

    Returns:
        dict: {
            'barcode': str,         # the original barcode string
            'part_number': str,     # from the BarCodePUN record
            'PUN': str,             # the regex pattern used
            'grade': str,           # the grade on the LaserMark record ('' if new)
            'status': str,          # one of 'malformed', 'created', 'failed_grade', 'duplicate'
            'scanned_at': datetime, # only present when status == 'duplicate'
        }

    Raises:
        BarCodePUN.DoesNotExist: if no BarCodePUN with the given id exists.
    """
    current_part_PUN = BarCodePUN.objects.get(id=part_id)
    barcode_result = {
        'barcode': barcode,
        'part_number': current_part_PUN.part_number,
        'PUN': current_part_PUN.regex,
        'grade': '',
        'status': '',
    }

    # check against the PUN
    if not re.search(current_part_PUN.regex, barcode):
        barcode_result['status'] = 'malformed'

    # set lm to None to prevent error
    lm = None
    # does barcode exist?
    lm, created = LaserMark.objects.get_or_create(bar_code=barcode)
    if created:
        # laser mark does not exist in db.  Need to create it.
        lm.part_number = current_part_PUN.part_number
        lm.save()
        barcode_result['status'] = 'created'

    # verify the barcode has a passing grade on file?
    if lm.grade not in ('A', 'B', 'C'):
        barcode_result['status'] = 'failed_grade'

    # has barcode been duplicate scanned?
    dup_scan, created = LaserMarkDuplicateScan.objects.get_or_create(
        laser_mark=lm)
    if not created:
        barcode_result['scanned_at'] = dup_scan.scanned_at
        barcode_result['status'] = 'duplicate'

    else:
        # barcode has not been scanned previously
        dup_scan.save()

    barcode_result['grade'] = lm.grade

    print(f'{current_part_PUN.part_number}:{barcode}')
    return barcode_result


def send_email_to_flask(code, barcode, scan_time):
    """Send scan data to the Flask email service without blocking.

    Posts a JSON payload containing the scan code, barcode value, and scan
    timestamp to an external Flask microservice. Uses a very short timeout
    so the Django view returns immediately; any request errors (including
    timeouts) are caught and logged to stdout.

    Args:
        code (str): Identifier or status code to send to the email service.
        barcode (str): The scanned barcode string.
        scan_time (str): Timestamp of the scan, pre-formatted as a string.

    Returns:
        JsonResponse: Always returns `{'status': 'Email task sent to Flask service'}`.

    """
    # url = 'http://localhost:5002/send-email' 
    url = 'http://10.4.1.234:5001/send-email' 
    
    payload = {
        'code': code,
        'barcode': barcode,
        'scan_time': scan_time  # Already formatted string
    }
    headers = {'Content-Type': 'application/json'}
    
    try:
        # Set a very short timeout to not wait for a response
        requests.post(url, json=payload, headers=headers, timeout=0.001)
    except requests.exceptions.RequestException as e:
        # This will catch the timeout error
        print(f"Request sent to Flask: {e}")

    # Return immediately
    return JsonResponse({'status': 'Email task sent to Flask service'})



def generate_unlock_code():
    """
    Generates a random 3-digit unlock code.
    """
    return '{:03d}'.format(random.randint(0, 999))


def generate_and_send_code(barcode, scan_time, part_number):
    """Generate an unlock code, notify via email, and log a duplicate‐barcode event.

    This function will:
    1. Generate a one‐time unlock code using `generate_unlock_code()`.
    2. Normalize `scan_time` (if given as an ISO‐8601 string) into a `datetime` and subtract 
       4 hours to adjust for timezone.
    3. Format the adjusted scan time as `YYYY-MM-DD HH:MM:SS` and send it, along with the 
       unlock code and barcode, to the Flask email service via `send_email_to_flask()`.  
       Any `'error'` key in the response will be printed to stdout.
    4. Compute `event_time` as “now minus 4 hours” and create a `DuplicateBarcodeEvent` record
       in the database, storing `barcode`, `part_number`, `scan_time`, `unlock_code`, and 
       `event_time`.
    5. Return the generated unlock code.

    Args:
        barcode (str): The scanned barcode string.
        scan_time (datetime.datetime or str): The original scan timestamp, or an
            ISO-8601 string (`'%Y-%m-%dT%H:%M:%S.%f%z'`).
        part_number (str): The part number to associate with the barcode event.

    Returns:
        str: The newly generated unlock code.

    Raises:
        ValueError: If `scan_time` is a string that does not match the expected
            `'%Y-%m-%dT%H:%M:%S.%f%z'` format.
    """
    code = generate_unlock_code()
    
    # Convert scan_time to datetime object if it's in string format
    if isinstance(scan_time, str):
        scan_time = datetime.strptime(scan_time, '%Y-%m-%dT%H:%M:%S.%f%z')
    
    # Subtract 4 hours from the scan time
    adjusted_scan_time = scan_time - timedelta(hours=4)
    
    # Format the scan time to the desired string format
    formatted_scan_time = adjusted_scan_time.strftime('%Y-%m-%d %H:%M:%S')
    
    response = send_email_to_flask(code, barcode, formatted_scan_time)
    if 'error' in response:
        print(f"Error sending email: {response['error']}")

    
    # Subtract 4 hours from the current time for event_time if needed
    event_time = timezone_now() - timedelta(hours=4)


    # Log the event to the database
    DuplicateBarcodeEvent.objects.create(
        barcode=barcode,
        part_number=part_number,
        scan_time=adjusted_scan_time,
        unlock_code=code,
        event_time=event_time
    )
    
    return code




def duplicate_scan(request):
    """Render and process the duplicate‐scan workflow for barcodes.

    This view handles both GET and POST requests to scan barcodes, validate them
    against a part’s PUN regex, check grades, detect duplicates, and route the
    user accordingly:

    - **GET**:  
      Displays an empty scan form.

    - **POST** with **'switch-mode'**:  
      Preserves the current part selection and redirects to the duplicate-scan-check view.

    - **POST** with **'set_count'**:  
      Resets the running count to the submitted value and redisplays the scan form.

    - **POST** with **'btnsubmit'**:  
      1. Validates the barcode against `BarCodePUN.regex`; if malformed, renders  
         `'barcode/malformed.html'`.  
      2. Gets/creates a `LaserMark`; if `grade` not in `('A','B','C')`, renders  
         `'barcode/failed_grade.html'`.  
      3. Gets/creates a `LaserMarkDuplicateScan`:  
         - If **already exists**, calls `generate_and_send_code()`, stores the  
           unlock code and duplicate info in `request.session`, logs the event,  
           and redirects to `'barcode:duplicate-found'`.  
         - If **new**, saves the scan, increments the running count, and shows  
           a success message.

    After processing, updates `request.session['RunningCount']`, builds the context
    (form, running_count, title, active_part, part_select_options, timer), and
    returns `render(request, 'barcode/dup_scan.html', context)`.

    Args:
        request (HttpRequest): The incoming HTTP request with session data and POST/GET parameters.

    Returns:
        HttpResponse: Either a redirect to another view or a rendered template response.
    """
    context = {}
    tic = time.time()
    running_count = int(request.session.get('RunningCount', '0'))
    last_part_id = request.session.get('LastPartID', '0')
    current_part_id = last_part_id
    select_part_options = BarCodePUN.objects.filter(active=True).order_by('name').values()

    if request.method == 'GET':
        form = BarcodeScanForm()

    if request.method == 'POST':
        if 'switch-mode' in request.POST:
            context['active_part'] = current_part_id
            return redirect('barcode:duplicate-scan-check')

        if 'set_count' in request.POST:
            messages.add_message(request, messages.INFO, 'Count reset.')
            running_count = request.POST.get('count', 0) or 0
            running_count = int(running_count)
            form = BarcodeScanForm()

        elif 'btnsubmit' in request.POST:
            form = BarcodeScanForm(request.POST)

            if form.is_valid():
                barcode = form.cleaned_data.get('barcode')
                current_part_id = int(request.POST.get('part_select', '0'))
                current_part_PUN = BarCodePUN.objects.get(id=current_part_id)

                if not re.search(current_part_PUN.regex, barcode):
                    context['scanned_barcode'] = barcode
                    context['part_number'] = current_part_PUN.part_number
                    context['expected_format'] = current_part_PUN.regex
                    return render(request, 'barcode/malformed.html', context=context)

                lm, created = LaserMark.objects.get_or_create(bar_code=barcode)
                if created:
                    lm.part_number = current_part_PUN.part_number
                    lm.save()

                if lm.grade not in ('A', 'B', 'C'):
                    context['scanned_barcode'] = barcode
                    context['part_number'] = lm.part_number
                    context['grade'] = lm.grade
                    return render(request, 'barcode/failed_grade.html', context=context)

                dup_scan, created = LaserMarkDuplicateScan.objects.get_or_create(laser_mark=lm)
                if not created:
                    scan_time = dup_scan.scanned_at  # Use the original scan time
                    unlock_code = generate_and_send_code(barcode, scan_time, lm.part_number)
                    request.session['unlock_code'] = unlock_code
                    request.session['duplicate_found'] = True
                    request.session['unlock_code_submitted'] = False
                    request.session['duplicate_barcode'] = barcode
                    request.session['duplicate_part_number'] = lm.part_number
                    request.session['duplicate_scan_at'] = scan_time.strftime('%Y-%m-%d %H:%M:%S')

                    loguru.logger.info(f"Duplicate found: True, Barcode: {barcode}, Part Number: {lm.part_number}, Time of original scan: {scan_time}")


                    return redirect('barcode:duplicate-found')
                else:
                    dup_scan.save()
                    messages.add_message(request, messages.SUCCESS, 'Valid Barcode Scanned')
                    running_count += 1
                    request.session['LastPartID'] = current_part_id
                    form = BarcodeScanForm()
        else:
            current_part_id = int(request.POST.get('part_select', '0'))
            running_count = 0
            form = BarcodeScanForm()

    toc = time.time()
    request.session['RunningCount'] = running_count
    context['form'] = form
    context['running_count'] = running_count
    context['title'] = 'Duplicate Scan'
    context['scan_check'] = False
    context['active_part'] = current_part_id
    context['part_select_options'] = select_part_options
    context['timer'] = f'{toc-tic:.3f}'

    return render(request, 'barcode/dup_scan.html', context=context)


def duplicate_found_view(request):
    """Process the unlock‐code submission after a duplicate scan is detected.

    Handles both GET and POST requests for the “duplicate found” page:

    - **GET**:  
      Renders a blank `UnlockCodeForm` asking the user to enter their unlock code, employee ID, and a reason.

    - **POST**:  
      1. Validates the submitted `UnlockCodeForm`.  
      2. Compares the submitted `unlock_code` against `request.session['unlock_code']`.  
      3. Parses `request.session['duplicate_scan_at']` (format `%Y-%m-%d %H:%M:%S`), subtracts 4 hours, and uses that to locate the existing `DuplicateBarcodeEvent`.  
      4. If the code matches, updates that event with `employee_id` and `user_reason`, clears the duplicate‐found flag, and redirects to the duplicate-scan page.  
      5. If the code is incorrect or the timestamp is malformed, adds an error message and re-renders the form.

    Args:
        request (HttpRequest): The incoming request, which must include in `.session`:
            - `'unlock_code'`: The expected unlock code to verify.
            - `'duplicate_scan_at'`: Original scan timestamp as a string (`'%Y-%m-%d %H:%M:%S'`).
            - `'duplicate_barcode'`: The barcode string that was duplicated.
            - `'duplicate_part_number'`: The part number associated with that barcode.

    Returns:
        HttpResponse:  
        - On successful verification: a redirect (`HttpResponseRedirect`) to the `'barcode:duplicate-scan'` view.  
        - Otherwise: a rendered `'barcode/dup_found.html'` with context:
          `{ 'scanned_barcode', 'part_number', 'duplicate_scan_at', 'unlock_code', 'form' }`.

    Raises:
        ValueError: If `'duplicate_scan_at'` is missing or not in the expected datetime format.
    """
    if request.method == 'POST':
        form = UnlockCodeForm(request.POST)

        if form.is_valid():
            submitted_code = form.cleaned_data['unlock_code']
            employee_id = form.cleaned_data['employee_id']
            reason = form.cleaned_data['reason']
            other_reason = form.cleaned_data['other_reason']
            user_reason = other_reason if reason == 'other' else dict(form.REASON_CHOICES).get(reason)

            if submitted_code == request.session.get('unlock_code'):
                request.session['unlock_code_submitted'] = True
                request.session['duplicate_found'] = False

                # Convert the scan_time back to a datetime object
                scan_time_str = request.session.get('duplicate_scan_at')
                scan_time = datetime.strptime(scan_time_str, '%Y-%m-%d %H:%M:%S')

                # Adjust the scan_time by subtracting 4 hours
                scan_time = scan_time - timedelta(hours=4)

                if scan_time:
                    # Log the event to the database with employee ID and user reason
                    event = DuplicateBarcodeEvent.objects.filter(
                        barcode=request.session['duplicate_barcode'],
                        unlock_code=request.session['unlock_code']
                    ).first()
                    event.employee_id = employee_id
                    event.user_reason = user_reason
                    event.save()

                    return redirect('barcode:duplicate-scan')
                else:
                    messages.error(request, 'Invalid scan time format. Please try again.')

    else:
        form = UnlockCodeForm()

    # Convert the scan_time back to a datetime object and adjust it
    scan_time_str = request.session.get('duplicate_scan_at', '')
    adjusted_scan_time_str = (datetime.strptime(scan_time_str, '%Y-%m-%d %H:%M:%S') - timedelta(hours=4)).strftime('%Y-%m-%d %H:%M:%S') if scan_time_str else ''

    context = {
        'scanned_barcode': request.session.get('duplicate_barcode', ''),
        'part_number': request.session.get('duplicate_part_number', ''),
        'duplicate_scan_at': adjusted_scan_time_str,
        'unlock_code': request.session.get('unlock_code'),
        'form': form,
    }

    return render(request, 'barcode/dup_found.html', context=context)




def send_new_unlock_code(request):
    """Generate and send a fresh unlock code for the current duplicate scan, then redirect.

    Retrieves the `duplicate_barcode`, `duplicate_scan_at`, and `duplicate_part_number`
    from the user’s session, calls `generate_and_send_code()` to issue a new code and
    notify the email service, and resets the session flags for the duplicate‐found flow.
    Logs the new code generation before redirecting back to the duplicate‐found page.

    Args:
        request (HttpRequest): The incoming request, expected to have in its `.session`:
            - `'duplicate_barcode'`: The barcode string previously identified as a duplicate.
            - `'duplicate_scan_at'`: The original scan timestamp string.
            - `'duplicate_part_number'`: The part number associated with that barcode.

    Returns:
        HttpResponseRedirect: A redirect to the `'barcode:duplicate-found'` view.
    """
    barcode = request.session.get('duplicate_barcode', '')
    scan_time = request.session.get('duplicate_scan_at', '')
    part_number = request.session.get('duplicate_part_number', '')
    unlock_code = generate_and_send_code(barcode, scan_time, part_number)
    request.session['unlock_code'] = unlock_code
    request.session['duplicate_found'] = True
    request.session['unlock_code_submitted'] = False

    humanized_time = humanize.naturaltime(localtime(timezone_now()))

    loguru.logger.info(f"New unlock code generated: {unlock_code}")

    return redirect('barcode:duplicate-found')



def duplicate_scan_batch(request):
    """Render and handle batch duplicate‐barcode scanning for multiple entries.

    On GET:
        Displays an empty `BatchBarcodeScanForm` for entering multiple barcodes.

    On POST:
        - Reads the raw `barcodes` textarea (newline‐separated).
        - Splits into individual barcode strings.
        - Verifies each against the part’s PUN via `verify_barcode()`.
        - Collects results into a `processed_barcodes` list (for future handling).
        - (Placeholder for per‐barcode rendering or result aggregation.)

    The view also:
        - Maintains `LastPartID` in `request.session` to remember the selected part.
        - Builds a context with:
          - `form`: the scan form instance.
          - `title`: “Batch Duplicate Scan”.
          - `active_part`: current part ID.
          - `part_select_options`: available `BarCodePUN` entries.
          - `active_part_prefix`: a slice of the regex for UI display.
          - `active_PUN`: the regex pattern stripped of named‐group syntax.
          - `parts_per_tray`: expected count from the PUN record.
          - `timer`: elapsed request‐processing time.

    Args:
        request (HttpRequest): Incoming request; uses `.session['LastPartID']`
            to persist the last‐selected part across requests.

    Returns:
        HttpResponse: Renders `'barcode/dup_scan_batch.html'` with the above context.
    """
    context = {}
    tic = time.time()
    # get data from session
    last_part_id = request.session.get('LastPartID', '0')
    current_part_id = last_part_id

    select_part_options = BarCodePUN.objects.filter(
        active=True).order_by('name').values()
    if current_part_id == '0':
        if select_part_options.first():
            current_part_id = select_part_options.first()['id']
    current_part_PUN = BarCodePUN.objects.get(id=current_part_id)

    if request.method == 'GET':
        # clear the form
        form = BatchBarcodeScanForm()

    if request.method == 'POST':
        barcodes = request.POST.get('barcodes')
        if len(barcodes):
            form = BatchBarcodeScanForm(request.POST)

            if form.is_valid():
                barcodes = form.cleaned_data.get('barcodes').split("\r\n")

                posted_part_id = int(request.POST.get('part_select', '0'))
                if posted_part_id:
                    current_part_id = posted_part_id
                processed_barcodes = []
                for barcode in barcodes:

                    # get or create a laser-mark for the scanned code
                    processed_barcodes.append(
                        verify_barcode(current_part_id, barcode))
                    print(f'{current_part_PUN.part_number}:{barcode}')
                    

                for barcode in processed_barcodes:

                    # # Malformed Barcode
                    # if barcode['status'] == 'malformed':
                    #     print('Malformed Barcode')
                    #     context['scanned_barcode'] = barcode
                    #     context['part_number'] = current_part_PUN.part_number
                    #     context['expected_format'] = current_part_PUN.regex
                    #     return render(request, 'barcode/malformed.html', context=context)

                    # verify the barcode has a passing grade on file?
                    # if barcode['status'] == 'failed_grade':
                    #     context['scanned_barcode'] = barcode
                    #     context['part_number'] = current_part_PUN.part_number
                    #     context['grade'] = barcode['grade']
                    #     return render(request, 'barcode/failed_grade.html', context=context)

                    # barcode has already been scanned
                    # if barcode['status'] == 'duplicate':
                    #     context['scanned_barcode'] = barcode['barcode']
                    #     context['part_number'] = barcode['part_number']
                    #     context['duplicate_scan_at'] = barcode['scanned_at']
                    #     return render(request, 'barcode/dup_found.html', context=context)
                    pass

        else:
            current_part_id = int(request.POST.get('part_select', '0'))
            if current_part_id == '0':
                if select_part_options.first():
                    current_part_id = select_part_options.first()['id']
            form = BatchBarcodeScanForm()

    context['form'] = form
    context['title'] = 'Batch Duplicate Scan'
    context['active_part'] = current_part_id
    context['part_select_options'] = select_part_options
    current_part_PUN = BarCodePUN.objects.get(id=current_part_id)
    context['active_part_prefix'] = current_part_PUN.regex[1:5]

    regex = current_part_PUN.regex
    while (regex.find('(?P') != -1):
        start = regex.find('(?P')
        end = regex.index('>',start)
        regex = regex[:start+1] + regex[end+1:]
    context['active_PUN'] = regex
    
    context['parts_per_tray'] = current_part_PUN.parts_per_tray

    request.session['LastPartID'] = current_part_id

    toc = time.time()
    context['timer'] = f'{toc-tic:.3f}'

    return render(request, 'barcode/dup_scan_batch.html', context=context)


def duplicate_scan_check(request):
    """Render and process a single‐scan duplicate check for barcodes.

    - **GET**:  
      Displays an empty `BarcodeScanForm` for scanning a barcode.

    - **POST** with **'switch-mode'**:  
      Preserves the current part selection and redirects back to the batch scan view.

    - **POST** with **'btnsubmit'**:  
      1. Validates the scanned barcode against the selected `BarCodePUN.regex`; if malformed, renders  
         `'barcode/malformed.html'`.  
      2. Gets or creates a `LaserMark`; if new, saves the part number, then creates a  
         `LaserMarkDuplicateScan` and immediately deletes it with an error message  
         (“Barcode Not Previously Scanned”).  
      3. If the duplicate‐scan record already exists, shows a success message  
         (“Previously Scanned at …”) and marks `scan_check=True` in context.

    After handling, stores `LastPart` in the session, builds a context with:
    `{ form, title, scan_check, active_part, part_select_options, timer }`,
    and renders `'barcode/dup_scan.html'`.

    Args:
        request (HttpRequest): The incoming request, using:
            - `request.session['LastPart']` to remember the selected part.
            - POST fields `'barcode'`, `'part_select'`, and action flags.

    Returns:
        HttpResponse: A redirect or the rendered duplicate‐scan template with context.
    """
    context = {}
    tic = time.time()

    current_part_id = request.session.get('LastPart', '0')

    select_part_options = BarCodePUN.objects.filter(
        active=True).order_by('name').values()

    if request.method == 'GET':
        # clear the form
        form = BarcodeScanForm()

    if request.method == 'POST':

        if 'switch-mode' in request.POST:
            context['active_part'] = current_part_id
            return redirect('barcode:duplicate-scan')

        if 'btnsubmit' in request.POST:

            form = BarcodeScanForm(request.POST)

            if form.is_valid():

                barcode = form.cleaned_data.get('barcode')

                current_part_id = int(request.POST.get('part_select', '0'))

                current_part_PUN = BarCodePUN.objects.get(id=current_part_id)

                if not re.search(current_part_PUN.regex, barcode):
                    # malformed barcode
                    context['scanned_barcode'] = barcode
                    context['part_number'] = current_part_PUN.part_number
                    context['expected_format'] = current_part_PUN.regex
                    return render(request, 'barcode/malformed.html', context=context)

                # does barcode exist?
                lm, created = LaserMark.objects.get_or_create(bar_code=barcode)
                if created:
                    # laser mark does not exist in db.  Need to create it.
                    lm.part_number = current_part_PUN.part_number
                    lm.save()

                # has barcode been duplicate scanned?
                dup_scan, created = LaserMarkDuplicateScan.objects.get_or_create(
                    laser_mark=lm)
                if created:
                    # barcode has not been scanned previously
                    messages.add_message(
                        request, messages.ERROR, 'Barcode Not Previously Scanned')
                    dup_scan.delete()
                    form = BarcodeScanForm()
                else:
                    # barcode has already been scanned
                    messages.add_message(
                        request, messages.SUCCESS, f'Barcode Previously Scanned at {dup_scan.scanned_at}')
                    context['status_last'] = 'good'
                    form = BarcodeScanForm()
        else:
            current_part_id = int(request.POST.get('part_select', '0'))
            form = BarcodeScanForm()

    toc = time.time()
    request.session['LastPart'] = current_part_id

    context['form'] = form
    context['title'] = 'Duplicate Scan Check'
    context['scan_check'] = True
    context['active_part'] = int(current_part_id)
    context['part_select_options'] = select_part_options
    context['timer'] = f'{toc-tic:.3f}'

    return render(request, 'barcode/dup_scan.html', context=context)



from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import random
from .models import LockoutEvent  # Import the LockoutEvent model

def lockout_view(request):
    """Manage a lockout event when invalid barcodes are scanned, notify supervisors, and handle unlock.

    This view supports two main workflows:
    
    1. **Initial lockout trigger** (POST with `lockout_trigger`):
       - Reads newline‐separated barcodes from the form.
       - Stores them in `request.session['lockout_barcodes']`.
       - Generates and stores a one‐time `unlock_code` in session.
       - Creates a `LockoutEvent` record (with `unlock_code` and location).
       - Marks `request.session['lockout_active'] = True` and resets `unlock_code_submitted` & `email_sent`.
    
    2. **Supervisor unlock submission** (POST without `lockout_trigger`):
       - Extracts `supervisor_id` and `unlock_code` from the form.
       - If the code matches the session’s `unlock_code`:
         - Sets `lockout_active = False`, `unlock_code_submitted = True`.
         - Updates the corresponding `LockoutEvent` with `supervisor_id`, `unlocked_at`, and `is_unlocked=True`.
         - Clears `lockout_barcodes` from session.
         - Adds a success message and redirects to the batch scan page.
       - If the code is incorrect:
         - Regenerates a new unlock code, updates the `LockoutEvent` and session.
         - Adds an error message.

    After either POST path, if no email has been sent (`session['email_sent']=False`):
    - Builds an HTML email with the scanned barcodes, affected stations, and unlock code.
    - Sends it to the configured address via `send_mail()`.
    - Sets `session['email_sent'] = True` to avoid duplicates.

    Finally, renders `'barcode/lockout.html'`, with session flags determining
    whether to show the lockout screen or the unlock form.

    Args:
        request (HttpRequest): Incoming HTTP request. Must have:
            - `session['lockout_barcodes']`: list of scanned barcode strings.
            - `session['unlock_code']`: current one‐time unlock code.
            - `session['lockout_event_id']`: ID of the `LockoutEvent`.
            - `session['lockout_active']`, `session['unlock_code_submitted']`, `session['email_sent']`.

    Returns:
        HttpResponse or HttpResponseRedirect:
        - A redirect to `'barcode:duplicate_scan_batch'` after successful unlock.
        - Otherwise, renders the lockout page (`barcode/lockout.html`).

    Side Effects:
        - Mutates `request.session` (stores codes, flags, barcodes).
        - Sends an email notification on the first render after a lockout.
        - Creates or updates `LockoutEvent` records in the database.
    """
    print("DEBUG: Entered lockout_view")  # Track entry into the view

    # Define locations for all stations where lockout could occur
    locations = ['10R80', '10R60', 'GFX']

    if request.method == 'POST':
        print("DEBUG: POST request received")  # Ensure we hit POST block

        if 'lockout_trigger' in request.POST:
            # This is the initial lockout trigger
            print("DEBUG: Initial lockout trigger received")
            # Get the barcodes from the form
            barcodes = request.POST.get('barcodes', '').split('\n')
            request.session['lockout_barcodes'] = barcodes
            # Generate unlock code
            request.session['unlock_code'] = generate_unlock_code()
            request.session['email_sent'] = False
            # Create LockoutEvent
            lockout_event = LockoutEvent.objects.create(
                unlock_code=request.session['unlock_code'],
                location='Batch Scanner',  # You can dynamically set this based on the actual station
            )
            request.session['lockout_event_id'] = lockout_event.id  # Store the event ID in session
            request.session['lockout_active'] = True
            request.session['unlock_code_submitted'] = False  # Reset this to False
            request.session.modified = True  # Force save session
            print(f"DEBUG: New lockout event, resetting email_sent to False and generating unlock code {request.session['unlock_code']}")
            # Proceed to render the lockout page
        else:
            # This is the supervisor unlock submission
            supervisor_id = request.POST.get('supervisor_id')
            unlock_code = request.POST.get('unlock_code')
            print(f"DEBUG: supervisor_id = {supervisor_id}, unlock_code = {unlock_code}")  # Output form values

            if supervisor_id and unlock_code:
                if unlock_code == request.session.get('unlock_code'):
                    print("DEBUG: Correct unlock code entered")  # Check correct unlock code

                    # Unlock the session by setting the appropriate session flag
                    request.session['lockout_active'] = False
                    request.session['unlock_code_submitted'] = True

                    # Update the LockoutEvent with supervisor_id and unlocked_at
                    lockout_event_id = request.session.get('lockout_event_id')
                    if lockout_event_id:
                        lockout_event = LockoutEvent.objects.get(id=lockout_event_id)
                        lockout_event.supervisor_id = supervisor_id
                        lockout_event.unlocked_at = timezone.now()
                        lockout_event.is_unlocked = True
                        lockout_event.save()

                    print(f"DEBUG: Set lockout_active = {request.session.get('lockout_active')}, unlock_code_submitted = {request.session.get('unlock_code_submitted')}")  # Check session values after unlock

                    # Mark the session as modified to force save
                    request.session.modified = True
                    print("DEBUG: Session modified after successful unlock")  # Confirm session modification

                    # Clear barcodes only after successful unlock, when we're done with the event.
                    if 'lockout_barcodes' in request.session:
                        del request.session['lockout_barcodes']
                        print("DEBUG: Cleared lockout_barcodes from session after successful unlock")

                    messages.success(request, 'Access granted! Returning to the batch scan page.')
                    return redirect('barcode:duplicate_scan_batch')
                else:
                    print("DEBUG: Incorrect unlock code entered")  # Indicate invalid unlock code

                    # Reset lockout and regenerate unlock code
                    request.session['email_sent'] = False
                    request.session['unlock_code'] = generate_unlock_code()  # Generate a new random unlock code

                    # Keep the lockout_barcodes in session
                    print(f"DEBUG: New unlock code generated: {request.session['unlock_code']}")

                    # Update LockoutEvent with new unlock code
                    lockout_event_id = request.session.get('lockout_event_id')
                    if lockout_event_id:
                        lockout_event = LockoutEvent.objects.get(id=lockout_event_id)
                        lockout_event.unlock_code = request.session['unlock_code']
                        lockout_event.save()

                    request.session.modified = True  # Force save session

                    messages.error(request, 'Incorrect unlock code. A new code has been sent.')
            else:
                # Missing supervisor_id or unlock_code
                print("DEBUG: Missing supervisor_id or unlock_code in POST")
                messages.error(request, 'Please enter both supervisor ID and unlock code.')
                # Proceed to render the lockout page with error message

    # Ensure the email gets sent if not already sent
    email_sent_flag = request.session.get('email_sent', False)
    if not email_sent_flag:
        print("DEBUG: Sending lockout email")  # Track request method

        # Get the unlock code from session
        unlock_code = request.session['unlock_code']

        # Get the barcodes from session (updated to handle new barcodes)
        barcodes = [barcode for barcode in request.session.get('lockout_barcodes', []) if barcode.strip()]  # Filter out empty barcodes

        # Email subject with unlock code
        email_subject = f"100% Inspection Hand-Scanner Lockout Notification - Unlock Code: {unlock_code}"

        # HTML email body with details
        email_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">

            <div style="background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);">
                <h2 style="color: #d9534f; font-size: 24px; text-align: center;">⚠️ Lockout Alert! ⚠️</h2>

                <p style="font-size: 16px; color: #333;">
                    One or more wrong parts were just scanned and submitted at one of the 100% inspection stations listed below, and immediate investigation is required:
                </p>

                <ul style="font-size: 16px; color: #333; list-style-type: none; padding-left: 0;">
                    <li style="padding: 5px 0;">🔹 {locations[0]}</li>
                    <li style="padding: 5px 0;">🔹 {locations[1]}</li>
                    <li style="padding: 5px 0;">🔹 {locations[2]}</li>
                </ul>

                <p style="font-size: 16px; color: #333;">
                    The following barcodes were scanned:
                </p>

                <ul style="font-size: 16px; color: #333;">
        """

        for barcode in barcodes:
            if barcode.startswith("INVALID:"):
                # Highlight invalid barcodes in red
                clean_barcode = barcode.replace("INVALID:", "")
                email_body += f"<li style='color: red;'>{clean_barcode}</li>"
            else:
                email_body += f"<li>{barcode}</li>"

        email_body += f"""
                </ul>

                <p style="font-size: 16px; color: #333;">
                    Please visit the station to investigate the issue and use the unlock code below to unlock the device:
                </p>

                <h3 style="font-size: 28px; text-align: center; font-weight: bold; padding: 10px 0;">
                    Unlock Code: <span style="font-size: 32px; color: #d9534f;">{unlock_code}</span>
                </h3>

                <p style="font-size: 16px; color: #333; text-align: center;">
                    <em>This code can be used to unlock the device.</em>
                </p>

                <p style="font-size: 14px; color: #777; text-align: center;">
                    <strong>Thank you</strong><br>
                </p>
            </div>

        </body>
        </html>
        """

        # Send the email
        try:
            send_mail(
                email_subject,  # Email subject with unlock code
                '',  # Plain-text version (will be empty since we're using HTML)
                settings.EMAIL_HOST_USER,  # From email
                ['tyler.careless@johnsonelectric.com'],  # To email
                html_message=email_body,  # HTML email content
                fail_silently=False,
            )
            print(f"DEBUG: Email successfully sent to tyler.careless@johnsonelectric.com with unlock code {unlock_code}")

            # Mark that the email has been sent to avoid duplicate emails
            request.session['email_sent'] = True
            request.session.modified = True
            print(f"DEBUG: Set email_sent flag = {request.session.get('email_sent')}")
        except Exception as e:
            print(f"DEBUG: Error occurred while sending email: {e}")

    print(f"DEBUG: Rendering lockout page. lockout_active = {request.session.get('lockout_active')}, unlock_code_submitted = {request.session.get('unlock_code_submitted')}")  # Show session state before rendering page

    return render(request, 'barcode/lockout.html')

# ===============================================
# ===============================================
# ============== Barcode Scan View ==============
# ===============================================
# ===============================================

from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import LaserMark, LaserMarkDuplicateScan
import MySQLdb
from datetime import timedelta
import time

# Scan view - step 1: Barcode input form
def barcode_scan_view(request):
    """Handle barcode lookups by exact or partial match and route to results.

    - **GET**:  
      Renders the empty scan form (`barcode/barcode_scan.html`).

    - **POST**:  
      1. Retrieves `barcode` from `request.POST`; if missing, re-renders the form with an error.  
      2. Queries `LaserMark` using `bar_code__icontains` to allow partial matches, ordered by creation time.  
      3. If multiple matches are found:
         - Builds `matching_barcodes_list` of dicts with `'barcode'` and formatted `'timestamp'`.  
         - Renders `barcode/barcode_matches.html` with this list.  
      4. If exactly one match is found:
         - Redirects to the `barcode:barcode-result` view for that code.  
      5. If no matches:
         - Re-renders the form with an error message.

    Args:
        request (HttpRequest): The incoming request, expecting optional `POST['barcode']`.

    Returns:
        HttpResponse: Either a rendered template (`barcode_scan.html` or `barcode_matches.html`)
                      or an `HttpResponseRedirect` to the single‐match results page.
    """
    if request.method == 'POST':
        barcode_input = request.POST.get('barcode', None)
        if not barcode_input:
            return render(request, 'barcode/barcode_scan.html', {'error': 'No barcode provided'})
        
        # Use LIKE to allow partial matches
        matching_barcodes = LaserMark.objects.filter(bar_code__icontains=barcode_input).order_by('created_at')

        # If multiple matches are found, redirect to the scan pick view
        if matching_barcodes.exists():
            if matching_barcodes.count() > 1:
                # Create list for the next step
                matching_barcodes_list = [
                    {
                        'barcode': barcode.bar_code,
                        'timestamp': barcode.created_at.strftime('%Y-%m-%d (%B %d) %I:%M:%S %p')
                    }
                    for barcode in matching_barcodes
                ]
                return render(request, 'barcode/barcode_matches.html', {'matching_barcodes': matching_barcodes_list})
            else:
                # If only one match, automatically go to results
                return redirect('barcode:barcode-result', barcode=matching_barcodes.first().bar_code)
        else:
            return render(request, 'barcode/barcode_scan.html', {'error': 'No matching barcodes found'})

    return render(request, 'barcode/barcode_scan.html')


# Scan pick view - step 2: Barcode match pick
def barcode_pick_view(request):
    if request.method == 'POST':
        barcode_input = request.POST.get('barcode')
        return redirect('barcode:barcode-result', barcode=barcode_input)

    return redirect('barcode:barcode-scan')


# Results view - step 3: Show barcode result and surrounding barcodes
from django.http import JsonResponse
from django.shortcuts import render
from datetime import timedelta
import MySQLdb
import time

def barcode_result_view(request, barcode):
    """Display detailed scan results for a barcode and support AJAX pagination.

    On a normal request, looks up the given `barcode` in the `LaserMark` table and:
    1. Retrieves its grade, asset, and creation timestamp.
    2. Checks for a duplicate scan and records its timestamp (adjusted for timezone).
    3. Fetches the 100 previous and next scans (by timestamp) for the same asset.
    4. Queries an external GP12 database for any scrap timestamp.
    5. Renders `'barcode/barcode_result.html'` with context:
       `{ barcode, grade, asset, lasermark_time, lasermark_duplicate_time,
         barcode_gp12_time, before_barcodes, after_barcodes }`.

    If the request is AJAX (`X-Requested-With: XMLHTTPRequest`), expects POST params:
    - `direction` (`'before'` or `'after'`)
    - `offset` (int)
    - `batch_size` (int)
    Returns a `JsonResponse` with either `before_barcodes` or `after_barcodes`, each
    a list of `{ 'barcode': str, 'timestamp': str }`.

    Args:
        request (HttpRequest): The incoming HTTP request.
        barcode (str): The barcode string to look up.

    Returns:
        HttpResponse or JsonResponse:
        - **HttpResponse**: on standard loads, renders the result template.
        - **JsonResponse**: on AJAX calls, returns paginated scan data.

    Raises:
        None: Missing barcodes on AJAX yield a 404 JSON error; missing barcodes on
        standard loads render the scan form with an error message.
    """
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        # Handle AJAX request for loading more barcodes (before or after)
        direction = request.POST.get('direction')
        offset = int(request.POST.get('offset', 0))
        batch_size = int(request.POST.get('batch_size', 100))

        try:
            lasermark = LaserMark.objects.get(bar_code=barcode)
        except LaserMark.DoesNotExist:
            return JsonResponse({'error': f'Barcode {barcode} not found'}, status=404)

        if direction == 'before':
            before_barcodes_qs = LaserMark.objects.filter(
                created_at__lt=lasermark.created_at,
                asset=lasermark.asset
            ).order_by('-created_at')

            before_barcodes = before_barcodes_qs[offset:offset + batch_size]
            adjusted_before_barcodes = [
                {'barcode': b.bar_code, 'timestamp': b.created_at.strftime('%Y-%m-%d (%B %d) %I:%M:%S %p')}
                for b in before_barcodes
            ]
            return JsonResponse({'before_barcodes': adjusted_before_barcodes})

        elif direction == 'after':
            after_barcodes_qs = LaserMark.objects.filter(
                created_at__gt=lasermark.created_at,
                asset=lasermark.asset
            ).order_by('created_at')

            after_barcodes = after_barcodes_qs[offset:offset + batch_size]
            adjusted_after_barcodes = [
                {'barcode': a.bar_code, 'timestamp': a.created_at.strftime('%Y-%m-%d (%B %d) %I:%M:%S %p')}
                for a in after_barcodes
            ]
            return JsonResponse({'after_barcodes': adjusted_after_barcodes})

    try:
        # Initial page load: Load 100 barcodes before and after
        lasermark = LaserMark.objects.get(bar_code=barcode)
        lasermark_time = lasermark.created_at.strftime('%Y-%m-%d (%B %d) %I:%M:%S %p')

        # Fetch grade and asset from LaserMark
        grade = lasermark.grade or 'N/A'  # Handle null values with 'N/A'
        asset = lasermark.asset or 'N/A'  # Handle null values with 'N/A'

        # Check for duplicate scan
        try:
            lasermark_duplicate = LaserMarkDuplicateScan.objects.get(laser_mark=lasermark)
            lasermark_duplicate_time = (lasermark_duplicate.scanned_at - timedelta(hours=4)).strftime('%Y-%m-%d (%B %d) %I:%M:%S %p')
        except LaserMarkDuplicateScan.DoesNotExist:
            lasermark_duplicate_time = 'Not found in LaserMarkDuplicateScan'

        # Load initial 100 barcodes before and after
        before_barcodes = LaserMark.objects.filter(
            created_at__lt=lasermark.created_at, 
            asset=lasermark.asset
        ).order_by('-created_at')[:100]

        after_barcodes = LaserMark.objects.filter(
            created_at__gt=lasermark.created_at, 
            asset=lasermark.asset
        ).order_by('created_at')[:100]

        # Format barcodes for display
        adjusted_before_barcodes = [
            {'barcode': b.bar_code, 'timestamp': b.created_at.strftime('%Y-%m-%d (%B %d) %I:%M:%S %p')}
            for b in before_barcodes
        ]
        adjusted_after_barcodes = [
            {'barcode': a.bar_code, 'timestamp': a.created_at.strftime('%Y-%m-%d (%B %d) %I:%M:%S %p')}
            for a in after_barcodes
        ]

        # Query external GP12 database
        barcode_gp12_time = None
        try:
            db = MySQLdb.connect(host="10.4.1.224", user="stuser", passwd="stp383", db="prodrptdb")
            cursor = db.cursor()
            query = "SELECT asset_num, scrap FROM barcode WHERE asset_num = %s"
            cursor.execute(query, (barcode,))
            result = cursor.fetchone()
            if result:
                scrap_time = time.strftime('%Y-%m-%d (%B %d) %I:%M:%S %p', time.gmtime(result[1] - 4 * 3600))
                barcode_gp12_time = scrap_time
            else:
                barcode_gp12_time = "Not found in GP12 database"
            cursor.close()
            db.close()
        except MySQLdb.Error as e:
            barcode_gp12_time = f"Error querying GP12 database: {str(e)}"

        # Prepare context for rendering
        context = {
            'barcode': lasermark.bar_code,
            'grade': grade,
            'asset': asset,
            'lasermark_time': lasermark_time,
            'lasermark_duplicate_time': lasermark_duplicate_time,
            'barcode_gp12_time': barcode_gp12_time,
            'before_barcodes': adjusted_before_barcodes,
            'after_barcodes': adjusted_after_barcodes,
        }

        return render(request, 'barcode/barcode_result.html', context)

    except LaserMark.DoesNotExist:
        return render(request, 'barcode/barcode_scan.html', {'error': f'Barcode {barcode} not found in LaserMark'})









# =====================================================================================
# =====================================================================================
# =========================== Grades Dashboard ========================================
# =====================================================================================
# =====================================================================================



def get_grade_totals(asset, grade):
    """Retrieve the count of a specific grade for an asset over the past 24 hours.

    Args:
        asset (str): Identifier of the asset to filter LaserMark records.
        grade (str): Grade value to count (e.g., 'A', 'B', 'C').

    Returns:
        int or str:
            If successful, returns the integer count of LaserMark records matching
            the given `asset` and `grade` with `created_at` in the last 24 hours.
            On error, returns a string with the error message.

    """
    """
    Fetch the total count of a specific grade for a given asset in the last 24 hours.
    """
    last_24_hours = datetime.now() - timedelta(hours=24)
    try:
        with connections['default'].cursor() as cursor:
            query = """
                SELECT COUNT(*)
                FROM barcode_lasermark
                WHERE asset = %s AND grade = %s AND created_at >= %s;
            """
            cursor.execute(query, [asset, grade, last_24_hours])
            return cursor.fetchone()[0]
    except Exception as e:
        return f"Error: {str(e)}"


def fetch_pie_chart_data(asset):
    """Gather grade distribution and failure summary for an asset over the last 24 hours.

    This routine will call `get_grade_totals` for each of the possible grades A–F,
    then compute:
      - `total`: the sum of all grade counts
      - `grades`: a dict mapping each grade to its 24-hour count
      - `failures_total`: the combined count for grades D, E, and F

    Args:
        asset (str): Identifier of the asset whose LaserMark grades to aggregate.

    Returns:
        dict: {
            "total" (int): total scans in the last 24 hours,
            "grades" (dict[str, int]): per-grade counts,
            "failures_total" (int): sum of counts for grades D, E, and F
        }
    """
    """
    Fetch overall raw grade totals for the last 24 hours to be used in a pie chart,
    including total count and total number of failures (grades not A/B/C).
    """
    possible_grades = ["A", "B", "C", "D", "E", "F"]
    # Get the total counts for each grade
    grade_totals = {grade: get_grade_totals(asset, grade) for grade in possible_grades}
    
    # Compute total (all grades)
    total = sum(grade_totals.values()) if all(isinstance(val, int) for val in grade_totals.values()) else 0
    
    # Failures = any grade that is D, E, or F
    failures = grade_totals.get("D", 0) + grade_totals.get("E", 0) + grade_totals.get("F", 0)
    
    return {
        "total": total,
        "grades": grade_totals,
        "failures_total": failures
    }



def fetch_grade_data_for_asset(asset, time_interval=60):
    """Gather weekly and interval‐based grade statistics for a single asset.

    This function computes:
      1. Total scan counts per grade (A–F) over the last 7 full days plus today.
      2. Percentage breakdown of each grade against the weekly total.
      3. An 8-hour interval breakdown for each day in that period, including:
         - Interval start/end timestamps
         - Total scan count in the interval
         - Grade counts and their percentages in that interval

    Args:
        asset (str): Identifier of the asset whose LaserMark data to aggregate.
        time_interval (int): (Currently unused) Intended interval length in minutes
            for finer granularity reporting.

    Returns:
        dict: {
            "asset" (str): The asset identifier,
            "total_count_last_7_days" (int): Sum of all grade counts over the week,
            "grade_counts_last_7_days" (dict[str, str]): Each grade mapped to
                a string `"count (percentage%)"`,
            "breakdown_data" (list[dict]): Each entry contains:
                - "interval_start" (str): e.g. "Jun-19 00:00"
                - "interval_end"   (str): e.g. "Jun-19 08:00"
                - "total_count"    (int)
                - "grade_counts"   (dict[str, str]): per‐grade `"count (percentage%)"`
        }
    """
    """
    Fetch total grade counts and calculate percentage breakdown for a single asset,
    covering the last 7 full days + today, with 8-hour interval breakdowns.
    """
    now = datetime.now()
    last_7_days = now - timedelta(days=7)
    possible_grades = ["A", "B", "C", "D", "E", "F"]

    grade_totals = {grade: get_grade_totals(asset, grade) for grade in possible_grades}
    total_count = sum(val for val in grade_totals.values() if isinstance(val, int))

    grade_percentages = {}
    for g, cnt in grade_totals.items():
        if isinstance(cnt, int) and total_count > 0:
            pct = round((cnt / total_count * 100), 2)
            grade_percentages[g] = f"{cnt} ({pct}%)"
        else:
            grade_percentages[g] = f"{cnt} (0.00%)" if isinstance(cnt, int) else cnt

    interval_offsets = [0, 8, 16]  # Start times for each 8-hour interval
    
    breakdown_data = []
    num_days = 7  # 7 full days + today

    try:
        with connections['default'].cursor() as cursor:
            for i in range(num_days + 1):  # +1 for today
                start_date = last_7_days + timedelta(days=i)

                for start_hour in interval_offsets:
                    start_time = start_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                    end_time = start_time + timedelta(hours=8)  # Ensure we don't set an invalid hour

                    if start_time >= now:  # Avoid future times
                        continue

                    cursor.execute(
                        """
                        SELECT COUNT(*)
                        FROM barcode_lasermark
                        WHERE asset = %s AND created_at >= %s AND created_at < %s;
                        """,
                        [asset, start_time, end_time]
                    )
                    interval_total = cursor.fetchone()[0]

                    if interval_total == 0:
                        continue

                    cursor.execute(
                        """
                        SELECT grade, COUNT(*)
                        FROM barcode_lasermark
                        WHERE asset = %s AND created_at >= %s AND created_at < %s
                        GROUP BY grade;
                        """,
                        [asset, start_time, end_time]
                    )
                    interval_grades_raw = {row[0]: row[1] for row in cursor.fetchall()}

                    interval_grade_counts = {}
                    for g in possible_grades:
                        count_g = interval_grades_raw.get(g, 0)
                        pct_g = round((count_g / interval_total * 100), 2) if interval_total else 0
                        interval_grade_counts[g] = f"{count_g} ({pct_g}%)"

                    breakdown_data.append({
                        "interval_start": start_time.strftime("%b-%d %H:%M"),
                        "interval_end": end_time.strftime("%b-%d %H:%M"),
                        "total_count": interval_total,
                        "grade_counts": interval_grade_counts,
                    })

    except Exception as e:
        print(f"Error fetching grade data for asset {asset}: {e}")
        breakdown_data = []  # Ensure we always return a list

    return {
        "asset": asset,
        "total_count_last_7_days": total_count,
        "grade_counts_last_7_days": grade_percentages,
        "breakdown_data": breakdown_data,  # Ensures remove_sharp_dips always gets a list
    }







def remove_sharp_dips(breakdown_data, asset):
    """Filter out time intervals with anomalously low or zero grade coverage.

    From a list of interval statistics (each containing per‐grade `"count (pct%)"` strings),
    removes any interval where:
      1. The sum of all grade percentages is below 75%.
      2. (Optional) All grades are zero (disabled by default).

    Args:
        breakdown_data (list[dict]): A list of interval dicts, each with keys:
            - `"interval_start"` (str)
            - `"interval_end"` (str)
            - `"total_count"` (int)
            - `"grade_counts"` (dict[str, str]): Mapping grades 'A'–'F' to `"count (pct%)"` strings.
        asset (str): Identifier of the asset (used for logging or debugging).

    Returns:
        list[dict]: A filtered list containing only those intervals whose total
        grade coverage meets or exceeds 75%.
    """
    """
    Removes time intervals where:
    1. The sum of A, B, C, D, E, and F percentages is < 75%.
    2. All grades are 0 (0.00%).
    """
    filtered_intervals = []

    for interval in breakdown_data:
        grade_counts = interval.get("grade_counts", {})

        # Convert grade percentages to float values
        percentages = [
            float(count.split("(")[1].replace("%)", "").strip()) if "(" in count else 0
            for count in grade_counts.values()
        ]
        total_percentage = sum(percentages)

        # Remove interval if total percentage is less than 75%
        if total_percentage < 75:
            # print(
            #     f"⚠ Removing interval with low total percentage for asset {asset}: "
            #     f"{interval['interval_start']} to {interval['interval_end']} - Total: {total_percentage:.2f}%"
            # )
            continue  # Skip this interval, do not add it to the final list

        # # Remove interval if all grades are "0 (0.00%)"
        # if all(count.startswith("0 (") for count in grade_counts.values()):
        #     # print(
        #     #     f"⚠ Removing interval with all zero grades for asset {asset}: "
        #     #     f"{interval['interval_start']} to {interval['interval_end']}"
        #     # )
        #     continue  # Skip this interval, do not add it to the final list

        # If valid, add to the list
        filtered_intervals.append(interval)

    return filtered_intervals


def grades_dashboard(request, line=None):
    """Render the grades dashboard for a given production line or show the line selector.

    If `line` (e.g. '10R80') is provided and valid, this view:
      1. Looks up the list of `assets` for that line.
      2. Reads an optional `time_interval` (minutes) from `request.GET` (default 30).
      3. For each asset, calls:
         - `fetch_grade_data_for_asset()` to get weekly grade counts and interval breakdowns.
         - `fetch_pie_chart_data()` to get overall grade totals and failure counts.
      4. Filters each asset’s `breakdown_data` through `remove_sharp_dips()`.
      5. Packs all of that into a JSON structure and renders `barcode/grades_dashboard.html`.

    If `line` is `None`:
      - **GET**: Renders `barcode/grades_dashboard_finder.html` with a simple line‐selection form.
      - **POST**: Reads `selected_line` from `request.POST` and, if valid, redirects to 
        `/barcode/grades-dashboard/<selected_line>/`.

    Args:
        request (HttpRequest): The incoming request, possibly containing GET or POST parameters.
        line (str, optional): Identifier of the production line to display. Defaults to None.

    Returns:
        HttpResponse: Either a rendered dashboard template, a line‐selector template, or a redirect.

    Raises:
        Http404: If a non‐existent `line` is provided in the URL.
    """
    """
    If a line (e.g., '10R80') is provided in the URL, render the dashboard for that line.
    If no line is provided, show the selection page.
    """
    # Mapping of line names to assets
    line_to_assets = {
        "10R80": ["1534", "1505", "1811"],
        "AB1V": ["1724", "1725", "1750"],
        # Add more lines as needed
    }

    if line:
        # If a line is provided, load the dashboard for that line's assets
        assets = line_to_assets.get(line, [])
        if not assets:
            raise Http404("Invalid line selection.")

        time_interval = int(request.GET.get("time_interval", 30))  # Default 30 min
        data = {}

        for asset in assets:
            grade_data = fetch_grade_data_for_asset(asset, time_interval)
            pie_data = fetch_pie_chart_data(asset)

            grade_data["breakdown_data"] = remove_sharp_dips(grade_data.get("breakdown_data", []), asset)

            data[asset] = {
                **grade_data,
                "pie_chart_data": pie_data
            }

        return render(
            request,
            "barcode/grades_dashboard.html",
            {"json_data": json.dumps(data, indent=4)}
        )

    # If no line is given, show the selection page
    if request.method == "POST":
        selected_line = request.POST.get("line")
        valid_lines = line_to_assets.keys()

        if selected_line in valid_lines:
            return redirect(f"/barcode/grades-dashboard/{selected_line}/")

    return render(request, "barcode/grades_dashboard_finder.html")






def grades_dashboard_finder(request):
    """Render a line‐selection page for the grades dashboard and handle the redirect.

    Displays a form where users can choose a production line (e.g. "10R80", "AB1V").
    On POST, if the selected line is valid, redirects to the corresponding
    grades dashboard URL `/barcode/grades-dashboard/<line>/`.

    Args:
        request (HttpRequest): The incoming HTTP request. For POST, expects a form
            field `"line"` with one of the valid line names.

    Returns:
        HttpResponse: On GET, renders `"barcode/grades_dashboard_finder.html"`.
        HttpResponseRedirect: On valid POST, redirects to the grades dashboard for
        the chosen line.
    """
    """
    Renders a selection page where users choose a line (e.g., 10R80, AB1V).
    Redirects them to the dashboard URL using the line name.
    """
    if request.method == "POST":
        selected_line = request.POST.get("line")

        # Define available lines
        valid_lines = ["10R80", "AB1V"]  # Add more if needed

        if selected_line in valid_lines:
            return redirect(f"/barcode/grades-dashboard/{selected_line}/")

    # Render the selection page if GET request
    return render(request, "barcode/grades_dashboard_finder.html")
