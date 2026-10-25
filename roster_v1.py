"""
Step 2: Build the best possible office roster.

The question the model answers:
    "Which days should each person come to the office, so that people get
     the days they like most, without running out of seats?"

How it works, in three parts:
    1. Decisions  - for every person and every day: in office (1) or not (0)
    2. Rules      - seats per day, and number of office days per person
    3. Goal       - make the total preference score as high as possible

Solver: SciPy's milp function, which uses the HiGHS optimisation engine.
It runs natively on Windows, Intel Macs and Apple-chip Macs.
"""
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds

# ---------- Settings: change these and re-run to test scenarios ----------
SEATS = 40          # desks available each day
MIN_DAYS = 3        # minimum office days per person per week
MAX_DAYS = 3        # maximum office days per person per week
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

# ---------- Load the data ----------
employees = pd.read_csv("employees.csv")
people = list(employees["employee_id"])
preference = employees.set_index("employee_id")[DAYS]   # table: person x day -> score

n_people = len(people)
n_days = len(DAYS)

# ---------- 1. Decisions ----------
# The solver works with one long list of yes/no decisions.
# This helper tells us where "person p is in office on day d" sits in that list.
n_decisions = n_people * n_days

def decision(p, d):
    return p * n_days + d

# ---------- 3. Goal ----------
# Each decision is worth that person's score for that day.
# SciPy always minimises, so we minimise the negative score,
# which is the same as maximising the score.
scores = preference.to_numpy().flatten()     # same order as decision(p, d)
goal = -scores

# ---------- 2. Rules ----------
# Each rule is a row saying which decisions to add up, plus the allowed range.
rules, lowest, highest = [], [], []

for d in range(n_days):
    # no more people than seats on any day
    row = np.zeros(n_decisions)
    for p in range(n_people):
        row[decision(p, d)] = 1
    rules.append(row); lowest.append(0); highest.append(SEATS)

for p in range(n_people):
    # each person comes in between MIN_DAYS and MAX_DAYS days
    row = np.zeros(n_decisions)
    for d in range(n_days):
        row[decision(p, d)] = 1
    rules.append(row); lowest.append(MIN_DAYS); highest.append(MAX_DAYS)

# ---------- Solve ----------
result = milp(
    c=goal,
    constraints=LinearConstraint(np.array(rules), lowest, highest),
    integrality=np.ones(n_decisions),   # every decision must be a whole number...
    bounds=Bounds(0, 1),                # ...between 0 and 1, so 0 or 1
)

if not result.success:
    print("No valid roster exists with these settings. Try more seats or fewer days.")
    raise SystemExit

# ---------- Results ----------
choices = result.x.round().astype(int).reshape(n_people, n_days)
roster = pd.DataFrame(choices, index=people, columns=DAYS)

# Satisfaction = score of assigned days / score of the person's best possible days
achieved = (roster * preference).sum(axis=1)
best_possible = preference.apply(lambda row: row.nlargest(MAX_DAYS).sum(), axis=1)
satisfaction = (achieved / best_possible * 100).round(1)

roster.insert(0, "team", employees.set_index("employee_id")["team"])
roster["satisfaction_%"] = satisfaction
roster.to_csv("roster.csv", index_label="employee_id")

print(f"People in office per day (seats available: {SEATS})")
for d in DAYS:
    print(f"  {d}: {roster[d].sum()}")
print(f"\nAverage satisfaction: {satisfaction.mean():.1f}%")
print(f"Lowest satisfaction:  {satisfaction.min():.1f}%  <- fairness is what v2 improves")
print(f"People who got all their favourite days: {(satisfaction == 100).sum()} of {n_people}")
print("\nFull roster saved to roster.csv")
