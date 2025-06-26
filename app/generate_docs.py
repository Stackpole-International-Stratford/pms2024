#!/usr/bin/env python3
import os
import sys

# === 1) Django setup ===
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pms.settings")
print(f"[DEBUG] DJANGO_SETTINGS_MODULE = {os.environ['DJANGO_SETTINGS_MODULE']}")

import django
django.setup()
print("[DEBUG] Django setup complete")

# === 2) Build module list and flags ===
MODULES = [
    "barcode.views",
    "barcode.models",
    "barcode.forms",
    "dashboards.views",
    "dashboards.models",
    "forms.views",
    "forms.models",
    "forms.forms",
    "plant.views.temp_sensor_views",
    "plant.views.setupfor_views",
    "plant.views.prodmon_views",
    "plant.views.password_views",
    "plant.views.maintenance_views",
    "plant.views.hr_views",
    "plant.views.cycle_crud_views",
    "plant.models.tempsensor_models",
    "plant.models.setupfor_models",
    "plant.models.password_models",
    "plant.models.maintenance_models",
    "plant.models.absentee_models",
    "plant.forms.setupfor_forms",
    "plant.forms.password_forms",
    "plant.forms.hr_forms",
    "plant.forms.cycle_crud_forms",
    "prod_query.views",
    "prod_query.models",
    "prod_query.forms",
    "quality.views",
    "quality.models",
    "quality.forms",
]
OUTPUT_DIR = "docs/apid_forms"

# Compose argv for pdoc: pretend the user ran:
#   pdoc --html -o docs/apid_forms <MODULES...>
new_argv = ["pdoc", "--html", "-o", OUTPUT_DIR] + MODULES

print(f"[DEBUG] Final sys.argv for pdoc: {new_argv!r}")

# Inject into sys.argv
sys.argv[:] = new_argv

# === 3) Invoke pdoc ===
from pdoc.cli import main

try:
    retval = main()  # main() will read sys.argv
    print(f"[DEBUG] pdoc finished, exit code {retval}")
    sys.exit(retval)
except Exception as e:
    print(f"[ERROR] Exception during pdoc generation: {e!r}")
    import traceback; traceback.print_exc()
    sys.exit(1)
