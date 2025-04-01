

'''
Press 272

Feb 2 11pm (1738555200) until Feb 7th 11pm (1738987200)

We calculated 2011 minutes of total downtime where 509 of those minutes were planned.


There is a total of 7200 total potential minutes in a week


We produced 16,873 parts in that time from GFx table directly


The target each week is 27,496 parts made









If it's over 4 hours and no overlap we need to assume that it's planned downtime. Which is what's happening right now, it's going into that bucket. 


If it's under 4 hours and no overlap, we need to assume that it's unplanned downtime. That is the check we need to make. 












'''



# Data for Press 272 (all times in minutes)
total_potential_minutes = 7200      # Total potential minutes in a week
planned_downtime = 509              # Planned downtime (minutes)
total_downtime = 2011               # Total downtime (planned + unplanned, minutes)
actual_parts = 16873                # Actual parts produced
target_parts = 27496                # Weekly target parts

# 1. Planned Production Time (PPT)
# Subtract planned downtime from the total potential minutes
planned_production_time = total_potential_minutes - planned_downtime

# 2. Run Time
# Unplanned downtime is the total downtime minus the planned downtime
unplanned_downtime = total_downtime - planned_downtime
# Run Time is the Planned Production Time minus unplanned downtime
run_time = planned_production_time - unplanned_downtime

# 3. Ideal Cycle Time (in minutes per part)
# This is the time it would take to produce one part ideally, based on the target
ideal_cycle_time = planned_production_time / target_parts

# 4. Availability
availability = run_time / planned_production_time

# 5. Performance
# Performance compares the ideal production time for the parts produced to the actual run time
performance = (ideal_cycle_time * actual_parts) / run_time

# 6. Quality (assumed to be 100%)
quality = 1.0

# Overall Equipment Effectiveness (OEE)
oee = availability * performance * quality

print("Press 272 OEE Calculation Breakdown (using minutes):")
print(f"Planned Production Time: {planned_production_time:.2f} minutes")
print(f"Run Time: {run_time:.2f} minutes")
print(f"Ideal Cycle Time: {ideal_cycle_time:.4f} minutes per part")
print(f"Availability: {availability:.2%}")
print(f"Performance: {performance:.2%}")
print(f"Quality: {quality:.2%}")
print(f"OEE: {oee:.2%}")
<<<<<<< HEAD
=======




# Data for Press xyz
total_potential_minutes = x      # Total potential minutes in a week
planned_downtime = y              # Planned downtime (minutes)
total_downtime = z               # Total downtime (planned + unplanned, minutes)
actual_parts = a                # Actual parts produced
target_parts = b               # Weekly target parts

# 1. Planned Production Time (PPT)
# Subtract planned downtime from the total potential minutes
planned_production_time = total_potential_minutes - planned_downtime

# 2. Run Time
# Unplanned downtime is the total downtime minus the planned downtime
unplanned_downtime = total_downtime - planned_downtime
# Run Time is the Planned Production Time minus unplanned downtime
run_time = planned_production_time - unplanned_downtime

# 3. Ideal Cycle Time (in minutes per part)
# This is the time it would take to produce one part ideally, based on the target
ideal_cycle_time = planned_production_time / target_parts

# 4. Availability
availability = run_time / planned_production_time

# 5. Performance
# Performance compares the ideal production time for the parts produced to the actual run time
performance = (ideal_cycle_time * actual_parts) / run_time

# 6. Quality (assumed to be 100%)
quality = 1.0

# Overall Equipment Effectiveness (OEE)
oee = availability * performance * quality
>>>>>>> production
