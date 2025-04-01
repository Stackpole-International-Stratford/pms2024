from datetime import datetime
import importlib.util
import os
from django.utils.dateparse import parse_datetime
from django.http import JsonResponse
from plant.models.setupfor_models import SetupFor

def fetch_prdowntime1_entries(assetnum, called4helptime, completedtime):
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
        SELECT problem, called4helptime, completedtime
        FROM pr_downtime1
        WHERE assetnum = %s
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





def calculate_downtime(machine, cursor, start_timestamp, end_timestamp, downtime_threshold=5, machine_parts=None):
    """
    Calculate the total downtime for a specific machine over a given time period.

    The downtime is calculated based on the intervals between consecutive production timestamps
    that exceed a given threshold. If no production timestamps are present, the entire period is
    considered downtime.

    Parameters:
    - machine (str): The identifier of the machine being analyzed.
    - machine_parts (list): A list of part identifiers associated with the machine.
    - start_timestamp (int): The starting timestamp of the analysis period (epoch time in seconds).
    - end_timestamp (int): The ending timestamp of the analysis period (epoch time in seconds).
    - downtime_threshold (int): The threshold (in minutes) above which an interval is considered downtime.
    - cursor (object): A database cursor for querying production data.

    Returns:
    - int: The total downtime in minutes for the specified machine and time period.
    """

    machine_downtime = 0  # Accumulate total downtime here
    prev_timestamp = start_timestamp  # Store the previous timestamp for interval calculations

    # If no parts are provided, assume the machine was entirely down during the period
    if not machine_parts:
        query = """
            SELECT TimeStamp
            FROM GFxPRoduction
            WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s
            ORDER BY TimeStamp ASC;
        """
        params = [machine, start_timestamp, end_timestamp]
    else:
        placeholders = ','.join(['%s'] * len(machine_parts)) # Create placeholders for params
        query = f"""
            SELECT TimeStamp
            FROM GFxPRoduction
            WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s AND Part IN ({placeholders})
            ORDER BY TimeStamp ASC;
        """
        params = [machine, start_timestamp, end_timestamp] + machine_parts

    cursor.execute(query, params) #execute the query

    timestamps_fetched = False
    for row in cursor:
        timestamps_fetched = True
        current_timestamp = row[0] #Extract the timestamp from the row

        time_delta = (current_timestamp - prev_timestamp) /60 #Convert seconds to minutes 
        # Add the downtime that exceeds the threshold
        minutes_over = max(0, time_delta - downtime_threshold)
        machine_downtime += minutes_over

        #Update the previous timestamp to the current one
        prev_timestamp = current_timestamp

    if not timestamps_fetched:
        # If no timestamps were fetched, assume the machine was entirely down during the period
        total_potential_minutes = (end_timestamp - start_timestamp) / 60 # Convert seconds to minutes
        return round(total_potential_minutes)
    
    #Handle the time from the last production timestamp to the end of the period
    remaining_time = (end_timestamp - prev_timestamp) / 60 # Convert seconds to minutes
    machine_downtime += remaining_time

    return round(machine_downtime)

    # placeholders = ','.join(['%s'] * len(machine_parts))  # Create placeholders for part list
    # query = f"""
    #     SELECT TimeStamp
    #     FROM GFxPRoduction
    #     WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s AND Part IN ({placeholders})
    #     ORDER BY TimeStamp ASC;
    # """
    # sql  = f'SELECT TimeStamp '
    # sql += f'FROM GFxPRoduction '
    # sql += f'WHERE Machine = %s '
    # sql += f'AND TimeStamp BETWEEN %s AND %s '
    # if machine_parts:
    #     sql+= f'AND Part IN ({placeholders}) '
    # sql += f'ORDER BY TimeStamp ASC;'

  
def calculate_downtime_and_threshold_count(
    machine, cursor, start_timestamp, end_timestamp, downtime_threshold=300, machine_parts=None
):
    """
    Calculate the total downtime and count the number of times downtime exceeded a threshold.
    The downtime threshold is in seconds, but downtime in results is in minutes.

    Parameters:
    - machine (str): The identifier of the machine being analyzed.
    - machine_parts (list): A list of part identifiers associated with the machine.
    - start_timestamp (int): The starting timestamp of the analysis period (epoch time in seconds).
    - end_timestamp (int): The ending timestamp of the analysis period (epoch time in seconds).
    - downtime_threshold (int): The threshold (in seconds) above which an interval is considered downtime.
    - cursor (object): A database cursor for querying production data.

    Returns:
    - tuple: (total_downtime_in_minutes, threshold_breach_count)
    """
    machine_downtime = 0  # Accumulate total downtime here in seconds
    threshold_breach_count = 0  # Count the number of times downtime exceeds the threshold
    prev_timestamp = start_timestamp  # Store the previous timestamp for interval calculations

    # If no parts are provided, assume the machine was entirely down during the period
    if not machine_parts:
        query = """
            SELECT TimeStamp
            FROM GFxPRoduction
            WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s
            ORDER BY TimeStamp ASC;
        """
        params = [machine, start_timestamp, end_timestamp]
    else:
        placeholders = ','.join(['%s'] * len(machine_parts))  # Create placeholders for params
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
        current_timestamp = row[0]  # Extract the timestamp from the row

        time_delta = current_timestamp - prev_timestamp  # Calculate time difference in seconds

        # Check if the downtime exceeds the threshold
        if time_delta > downtime_threshold:
            threshold_breach_count += 1

        # Add the downtime that exceeds the threshold
        seconds_over = max(0, time_delta - downtime_threshold)
        machine_downtime += seconds_over

        # Update the previous timestamp to the current one
        prev_timestamp = current_timestamp

    if not timestamps_fetched:
        # If no timestamps were fetched, assume the machine was entirely down during the period
        total_potential_seconds = end_timestamp - start_timestamp
        return round(total_potential_seconds / 60), 1  # Entire period is a single threshold breach

    # Handle the time from the last production timestamp to the end of the period
    remaining_time = end_timestamp - prev_timestamp  # Time in seconds
    if remaining_time > downtime_threshold:
        threshold_breach_count += 1
    machine_downtime += remaining_time

    # Convert downtime to minutes for return
    return round(machine_downtime / 60), threshold_breach_count
  

def calculate_total_produced(machine, machine_parts, start_timestamp, end_timestamp, cursor):
    """
    Calculate the total number of parts produced by a specific machine over a given time period.

    This function queries a production database to count the number of records for the specified
    machine and parts within the given time range. It iterates over the provided parts and
    sums up the production counts for each part.

    Parameters:
    - machine (str): The identifier of the machine being analyzed.
    - machine_parts (list): A list of part identifiers associated with the machine.
    - start_timestamp (int): The starting timestamp of the analysis period (epoch time in seconds).
    - end_timestamp (int): The ending timestamp of the analysis period (epoch time in seconds).
    - cursor (object): A database cursor for querying production data.

    Returns:
    - int: The total count of parts produced by the machine during the specified time period.
    """
    total_entries = 0  # Initialize total count of produced parts

    if not machine_parts:
        # Query all entries for hte machine if no specific parts are provided
        query = """
            SELECT COUNT(*)
            FROM GFxPRoduction
            WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s;
        """
        cursor.execute(query, (machine, start_timestamp, end_timestamp))
        total_entries = cursor.fetchone()[0] or 0
    else:
        #Query specific parts
        for part in machine_parts:
            query = """
                SELECT COUNT(*)
                FROM GFxPRoduction
                WHERE Machine = %s AND TimeStamp BETWEEN %s AND %s AND Part = %s;
            """
            cursor.execute(query, (machine, start_timestamp, end_timestamp, part))
            part_total = cursor.fetchone()[0] or 0
            total_entries += part_total

    return total_entries

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









# ==================================================================
# ==================================================================
# ==================== Fetch Part for Asset ========================
# ==================================================================
# ==================================================================


def get_part_number(asset_id, datetime_str):
    """
    Given an asset ID and a datetime string, this function returns a dictionary containing the
    part number for the latest SetupFor record (on or before the provided datetime). If an error occurs
    or no record is found, an appropriate error message is returned.

    :param asset_id: The asset identifier.
    :param datetime_str: A datetime string in ISO format (e.g., from an HTML datetime-local input).
    :return: A dictionary with either {'part_number': <value>} or {'error': <message>}.
    """

    # Validate input
    if not asset_id or not datetime_str:
        return {'error': 'Asset and datetime are required.'}

    # Parse the datetime string from the input.
    dt = parse_datetime(datetime_str)
    if dt is None:
        return {'error': 'Invalid datetime format.'}

    # Convert the datetime to an epoch timestamp.
    # Note: If dt is naive, dt.timestamp() treats it as local time.
    epoch_time = int(dt.timestamp())

    # Query for the latest SetupFor record for the given asset that occurred on or before the provided datetime.
    record = SetupFor.objects.filter(asset_id=asset_id, since__lte=epoch_time).order_by('-since').first()

    if record:
        return {'part_number': record.part.part_number}
    else:
        return {'error': 'No record found for the given asset and time.'}
    














# ====================================================================
# ====================================================================
# ==================== OA By Day Useful Functions ====================
# ====================================================================
# ====================================================================


