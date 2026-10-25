"""
Step 1: Create sample employee data.

We use made-up data (never real company data) so the project can be shared publicly.
Each employee belongs to a team and scores each weekday from 1 (dislike) to 5 (love).
Midweek days are made more popular on purpose, so the model has a real problem to
solve: everyone wants Tuesday to Thursday, but there are not enough seats.
"""
import csv
import random

random.seed(42)  # same "random" data every time, so results are repeatable

NUM_EMPLOYEES = 60
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
TEAMS = ["Design", "Analytics", "PMO", "Quality", "Support"]

# How popular each day is on average (5 = most popular)
DAY_POPULARITY = {"Mon": 2, "Tue": 4, "Wed": 5, "Thu": 4, "Fri": 1}

rows = []
for i in range(1, NUM_EMPLOYEES + 1):
    row = {"employee_id": f"E{i:03d}", "team": random.choice(TEAMS)}
    for day in DAYS:
        # start from the day's popularity, add some personal variation,
        # then keep the score between 1 and 5
        score = DAY_POPULARITY[day] + random.randint(-2, 2)
        row[day] = max(1, min(5, score))
    rows.append(row)

with open("employees.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["employee_id", "team"] + DAYS)
    writer.writeheader()
    writer.writerows(rows)

print(f"Created employees.csv with {NUM_EMPLOYEES} employees.")
