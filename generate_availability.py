"""
Step 1b: Create sample availability data for one week.

Real weeks are messy: some people work part-time, some are on leave,
and some can't come in on a particular day (a fixed client call, school pickup).
This script creates availability.csv, one row per employee, with each weekday marked as:

    available    - can come to the office
    off          - not a working day (part-time staff)
    leave        - on leave
    unavailable  - working, but can't come to the office that day

Run generate_data.py first: this script reads employees.csv.
"""
import csv
import random

random.seed(7)  # same "random" week every time, so results are repeatable

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
PART_TIME_SHARE = 0.15      # about 15% of people work part-time
LEAVE_CHANCE = 0.15         # chance a person takes some leave this week
UNAVAILABLE_CHANCE = 0.10   # chance a person has one day they can't come in

with open("employees.csv") as f:
    employee_ids = [row["employee_id"] for row in csv.DictReader(f)]

rows = []
for employee_id in employee_ids:
    week = {day: "available" for day in DAYS}
    contract = "full-time"

    if random.random() < PART_TIME_SHARE:
        contract = "part-time"
        working_days = random.choice([3, 4])
        for day in random.sample(DAYS, 5 - working_days):
            week[day] = "off"

    if random.random() < LEAVE_CHANCE:
        working = [d for d in DAYS if week[d] == "available"]
        # leave is usually consecutive days, e.g. Wed-Fri
        length = random.choice([1, 1, 2, 3, 5])
        start = random.randint(0, max(0, len(working) - length))
        for day in working[start:start + length]:
            week[day] = "leave"

    if random.random() < UNAVAILABLE_CHANCE:
        working = [d for d in DAYS if week[d] == "available"]
        if len(working) > 1:
            week[random.choice(working)] = "unavailable"

    rows.append({"employee_id": employee_id, "contract": contract, **week})

with open("availability.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["employee_id", "contract"] + DAYS)
    writer.writeheader()
    writer.writerows(rows)

part_time = sum(r["contract"] == "part-time" for r in rows)
on_leave = sum(any(r[d] == "leave" for d in DAYS) for r in rows)
blocked = sum(any(r[d] == "unavailable" for d in DAYS) for r in rows)
print(f"Created availability.csv: {part_time} part-time, {on_leave} taking leave, "
      f"{blocked} with a day they can't come in.")
