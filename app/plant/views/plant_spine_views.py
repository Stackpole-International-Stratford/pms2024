# plant/views.py
from datetime import datetime, timezone
from zoneinfo import ZoneInfo     # Python 3.9+ built-in; for older Pythons use `import pytz`
from django.shortcuts import render
from plant.models.plantSpine_models import PlantSpine

def plant_blueprint(request):
    """
    Displays all PlantSpine records in a table, converting the
    cycle_time_effective_date epoch into an EST/EDT datetime.
    """
    records = PlantSpine.objects.all()

    # set up the Eastern timezone
    eastern = ZoneInfo('America/New_York')
    for rec in records:
        ts = rec.cycle_time_effective_date
        # if you actually store milliseconds, convert to seconds:
        if ts > 10**12:
            ts = ts / 1000.0
        # interpret as UTC then convert to Eastern
        rec.effective_dt = (
            datetime.fromtimestamp(ts, tz=timezone.utc)
                    .astimezone(eastern)
        )

    return render(request, 'plant/plant_blueprint.html', {
        'records': records,
    })
