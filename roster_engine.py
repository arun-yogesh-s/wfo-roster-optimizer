"""
Roster engine: the version 4 model, packaged so other programs can use it.

roster_v4.py is a script you run from the terminal. This file holds the same
model as reusable functions, so the web app (app.py) can call it with uploaded
data and settings chosen on screen. Two upgrades for real-world data:
    - Input checks with plain-English messages (wrong columns, bad scores, typos)
    - Sparse rule tables and a time limit, so it handles hundreds of employees
"""
import math
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import csr_array

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
STATUSES = ["available", "off", "leave", "unavailable"]
LABELS = {"available": "Home", "off": "Off", "leave": "Leave", "unavailable": "Unavailable"}
TIME_LIMIT_SECONDS = 30      # per solve; the best roster found so far is used after this


# ======================================================================
# 1. Checking and preparing the data
# ======================================================================
def check_inputs(employees, availability=None):
    """Return (errors, warnings). Errors stop the roster; warnings are fixed automatically."""
    errors, warnings = [], []

    needed = ["employee_id", "team"] + DAYS
    missing = [c for c in needed if c not in employees.columns]
    if missing:
        errors.append(f"The employees file is missing these columns: {', '.join(missing)}. "
                      f"It needs: {', '.join(needed)}.")
        return errors, warnings
    if employees.empty:
        errors.append("The employees file has no rows.")
        return errors, warnings

    ids = employees["employee_id"].astype(str).str.strip()
    duplicates = sorted(set(ids[ids.duplicated()]))
    if duplicates:
        errors.append(f"These employee IDs appear more than once: {', '.join(duplicates[:10])}.")
    if employees["team"].isna().any():
        errors.append("Some employees have no team. Fill in the team column for every row.")

    scores = employees[DAYS].apply(pd.to_numeric, errors="coerce")
    bad = scores.isna() | (scores < 1) | (scores > 5)
    if bad.any().any():
        rows = list(ids[bad.any(axis=1)][:10])
        errors.append(f"Day preferences must be numbers from 1 to 5. Check: {', '.join(rows)}.")

    if availability is not None:
        missing = [c for c in ["employee_id"] + DAYS if c not in availability.columns]
        if missing:
            errors.append(f"The availability file is missing these columns: {', '.join(missing)}.")
            return errors, warnings
        values = availability[DAYS].astype(str).apply(lambda col: col.str.strip().str.lower())
        unknown = sorted(set(values.to_numpy().ravel()) - set(STATUSES))
        if unknown:
            errors.append(f"Availability values must be one of {', '.join(STATUSES)}. "
                          f"Found: {', '.join(unknown[:10])}.")
        avail_ids = set(availability["employee_id"].astype(str).str.strip())
        not_listed = sorted(set(ids) - avail_ids)
        extra = sorted(avail_ids - set(ids))
        if not_listed:
            warnings.append(f"{len(not_listed)} employee(s) are not in the availability file, "
                            f"so they are treated as full-time and available all week "
                            f"(e.g. {', '.join(not_listed[:5])}).")
        if extra:
            warnings.append(f"{len(extra)} ID(s) in the availability file are not in the employees "
                            f"file and were ignored (e.g. {', '.join(extra[:5])}).")
    return errors, warnings


def prepare(employees, availability=None):
    """Tidy both tables into the shape the model needs. Run check_inputs first."""
    employees = employees.copy()
    employees["employee_id"] = employees["employee_id"].astype(str).str.strip()
    employees["team"] = employees["team"].astype(str).str.strip()
    employees[DAYS] = employees[DAYS].apply(pd.to_numeric).round().astype(int)

    table = pd.DataFrame({"employee_id": employees["employee_id"], "contract": "full-time"})
    for d in DAYS:
        table[d] = "available"
    table = table.set_index("employee_id")
    if availability is not None:
        given = availability.copy()
        given["employee_id"] = given["employee_id"].astype(str).str.strip()
        given = given.drop_duplicates("employee_id").set_index("employee_id")
        given = given[given.index.isin(table.index)]
        for d in DAYS:
            table.loc[given.index, d] = given[d].astype(str).str.strip().str.lower()
        if "contract" in given.columns:
            table.loc[given.index, "contract"] = given["contract"].fillna("full-time").astype(str)
    return employees.reset_index(drop=True), table.loc[employees["employee_id"]]


def office_targets(status, policy_days):
    """Office days each person needs this week, pro-rata to the days they work."""
    days_worked = ((status != "off") & (status != "leave")).sum(axis=1)
    return np.array([int(math.floor(policy_days * w / len(DAYS) + 0.5)) for w in days_worked])


# ======================================================================
# 2. The model
# ======================================================================
class _Rules:
    """Collects rules as a sparse table: only the non-zero entries are stored."""
    def __init__(self):
        self.rows, self.cols, self.vals, self.lowest, self.highest = [], [], [], [], []

    def add(self, terms, low, high):
        r = len(self.lowest)
        for col, val in terms:
            self.rows.append(r); self.cols.append(col); self.vals.append(val)
        self.lowest.append(low); self.highest.append(high)

    def constraint(self, n_decisions):
        matrix = csr_array((self.vals, (self.rows, self.cols)),
                           shape=(len(self.lowest), n_decisions))
        return LinearConstraint(matrix, self.lowest, self.highest)


def solve_roster(scores, team_of, allowed, targets, seats,
                 team_days=True, team_share=0.75, fairness=True):
    """
    Build the best roster. Returns a dict, or None if no roster is possible.
      scores   person x day preference (1-5)
      team_of  team name per person
      allowed  person x day True/False (can this person attend this day?)
      targets  office days required per person
    """
    n_people, n_days = scores.shape
    teams = sorted(set(team_of))
    members = {t: [p for p in range(n_people) if team_of[p] == t] for t in teams}
    n_teams = len(teams)

    def x(p, d):        # person p in office on day d
        return p * n_days + d

    def y(t, d):        # day d is team t's shared day
        return n_people * n_days + t * n_days + d

    FLOOR = n_people * n_days + n_teams * n_days
    n_decisions = FLOOR + 1

    best_possible = np.array([np.sort(scores[p][allowed[p]])[::-1][: targets[p]].sum()
                              for p in range(n_people)], dtype=float)
    counted = (targets > 0) & (best_possible > 0)

    rules = _Rules()
    upper = np.ones(n_decisions)
    upper[: n_people * n_days] = allowed.ravel().astype(float)

    for d in range(n_days):
        rules.add([(x(p, d), 1) for p in range(n_people)], 0, seats)
    for p in range(n_people):
        rules.add([(x(p, d), 1) for d in range(n_days)], targets[p], targets[p])

    for t_index, t in enumerate(teams):
        ok_days = eligible_team_days(members[t], allowed, targets, seats, team_share)
        for d in range(n_days):
            if not team_days or d not in ok_days:
                upper[y(t_index, d)] = 0
        if team_days:
            rules.add([(y(t_index, d), 1) for d in range(n_days)], 1, 1)
            for p in members[t]:
                for d in range(n_days):
                    if allowed[p, d] and targets[p] > 0:
                        rules.add([(x(p, d), 1), (y(t_index, d), -1)], 0, np.inf)

    if fairness:
        for p in np.flatnonzero(counted):
            terms = [(x(p, d), scores[p, d]) for d in range(n_days)]
            rules.add(terms + [(FLOOR, -best_possible[p])], 0, np.inf)

    whole_numbers = np.ones(n_decisions)
    whole_numbers[FLOOR] = 0
    limits = Bounds(np.zeros(n_decisions), upper)
    timed_out = False

    def solve(goal):
        nonlocal timed_out
        result = milp(goal, constraints=rules.constraint(n_decisions), integrality=whole_numbers,
                      bounds=limits, options={"time_limit": TIME_LIMIT_SECONDS})
        if result.status == 1 and result.x is not None:     # time limit, but a roster was found
            timed_out = True
            return result
        return result if result.success else None

    if fairness:
        goal = np.zeros(n_decisions); goal[FLOOR] = -1
        stage1 = solve(goal)
        if stage1 is None:
            return None
        rules.add([(FLOOR, 1)], stage1.x[FLOOR] - 1e-6, 1)

    goal = np.zeros(n_decisions)
    goal[: n_people * n_days] = -scores.ravel()
    result = solve(goal)
    if result is None:
        return None

    roster = result.x[: n_people * n_days].round().astype(int).reshape(n_people, n_days)
    satisfaction = np.full(n_people, np.nan)
    achieved = (roster * scores).sum(axis=1)
    satisfaction[counted] = achieved[counted] / best_possible[counted] * 100

    shared_days = {}
    if team_days:
        for t in teams:
            for d in range(n_days):
                present = [p for p in members[t] if roster[p, d]]
                away = [p for p in members[t] if not allowed[p, d] or targets[p] == 0]
                if present and len(present) + len(away) == len(members[t]):
                    shared_days[t] = (d, len(present), len(away))
                    break
    return {"roster": roster, "satisfaction": satisfaction,
            "shared_days": shared_days, "timed_out": timed_out}


def eligible_team_days(team_members, allowed, targets, seats, team_share):
    """Days a team could use as its shared day (people away all week don't count)."""
    working = [p for p in team_members if targets[p] > 0]
    days = []
    for d in range(allowed.shape[1]):
        present = sum(allowed[p, d] for p in working)
        if working and present >= team_share * len(working) and present <= seats:
            days.append(d)
    return days


# ======================================================================
# 3. Explaining problems
# ======================================================================
def quick_checks(ids, team_of, allowed, targets, seats, team_days, team_share):
    problems = []
    for p, pid in enumerate(ids):
        free = [DAYS[d] for d in range(len(DAYS)) if allowed[p, d]]
        if targets[p] > len(free):
            problems.append(f"{pid} must come in {targets[p]} days but can only attend "
                            f"{len(free)} ({', '.join(free) or 'none'}).")
    needed, available = int(targets.sum()), seats * len(DAYS)
    if needed > available:
        problems.append(f"Not enough desks: {needed} desk-days are needed this week but "
                        f"{seats} seats × {len(DAYS)} days = {available}. "
                        f"You need at least {math.ceil(needed / len(DAYS))} seats.")
    if team_days:
        for t in sorted(set(team_of)):
            team_members = [p for p in range(len(ids)) if team_of[p] == t]
            if not eligible_team_days(team_members, allowed, targets, seats, team_share):
                working = sum(targets[p] > 0 for p in team_members)
                problems.append(f"Team {t} has no day when at least {team_share:.0%} of its "
                                f"{working} working members are available (and fit in the office).")
    return problems


def diagnose(scores, ids, team_of, allowed, targets, seats, team_days, team_share):
    problems = quick_checks(ids, team_of, allowed, targets, seats, team_days, team_share)
    if problems:
        return problems
    if team_days and solve_roster(scores, team_of, allowed, targets, seats,
                                  False, team_share, False) is not None:
        problems.append("Team days are the blocker: there are enough seats overall, "
                        "but the teams' shared days can't all fit this week.")
    for extra in range(1, len(ids) + 1):
        if solve_roster(scores, team_of, allowed, targets, seats + extra,
                        team_days, team_share, False) is not None:
            problems.append(f"Adding {extra} seat(s) per day (to {seats + extra}) would make it work.")
            break
    return problems or ["Too many people can only attend on the same few days."]


# ======================================================================
# 4. One call that does everything (used by the web app)
# ======================================================================
def plan_week(employees, status_table, seats, policy_days,
              team_days=True, team_share=0.75, compare_naive=True):
    """Prepared tables + settings -> everything the app needs to show."""
    ids = list(employees["employee_id"])
    team_of = list(employees["team"])
    scores = employees[DAYS].to_numpy()
    status = status_table[DAYS].to_numpy()
    allowed = status == "available"
    targets = office_targets(status, policy_days)

    out = {"targets": targets, "problems": None, "naive_clashes": None}

    problems = quick_checks(ids, team_of, allowed, targets, seats, team_days, team_share)
    solved = None if problems else solve_roster(scores, team_of, allowed, targets, seats,
                                                team_days, team_share)
    if solved is None:
        out["problems"] = problems or diagnose(scores, ids, team_of, allowed, targets,
                                               seats, team_days, team_share)
        return out

    roster, satisfaction = solved["roster"], solved["satisfaction"]
    labelled = pd.DataFrame(
        [["Office" if roster[p, d] else LABELS[status[p, d]] for d in range(len(DAYS))]
         for p in range(len(ids))], columns=DAYS)
    labelled.insert(0, "employee_id", ids)
    labelled.insert(1, "team", team_of)
    labelled.insert(2, "contract", status_table["contract"].to_numpy())
    labelled.insert(3, "office_days", targets)
    labelled["satisfaction_%"] = np.round(satisfaction, 1)

    out.update({
        "roster": labelled,
        "per_day": pd.Series(roster.sum(axis=0), index=DAYS),
        "average": float(np.nanmean(satisfaction)) if np.isfinite(satisfaction).any() else None,
        "lowest": float(np.nanmin(satisfaction)) if np.isfinite(satisfaction).any() else None,
        "desks_freed": int(len(ids) * policy_days - targets.sum()),
        "shared_days": {t: (DAYS[d], n_in, n_away)
                        for t, (d, n_in, n_away) in solved["shared_days"].items()},
        "timed_out": solved["timed_out"],
    })

    if compare_naive and (status != "available").any():
        everyone = np.ones_like(allowed)
        naive = solve_roster(scores, team_of, everyone, np.full(len(ids), policy_days), seats,
                             team_days, team_share)
        if naive is not None:
            booked = naive["roster"] == 1
            out["naive_clashes"] = {kind: int((booked & (status == kind)).sum())
                                    for kind in ["leave", "off", "unavailable"]}
    return out
