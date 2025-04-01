import os
import importlib.util
import mysql.connector
from mysql.connector import Error
import datetime
import json

# Dynamically import `settings.py` from your Django project
def load_django_settings():
    """ Load Django settings.py dynamically to access database connection details. """
    settings_path = os.path.join(os.path.dirname(__file__), '../pms/settings.py')
    spec = importlib.util.spec_from_file_location("settings", settings_path)
    settings = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(settings)
    return settings

# Load settings
settings = load_django_settings()

# Extract database connection details for Dave's database
DB_HOST = settings.DAVE_HOST
DB_USER = settings.DAVE_USER
DB_PASSWORD = settings.DAVE_PASSWORD
DB_NAME = settings.DAVE_DB

def get_press_changeover_data():
    """
    Connects to the database and retrieves:
      - asset,
      - the last 9 characters of 'problem' as part_number,
      - completedtime converted to an epoch timestamp.
    
    The function writes the results to a JSON file (changeovers.json)
    and returns a list of dictionaries for further processing.
    """
    try:
        # Establish database connection
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )

        if connection.is_connected():
            cursor = connection.cursor()

            # Query to get asset, last 9 characters of problem, and completedtime
            query = """
                SELECT asset, SUBSTRING(problem, -9) AS part_number, completedtime
                FROM Press_Changeovers
                WHERE LENGTH(problem) >= 9
                ORDER BY asset, part_number;
            """
            cursor.execute(query)

            # Fetch results
            results = cursor.fetchall()

            # Process results: convert completedtime to epoch and build a list of changeover records
            changeovers = []
            for asset, part_number, completedtime in results:
                # Ensure completedtime is a datetime object
                if isinstance(completedtime, str):
                    completedtime = datetime.datetime.strptime(completedtime, "%Y-%m-%d %H:%M:%S")
                epoch_time = int(completedtime.timestamp())
                changeover = {
                    'asset': asset,
                    'part_number': part_number,
                    'completed_time_epoch': epoch_time
                }
                changeovers.append(changeover)

            # Write the list of dictionaries to a JSON file
            with open("changeovers.json", "w") as json_file:
                json.dump(changeovers, json_file, indent=2)
            print("Data has been written to changeovers.json")

            return changeovers

    except Error as e:
        print(f"Error: {e}")
        return []

    finally:
        # Close the database connection if open
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()


if __name__ == "__main__":
    # Run the function to get data and output it to changeovers.json
    changeover_data = get_press_changeover_data()
