"""
Version 4: real weeks - leave, part-time staff and days people can't come in.

Versions 1-3 assumed everyone could come in any day. Version 4 reads
availability.csv and adds:
    1. Blocked days   - nobody is rostered on a day they're off, on leave or unavailable
    2. Pro-rata targets - office days scale with days actually worked this week
                          (a part-timer working 3 days under a 3-day policy comes in 2 days)
    3. Smarter team days - a team's shared day must be one most of the team can attend;
                           members who are away that day are excused
    4. Diagnosis      - names the specific person or team that makes a roster impossible

It also shows what would have gone wrong if the roster ignored availability.
"""
import math
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds

# ---------- Settings ----------
SEATS = 40
POLICY_DAYS = 3              # office days per week for a full-time person with no leave
TEAM_DAYS = True
TEAM_DAY_MIN_SHARE = 0.75    # a team day needs at least 75% of the team available
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

# ---------- Load the data ----------
employees = pd.read_csv("employees.csv")
availability = pd.read_csv("availability.csv").set_index("employee_id")
people = list(employees["employee_id"])
team_of = list(employees["team"])
teams = sorted(set(team_of))
scores = employees[DAYS].to_numpy()
status = availability.loc[people, DAYS].to_numpy()        # person x day -> "available", "leave", ...

n_people, n_days, n_teams = len(people), len(DAYS), len(teams)
members = {t: [p for p in range(n_people) if team_of[p] == t] for t in teams}


# ---------- Office-day targets ----------
def round_half_up(x):
    return int(math.floor(x + 0.5))

# Days actually worked this week = not "off" and not "leave".
# "unavailable" days are still working days, so they don't reduce the target.
days_worked = ((status != "off") & (status != "leave")).sum(axis=1)
target = np.array([round_half_up(POLICY_DAYS * w / n_days) for w in days_worked])
can_attend = status == "available"                          # person x day -> True/False


# ---------- Decisions (same layout as before) ----------
def in_office(p, d):
    return p * n_days + d

def team_day(t, d):
    return n_people * n_days + t * n_days + d

FLOOR = n_people * n_days + n_teams * n_days
n_decisions = FLOOR + 1


def eligible_team_days(t, allowed, seats, targets):
    """Days team t could use as its shared day (people away all week don't count)."""
    working = [p for p in members[t] if targets[p] > 0]
    days = []
    for d in range(n_days):
        present = sum(allowed[p, d] for p in working)
        if working and present >= TEAM_DAY_MIN_SHARE * len(working) and present <= seats:
            days.append(d)
    return days


def build_roster(seats, targets, allowed, fairness=True, team_days=True):
    """Solve the roster problem. Returns (roster table, satisfaction %) or None."""
    # each person's best possible score = their favourite days among the days they can attend
    best_possible = np.array([
        np.sort(scores[p][allowed[p]])[::-1][: targets[p]].sum() for p in range(n_people)
    ])
    counted = targets > 0          # people away all week are left out of satisfaction

    rules, lowest, highest = [], [], []

    def add_rule(terms, low, high):
        row = np.zeros(n_decisions)
        for position, multiplier in terms:
            row[position] += multiplier
        rules.append(row); lowest.append(low); highest.append(high)

    # Upper limits: a blocked day can't be chosen; a team day only on an eligible day
    upper = np.ones(n_decisions)
    for p in range(n_people):
        for d in range(n_days):
            if not allowed[p, d]:
                upper[in_office(p, d)] = 0

    for d in range(n_days):
        add_rule([(in_office(p, d), 1) for p in range(n_people)], 0, seats)
    for p in range(n_people):
        add_rule([(in_office(p, d), 1) for d in range(n_days)], targets[p], targets[p])

    if team_days:
        for t_index, t in enumerate(teams):
            ok_days = eligible_team_days(t, allowed, seats, targets)
            for d in range(n_days):
                if d not in ok_days:
                    upper[team_day(t_index, d)] = 0
            add_rule([(team_day(t_index, d), 1) for d in range(n_days)], 1, 1)
            for p in members[t]:
                for d in range(n_days):
                    if allowed[p, d] and targets[p] > 0:
                        # if it's your team's day and you're around, you come in
                        add_rule([(in_office(p, d), 1), (team_day(t_index, d), -1)], 0, np.inf)
    else:
        for t_index in range(n_teams):
            for d in range(n_days):
                upper[team_day(t_index, d)] = 0

    if fairness:
        for p in range(n_people):
            if counted[p]:
                terms = [(in_office(p, d), scores[p, d]) for d in range(n_days)]
                add_rule(terms + [(FLOOR, -best_possible[p])], 0, np.inf)

    whole_numbers = np.ones(n_decisions)
    whole_numbers[FLOOR] = 0
    limits = Bounds(np.zeros(n_decisions), upper)

    def solve(goal):
        return milp(goal, constraints=LinearConstraint(np.array(rules), lowest, highest),
                    integrality=whole_numbers, bounds=limits)

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
    satisfaction = np.full(n_people, np.nan)
    satisfaction[counted] = (roster * scores).sum(axis=1)[counted] / best_possible[counted] * 100
    return roster, satisfaction


def quick_checks(seats, targets, allowed, team_days=True):
    """Arithmetic checks that name the person or team causing a problem."""
    problems = []
    for p in range(n_people):
        free = [DAYS[d] for d in range(n_days) if allowed[p, d]]
        if targets[p] > len(free):
            problems.append(f"{people[p]} must come in {targets[p]} days but can only attend "
                            f"{len(free)} ({', '.join(free) or 'none'}). Excuse them from "
                            f"one day or change an 'unavailable' day.")
    needed, available = int(targets.sum()), seats * n_days
    if needed > available:
        problems.append(f"Not enough desks: {needed} desk-days needed this week but only "
                        f"{available} available. Increase seats to {math.ceil(needed / n_days)}.")
    if team_days:
        for t in teams:
            if not eligible_team_days(t, allowed, seats, targets):
                working = sum(targets[p] > 0 for p in members[t])
                problems.append(f"Team {t} has no day when at least {TEAM_DAY_MIN_SHARE:.0%} "
                                f"of its {working} working members are available. Lower "
                                f"TEAM_DAY_MIN_SHARE or skip team days this week.")
    return problems


def diagnose(seats, targets, allowed, team_days=True):
    problems = quick_checks(seats, targets, allowed, team_days)
    if problems:
        return problems
    if team_days and build_roster(seats, targets, allowed, False, False) is not None:
        problems.append("Team days are the blocker: there are enough seats overall, but the "
                        "teams' shared days can't all fit this week.")
    for extra in range(1, n_people + 1):
        if build_roster(seats + extra, targets, allowed, False, team_days) is not None:
            problems.append(f"Adding {extra} seat(s) per day (to {seats + extra}) would make it work.")
            break
    if len(problems) == 0:
        problems.append("Too many people can only attend on the same few days. "
                        "Check availability.csv for clashes.")
    return problems


# ---------- Part 1: what goes wrong if availability is ignored ----------
everyone_allowed = np.ones((n_people, n_days), dtype=bool)
naive = build_roster(SEATS, np.full(n_people, POLICY_DAYS), everyone_allowed, True, TEAM_DAYS)
if naive is not None:
    naive_roster = naive[0]
    clashes = {kind: int(((naive_roster == 1) & (status == kind)).sum())
               for kind in ["leave", "off", "unavailable"]}
    print("If the roster ignored availability (version 3), it would book:")
    def desk_days(n):
        return f"{n} desk-day{'s' if n != 1 else ''}"
    print(f"  {desk_days(clashes['leave'])} for people on leave")
    print(f"  {desk_days(clashes['off'])} for part-timers on their day off")
    print(f"  {desk_days(clashes['unavailable'])} for people who said they can't come in")
    print(f"  = {sum(clashes.values())} desks booked for people who won't turn up\n")

# ---------- Part 2: the real roster ----------
print(f"This week: {SEATS} seats, {POLICY_DAYS}-day policy (pro-rata), "
      f"team days {'on' if TEAM_DAYS else 'off'}")
print(f"  {int((availability['contract'] == 'part-time').sum())} part-time, "
      f"{int((status == 'leave').any(axis=1).sum())} taking leave, "
      f"{int((target == 0).sum())} away all week\n")

outcome = None
if not quick_checks(SEATS, target, can_attend, TEAM_DAYS):
    outcome = build_roster(SEATS, target, can_attend, True, TEAM_DAYS)

if outcome is None:
    print("No valid roster is possible. Why:")
    for problem in diagnose(SEATS, target, can_attend, TEAM_DAYS):
        print(f"  - {problem}")
    raise SystemExit

roster, satisfaction = outcome
print(f"Roster found. Average satisfaction {np.nanmean(satisfaction):.1f}%, "
      f"lowest {np.nanmin(satisfaction):.1f}%")
print("People in office per day:", dict(zip(DAYS, roster.sum(axis=0).tolist())))

if TEAM_DAYS:
    print("\nShared team days:")
    for t in teams:
        for d in range(n_days):
            team_present = [p for p in members[t] if roster[p, d]]
            excused = [p for p in members[t] if not can_attend[p, d] or target[p] == 0]
            if len(team_present) + len(excused) == len(members[t]) and team_present:
                note = f", {len(excused)} away" if excused else ""
                print(f"  {t:<10} {DAYS[d]}  ({len(team_present)} of {len(members[t])} in{note})")
                break

# ---------- Save a readable roster ----------
labels = {"available": "Home", "off": "Off", "leave": "Leave", "unavailable": "Unavailable"}
table = pd.DataFrame(
    [["Office" if roster[p, d] else labels[status[p, d]] for d in range(n_days)]
     for p in range(n_people)],
    index=people, columns=DAYS,
)
table.insert(0, "team", team_of)
table.insert(1, "contract", availability.loc[people, "contract"].to_numpy())
table.insert(2, "office_days_target", target)
table["satisfaction_%"] = np.round(satisfaction, 1)
table.to_csv("roster_v4.csv", index_label="employee_id")
print("\nFull roster saved to roster_v4.csv")
