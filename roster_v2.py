"""
Version 2: a fairer roster that keeps teams together.

Version 1 maximised total happiness, but some people paid for it:
the least-satisfied person got only about 60% of their best possible score.

Version 2 adds two upgrades:
    1. Fairness  - first lift the least-satisfied person as high as possible,
                   then maximise everyone's happiness without dropping below that floor
    2. Team days - each team gets one shared office day, and all members come in that day

It runs three scenarios and prints a comparison, so you can see what each upgrade costs
and what it buys.
"""
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds

# ---------- Settings ----------
SEATS = 40
MIN_DAYS = 3
MAX_DAYS = 3
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

# ---------- Load the data ----------
employees = pd.read_csv("employees.csv")
people = list(employees["employee_id"])
team_of = list(employees["team"])
teams = sorted(set(team_of))
preference = employees.set_index("employee_id")[DAYS]
scores = preference.to_numpy()

# each person's best possible score = their top MAX_DAYS days added up
best_possible = np.sort(scores, axis=1)[:, -MAX_DAYS:].sum(axis=1)

n_people, n_days, n_teams = len(people), len(DAYS), len(teams)

# ---------- Decisions ----------
# All decisions sit in one long list. These helpers say where each one is:
#   in_office(p, d)  - person p comes in on day d               (yes/no)
#   team_day(t, d)   - day d is team t's shared office day       (yes/no)
#   FLOOR            - satisfaction of the least-satisfied person (0 to 1)
def in_office(p, d):
    return p * n_days + d

def team_day(t, d):
    return n_people * n_days + t * n_days + d

FLOOR = n_people * n_days + n_teams * n_days
n_decisions = FLOOR + 1


def build_roster(fairness, team_days):
    """Solve the roster problem with or without each upgrade. Returns a 0/1 table or None."""
    rules, lowest, highest = [], [], []

    def add_rule(terms, low, high):
        # terms is a list of (decision position, multiplier) pairs
        row = np.zeros(n_decisions)
        for position, multiplier in terms:
            row[position] += multiplier
        rules.append(row); lowest.append(low); highest.append(high)

    # Rule: seats per day
    for d in range(n_days):
        add_rule([(in_office(p, d), 1) for p in range(n_people)], 0, SEATS)

    # Rule: office days per person
    for p in range(n_people):
        add_rule([(in_office(p, d), 1) for d in range(n_days)], MIN_DAYS, MAX_DAYS)

    if team_days:
        # Rule: each team picks exactly one shared day
        for t in range(n_teams):
            add_rule([(team_day(t, d), 1) for d in range(n_days)], 1, 1)
        # Rule: if it's your team's day, you're in (in_office - team_day >= 0)
        for p in range(n_people):
            t = teams.index(team_of[p])
            for d in range(n_days):
                add_rule([(in_office(p, d), 1), (team_day(t, d), -1)], 0, np.inf)

    if fairness:
        # Rule: everyone's score is at least FLOOR x their best possible score
        for p in range(n_people):
            terms = [(in_office(p, d), scores[p, d]) for d in range(n_days)]
            add_rule(terms + [(FLOOR, -best_possible[p])], 0, np.inf)

    whole_numbers = np.ones(n_decisions)
    whole_numbers[FLOOR] = 0          # FLOOR is a fraction, everything else is yes/no
    limits = Bounds(0, 1)

    def solve(goal):
        return milp(goal, constraints=LinearConstraint(np.array(rules), lowest, highest),
                    integrality=whole_numbers, bounds=limits)

    if fairness:
        # Stage 1: push the floor as high as possible (SciPy minimises, so use -1)
        goal = np.zeros(n_decisions); goal[FLOOR] = -1
        stage1 = solve(goal)
        if not stage1.success:
            return None
        # Stage 2: lock that floor in before maximising total happiness
        add_rule([(FLOOR, 1)], stage1.x[FLOOR] - 1e-6, 1)

    # Goal: maximise total preference score
    goal = np.zeros(n_decisions)
    for p in range(n_people):
        for d in range(n_days):
            goal[in_office(p, d)] = -scores[p, d]
    result = solve(goal)
    if not result.success:
        return None
    return result.x[: n_people * n_days].round().astype(int).reshape(n_people, n_days)


def summarise(roster):
    satisfaction = (roster * scores).sum(axis=1) / best_possible * 100
    teams_together = 0
    for t in teams:
        members = [p for p in range(n_people) if team_of[p] == t]
        if any(roster[members, d].all() for d in range(n_days)):
            teams_together += 1
    return {
        "Average satisfaction": f"{satisfaction.mean():.1f}%",
        "Lowest satisfaction": f"{satisfaction.min():.1f}%",
        "Got all favourite days": f"{(satisfaction >= 99.99).sum()} of {n_people}",
        "Teams with a shared day": f"{teams_together} of {n_teams}",
    }, satisfaction


# ---------- Run the three scenarios ----------
scenarios = {
    "v1: max happiness": (False, False),
    "+ fairness": (True, False),
    "+ fairness + team days": (True, True),
}
comparison = {}
for name, (fairness, team_days) in scenarios.items():
    roster = build_roster(fairness, team_days)
    if roster is None:
        print(f"{name}: no valid roster with these settings.")
        raise SystemExit
    comparison[name], satisfaction = summarise(roster)
    final_roster = roster

print(pd.DataFrame(comparison).to_string())

# ---------- Save the final roster (fairness + team days) ----------
output = pd.DataFrame(final_roster, index=people, columns=DAYS)
output.insert(0, "team", team_of)
output["satisfaction_%"] = satisfaction.round(1)
output.to_csv("roster_v2.csv", index_label="employee_id")

print("\nShared team days:")
for t in teams:
    members = [p for p in range(n_people) if team_of[p] == t]
    shared = [DAYS[d] for d in range(n_days) if final_roster[members, d].all()]
    print(f"  {t:<10} {', '.join(shared)}  ({len(members)} people)")
print("\nPeople in office per day:", dict(zip(DAYS, final_roster.sum(axis=0).tolist())))
print("Full roster saved to roster_v2.csv")
