# views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings
import MySQLdb
from plant.models.maintenance_models import *
from plant.models.heat_break_models import *


DAVE_HOST = settings.NEW_HOST
DAVE_USER = settings.DAVE_USER
DAVE_PASSWORD = settings.DAVE_PASSWORD
DAVE_DB = settings.DAVE_DB
# ---------- helpers ----------

def now_epoch() -> int:
    return int(timezone.now().timestamp())

def epoch_to_iso(epoch: int | None) -> str | None:
    if epoch is None:
        return None
    # Render in the current Django timezone
    return timezone.datetime.fromtimestamp(epoch, tz=timezone.get_current_timezone()).isoformat()

def parse_to_epoch(value: str | None) -> int:
    """
    Accepts either:
      - epoch (e.g. '1724162400' or '1724162400.123')
      - ISO 8601 (e.g. '2025-08-20T10:21:00' or '2025-08-20 10:21:00+00:00')
    Falls back to now() if it can't parse.
    """
    if not value:
        return now_epoch()

    # 1) try epoch directly
    try:
        return int(float(value))
    except Exception:
        pass

    # 2) try ISO 8601
    try:
        dt = timezone.datetime.fromisoformat(value)
        if dt.tzinfo is None:
            # assume current TZ for naive times
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return int(dt.timestamp())
    except Exception:
        # 3) fallback
        return now_epoch()

# ---------- views ----------

@login_required
def heat_toggle_view(request):
    print("➡️ heat_toggle_view called by:", request.user)

    machines = DowntimeMachine.objects.filter(is_tracked=True)\
        .order_by("line", "operation", "machine_number")
    print(f"Found {machines.count()} tracked machines")

    # Map active heatbreaks by machine_id
    active_qs = HeatBreak.objects.filter(machine__in=machines, end_time_epoch__isnull=True)
    active_by_machine = {
        hb.machine_id: {
            "id": hb.id,
            "duration": hb.duration_minutes,
            "start_time_iso": epoch_to_iso(hb.start_time_epoch),
        }
        for hb in active_qs
    }

    # Group machines by line and attach active hb metadata to each machine
    grouped_data = {}
    for m in machines:
        # attach for easy access in template
        m.active_hb = active_by_machine.get(m.id)  # either dict or None
        grouped_data.setdefault(m.line, []).append(m)

    for line, mlist in grouped_data.items():
        print(f"Line {line}: {len(mlist)} machines")

    context = {
        "grouped_data": grouped_data,
        "durations": [15, 30, 45],
    }
    print("✅ Context prepared for template")
    return render(request, "plant/heat_toggle.html", context)


@login_required
def turn_on_heat(request, machine_id):
    print("➡️ turn_on_heat called by:", request.user, "for machine_id:", machine_id)

    if request.method != "POST":
        print("❌ turn_on_heat invalid request method:", request.method)
        return JsonResponse({"status": "error", "msg": "Invalid request"}, status=400)

    duration_raw = request.POST.get("duration")
    print("POST duration raw value:", duration_raw)
    try:
        duration = int(duration_raw)
    except Exception as e:
        print("❌ Error parsing duration:", e)
        return JsonResponse({"status": "error", "msg": "Invalid duration"}, status=400)

    machine = get_object_or_404(DowntimeMachine, pk=machine_id)
    print("✅ Found machine:", machine)

    start_epoch = now_epoch()
    hb = HeatBreak.objects.create(
        machine=machine,
        machine_number=machine.machine_number,           # ✅ snapshot the machine number
        duration_minutes=duration,
        start_time_epoch=start_epoch,
        turned_on_by_username=request.user.get_username(),  # ✅ username, not FK
    )
    print("✅ Created HeatBreak:", hb.id, "at epoch", hb.start_time_epoch)

    return JsonResponse({
        "status": "ok",
        "heatbreak_id": hb.id,
        "start_time_epoch": hb.start_time_epoch,
        "start_time_iso": epoch_to_iso(hb.start_time_epoch),
    })


@login_required
def turn_off_heat(request, heatbreak_id):
    print("➡️ turn_off_heat called by:", request.user, "for heatbreak_id:", heatbreak_id)

    if request.method != "POST":
        print("❌ turn_off_heat invalid request method:", request.method)
        return JsonResponse({"status": "error", "msg": "Invalid request"}, status=400)

    hb = get_object_or_404(HeatBreak, pk=heatbreak_id, end_time_epoch__isnull=True)
    print("✅ Found active HeatBreak:", hb.id, "machine:", hb.machine)

    end_time_raw = request.POST.get("end_time")
    print("POST end_time raw value:", end_time_raw)

    end_epoch = parse_to_epoch(end_time_raw)
    hb.end_time_epoch = end_epoch
    hb.turned_off_by_username = request.user.get_username()  # ✅ username
    hb.updated_at_epoch = now_epoch()                        # ✅ keep updated_at in sync (unless model auto-updates)
    hb.save()
    print("✅ Updated HeatBreak:", hb.id, "end_time_epoch:", hb.end_time_epoch)

    # 🔗 call hook after save
    hook_to_downtime_app(
        machine_id=hb.machine.id,
        start_epoch=hb.start_time_epoch,
        end_epoch=hb.end_time_epoch,
        turned_on_username=hb.turned_on_by_username,
        turned_off_username=hb.turned_off_by_username,
    )

    return JsonResponse({
        "status": "ok",
        "end_time_epoch": hb.end_time_epoch,
        "end_time_iso": epoch_to_iso(hb.end_time_epoch),
    })










# ======================================================================
# ======================================================================
# ==================== Hook now into downtime app ======================
# ======================================================================
# ======================================================================


def hook_to_downtime_app(machine_id, start_epoch, end_epoch, turned_on_username, turned_off_username):
    """
    Placeholder integration. For now, just print.
    """
    print("📡 hook_to_downtime_app called:")
    print("   machine_id        :", machine_id)
    print("   start_time_epoch  :", start_epoch)
    print("   end_time_epoch    :", end_epoch)
    print("   turned_on_username:", turned_on_username)
    print("   turned_off_username:", turned_off_username)

    # also call gfx_run
    gfx_run(
        host=DAVE_HOST,
        user=DAVE_USER,
        password=DAVE_PASSWORD,
        db_name=DAVE_DB,
        machine_id=machine_id,
        start_epoch=start_epoch,
        end_epoch=end_epoch,
        turned_on_username=turned_on_username,
        turned_off_username=turned_off_username,
    )


def gfx_run(host, user, password, db_name,
            machine_id, start_epoch, end_epoch,
            turned_on_username, turned_off_username):
    """
    Connects to MySQL and prints the most recent row from GFX_Production,
    then also prints the latest MachineDowntimeEvent from Django ORM.
    """
    print("🧪 gfx_run: attempting MySQL connection...")

    try:
        conn = MySQLdb.connect(
            host=host,
            user=user,
            passwd=password,
            db=db_name,
            charset="utf8mb4"
        )
        cursor = conn.cursor()
        print("✅ gfx_run: connected")

        # Try to fetch last row ordered by id (adjust if needed)
        cursor.execute("SELECT * FROM GFxPRoduction ORDER BY id DESC LIMIT 1;")
        row = cursor.fetchone()

        if row:
            cols = [desc[0] for desc in cursor.description]
            print("🧾 gfx_run: last row in GFX_Production:")
            for col, val in zip(cols, row):
                print(f"   {col}: {val}")
        else:
            print("⚠️ gfx_run: no rows in GFX_Production")

        cursor.close()
        conn.close()

    except Exception as e:
        print("❌ gfx_run: DB error ->", repr(e))

    # Log the context we were passed
    print("🧷 gfx_run context:")
    print("   machine_id        :", machine_id)
    print("   start_time_epoch  :", start_epoch)
    print("   end_time_epoch    :", end_epoch)
    print("   turned_on_username:", turned_on_username)
    print("   turned_off_username:", turned_off_username)

    # ---------- NEW: also dump latest MachineDowntimeEvent ----------
    try:
        mde = (MachineDowntimeEvent.objects
               .filter(is_deleted=False)
               .order_by('-created_at_UTC')
               .first())

        if not mde:
            mde = (MachineDowntimeEvent.objects
                   .filter(is_deleted=False)
                   .order_by('-start_epoch')
                   .first())

        if mde:
            print("🧾 Latest MachineDowntimeEvent:")
            print(f"   id                : {mde.id}")
            print(f"   line              : {mde.line}")
            print(f"   machine           : {mde.machine}")
            print(f"   category          : {mde.category}")
            print(f"   subcategory       : {mde.subcategory}")
            print(f"   code              : {mde.code}")
            print(f"   start_epoch       : {mde.start_epoch}")
            print(f"   closeout_epoch    : {mde.closeout_epoch}")
            print(f"   comment           : {mde.comment}")
            print(f"   labour_types      : {mde.labour_types}")
            print(f"   employee_id       : {mde.employee_id}")
            print(f"   closeout_comment  : {mde.closeout_comment}")
            print(f"   is_deleted        : {mde.is_deleted}")
            print(f"   created_at_UTC    : {mde.created_at_UTC}")
            print(f"   updated_at_UTC    : {mde.updated_at_UTC}")
        else:
            print("⚠️ No MachineDowntimeEvent rows found.")

    except Exception as e:
        print("❌ gfx_run: ORM error ->", repr(e))
