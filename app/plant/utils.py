

import MySQLdb
from django.conf import settings


def get_db_connection():
    return MySQLdb.connect(
        host=settings.DAVE_HOST,
        user=settings.DAVE_USER,
        passwd=settings.DAVE_PASSWORD,
        db=settings.DAVE_DB
    )



def get_zones():
    """
    Connects to the DB, retrieves the unique zones and their humidex
    (divided by 10) from temp_monitors, and returns a list of dicts:
      [ { 'zone': 0, 'humidex': 44.2 }, … ]
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT zone, humidex
                  FROM temp_monitors
              ORDER BY zone
            """)
            return [
                {
                    'zone': row[0],
                    # assume humidex stored as int*10, so convert to real float
                    'humidex': row[1] / 10.0
                }
                for row in cur.fetchall()
            ]
    except MySQLdb.Error as e:
        print(f"Error fetching zones: {e}")
        return []
    finally:
        conn.close()