"""
Version 3: explain problems and test what-if scenarios.

Version 2 built a fair roster with team days, but when the rules conflicted
it could only say "no valid roster". Version 3 adds:
    1. Diagnosis - says WHY no roster is possible, and what to change
    2. What-if analysis - tests many seat counts and office policies at once,
       so leadership can see the trade-offs before deciding

Outputs:
    roster_v3.csv   - the roster for the current settings (if one is possible)
    scenarios.csv   - results for every what-if scenario
    scenarios.png   - chart of those results
"""
import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")                 # draw charts to a file, no window needed
import matplotlib.pyplot as plt
from scipy.optimize import milp, LinearConstraint, Bounds

# ---------- Current settings ----------
SEATS = 40
MIN_DAYS = 3
MAX_DAYS = 3
TEAM_DAYS = True
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

# ---------- What-if ranges ----------
SEAT_OPTIONS = [30, 35, 40, 45, 50]
POLICY_OPTIONS = [2, 3, 4]            # office days per week, the same for everyone

# ---------- Load the data ----------
employees = pd.read_csv("employees.csv")
people = list(employees["employee_id"])
team_of = list(employees["team"])
teams = sorted(set(team_of))
scores = employees[DAYS].to_numpy()
team_sizes = {t: team_of.count(t) for t in teams}

n_people, n_days, n_teams = len(people), len(DAYS), len(teams)

# ---------- Decisions (same layout as version 2) ----------
def in_office(p, d):
    return p * n_days + d

def team_day(t, d):
    return n_people * n_days + t * n_days + d

FLOOR = n_people * n_days + n_teams * n_days
n_decisions = FLOOR + 1


def build_roster(seats, min_days, max_days, fairness=True, team_days=True):
    """Solve the roster problem. Returns (roster table, satisfaction %) or None."""
    best_possible = np.sort(scores, axis=1)[:, -max_days:].sum(axis=1)
    rules, lowest, highest = [], [], []

    def add_rule(terms, low, high):
        row = np.zeros(n_decisions)
        for position, multiplier in terms:
            row[position] += multiplier
        rules.append(row); lowest.append(low); highest.append(high)

    for d in range(n_days):
        add_rule([(in_office(p, d), 1) for p in range(n_people)], 0, seats)
    for p in range(n_people):
        add_rule([(in_office(p, d), 1) for d in range(n_days)], min_days, max_days)
    if team_days:
        for t in range(n_teams):
            add_rule([(team_day(t, d), 1) for d in range(n_days)], 1, 1)
        for p in range(n_people):
            t = teams.index(team_of[p])
            for d in range(n_days):
                add_rule([(in_office(p, d), 1), (team_day(t, d), -1)], 0, np.inf)
    if fairness:
        for p in range(n_people):
            terms = [(in_office(p, d), scores[p, d]) for d in range(n_days)]
            add_rule(terms + [(FLOOR, -best_possible[p])], 0, np.inf)

    whole_numbers = np.ones(n_decisions)
    whole_numbers[FLOOR] = 0

    def solve(goal):
        return milp(goal, constraints=LinearConstraint(np.array(rules), lowest, highest),
                    integrality=whole_numbers, bounds=Bounds(0, 1))

    if fairness:
        goal = np.zeros(n_decisions); goal[FLOOR] = -1
        stage1 = solve(goal)
        if not stage1.success:
            return None
        add_rule([(FLOOR, 1)], stage1.x[FLOOR] - 1e-6, 1)

    goal = np.zeros(n_decisions)
    for p in range(n_people):
        for d in range(n_days):
            goal[in_office(p, d)] = -scores[p, d]
    result = solve(goal)
    if not result.success:
        return None
    roster = result.x[: n_people * n_days].round().astype(int).reshape(n_people, n_days)
    satisfaction = (roster * scores).sum(axis=1) / best_possible * 100
    return roster, satisfaction


def quick_checks(seats, min_days, max_days, team_days=True):
    """Simple arithmetic checks that explain the most common problems. No solver needed."""
    problems = []
    if min_days > max_days:
        problems.append(f"The minimum office days ({min_days}) is more than the maximum "
                        f"({max_days}). Raise MAX_DAYS to at least {min_days}.")
    needed = n_people * min_days
    available = seats * n_days
    if needed > available:
        seats_needed = math.ceil(needed / n_days)
        problems.append(f"Not enough desks: {n_people} people x {min_days} days = {needed} "
                        f"desk-days needed, but {seats} seats x {n_days} days = {available}. "
                        f"Increase seats to {seats_needed}, or lower the policy to "
                        f"{available // n_people} days.")
    if team_days:
        for t, size in team_sizes.items():
            if size > seats:
                problems.append(f"Team {t} has {size} people but there are only {seats} seats, "
                                f"so it can never be in the office together.")
    return problems


def diagnose(seats, min_days, max_days, team_days=True):
    """Explain why no roster is possible and suggest the smallest fix."""
    problems = quick_checks(seats, min_days, max_days, team_days)
    if problems:
        return problems
    # The simple checks pass, so the conflict comes from rules interacting.
    # Fairness can never cause it (the floor can always drop), so test team days.
    if team_days and build_roster(seats, min_days, max_days, False, False) is not None:
        problems.append("Team days are the blocker: there are enough seats overall, but the "
                        "teams' shared days can't all fit alongside everyone else.")
    for extra in range(1, n_people + 1):
        if build_roster(seats + extra, min_days, max_days, False, team_days) is not None:
            problems.append(f"Adding {extra} seat(s) per day (to {seats + extra}) would make it work.")
            break
    return problems


# ---------- Part 1: the current settings ----------
print(f"Current settings: {SEATS} seats, {MIN_DAYS}-{MAX_DAYS} days per person, "
      f"team days {'on' if TEAM_DAYS else 'off'}\n")
problems = quick_checks(SEATS, MIN_DAYS, MAX_DAYS, TEAM_DAYS)
outcome = None if problems else build_roster(SEATS, MIN_DAYS, MAX_DAYS, True, TEAM_DAYS)

if outcome is None:
    print("No valid roster is possible. Why:")
    for problem in diagnose(SEATS, MIN_DAYS, MAX_DAYS, TEAM_DAYS):
        print(f"  - {problem}")
else:
    roster, satisfaction = outcome
    print(f"Roster found. Average satisfaction {satisfaction.mean():.1f}%, "
          f"lowest {satisfaction.min():.1f}%")
    print("People in office per day:", dict(zip(DAYS, roster.sum(axis=0).tolist())))
    output = pd.DataFrame(roster, index=people, columns=DAYS)
    output.insert(0, "team", team_of)
    output["satisfaction_%"] = satisfaction.round(1)
    output.to_csv("roster_v3.csv", index_label="employee_id")
    print("Saved to roster_v3.csv")

# ---------- Part 2: what-if analysis ----------
print("\nRunning what-if scenarios (this takes a little while)...")
results = []
for policy in POLICY_OPTIONS:
    for seats in SEAT_OPTIONS:
        outcome = None
        if not quick_checks(seats, policy, policy, TEAM_DAYS):
            outcome = build_roster(seats, policy, policy, True, TEAM_DAYS)
        results.append({
            "office_days": policy,
            "seats": seats,
            "possible": outcome is not None,
            "average_satisfaction_%": round(outcome[1].mean(), 1) if outcome else None,
            "lowest_satisfaction_%": round(outcome[1].min(), 1) if outcome else None,
        })
        print(f"  {policy} days, {seats} seats: "
              + (f"avg {results[-1]['average_satisfaction_%']}%, "
                 f"lowest {results[-1]['lowest_satisfaction_%']}%" if outcome else "not possible"))

table = pd.DataFrame(results)
table.to_csv("scenarios.csv", index=False)

# ---------- Chart ----------
fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
for policy in POLICY_OPTIONS:
    rows = table[(table["office_days"] == policy) & table["possible"]]
    left.plot(rows["seats"], rows["average_satisfaction_%"], marker="o", label=f"{policy} days/week")
    right.plot(rows["seats"], rows["lowest_satisfaction_%"], marker="o", label=f"{policy} days/week")
for axis, title in [(left, "Average satisfaction"), (right, "Least-satisfied employee")]:
    axis.set_title(title)
    axis.set_xlabel("Seats available per day")
    axis.set_xticks(SEAT_OPTIONS)
    axis.grid(alpha=0.3)
left.set_ylabel("Satisfaction (%)")
if left.lines:
    left.legend(loc="lower right")
fig.suptitle(f"What-if analysis: {n_people} employees, fairness and team days on "
             f"(missing points = no valid roster)", fontsize=10)
fig.tight_layout()
fig.savefig("scenarios.png", dpi=150)
print("\nSaved scenarios.csv and scenarios.png")
