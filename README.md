# Work-from-Office Roster Optimizer

Hybrid work creates a scheduling problem: everyone wants to come in midweek, but there are only so many desks. This project builds the best possible weekly office roster using mathematical optimisation (integer linear programming) in Python.

It is a rebuild and extension of my MBA capstone at IIM Tiruchirappalli (Best Industry Project Award, 2023), which was originally built in Excel Solver.

## The problem

Given:
- a list of employees and their teams
- each person's preference for each weekday (1 = dislike, 5 = love)
- the number of desks available
- the company's office-attendance policy (e.g. 3 days a week)

Find the roster that gives people the days they prefer most, without exceeding seat capacity.

## How the model works

| Part | In plain terms |
|---|---|
| Decisions | For every person and every day: in the office (1) or not (0) |
| Rule: seats | People in office on any day ≤ seats available |
| Rule: attendance | Each person comes in between the minimum and maximum days |
| Goal | Maximise the total preference score across everyone |

## Results (v1, sample data: 60 employees, 40 seats, 3 days/week)

- Tuesday to Thursday fill to capacity; the model moves the overflow to Monday and Friday
- Average satisfaction: 93.1% of each person's best possible score
- Half of employees get all three of their favourite days
- But the least-satisfied person gets only 62.5%, which is the fairness problem v2 solves

## Results (v2: fairness and team days)

Version 2 adds two upgrades and compares three scenarios on the same data:

1. **Fairness:** first raise the least-satisfied person's score as high as possible, then maximise everyone's happiness without dropping below that floor (a two-stage, max-min approach).
2. **Team days:** each team gets one shared office day, and every member comes in that day.

| | v1: max happiness | + fairness | + fairness + team days |
|---|---|---|---|
| Average satisfaction | 93.1% | 93.0% | 91.1% |
| Lowest satisfaction | 62.5% | 83.3% | 81.8% |
| Got all favourite days | 30 of 60 | 25 of 60 | 19 of 60 |
| Teams with a shared day | 0 of 5 | 0 of 5 | 5 of 5 |

**What this shows:**
- Fairness lifts the worst-off employee from 62.5% to 83.3% while the average drops by only 0.1 points. The v1 roster was unfair for almost no gain.
- Guaranteeing every team a shared day costs about 2 points of average satisfaction, which leadership can weigh against the value of in-person collaboration.

## Results (v3: diagnosis and what-if analysis)

**Diagnosis.** When the rules conflict, the model explains why in plain English and suggests the smallest fix, instead of just failing. For example, with 35 seats and a 3-day policy:

```
No valid roster is possible. Why:
  - Not enough desks: 60 people x 3 days = 180 desk-days needed, but 35 seats x 5 days = 175.
    Increase seats to 36, or lower the policy to 2 days.
```

It first runs quick arithmetic checks (seat capacity, contradictory rules, teams larger than the office). If those pass but the solver still finds no roster, it tests whether team days are the blocker and searches for the smallest number of extra seats that would make a roster possible.

**What-if analysis.** The model tests 15 combinations of seat count and office policy in about 10 seconds, with fairness and team days on:

![What-if analysis chart](scenarios.png)

**What this shows:**
- A 3-day policy needs at least 36 seats for 60 people; a 4-day policy needs 48.
- At 40 seats, moving from a 2-day to a 3-day policy costs about 6 points of average satisfaction (97.3% to 91.1%).
- Under a 3-day policy, adding 5 seats (40 to 45) raises the average from 91.1% to 96.0% and the least-satisfied employee from 81.8% to 85.7%.
- Under a 2-day policy, the least-satisfied employee stays at 80% beyond 40 seats, so extra desks stop helping.

Built with Python, pandas and SciPy (HiGHS solver). Runs natively on Windows, Intel Macs and Apple-chip Macs.

## How to run

```
pip install -r requirements.txt
python generate_data.py
python roster_v1.py
python roster_v2.py
python roster_v3.py
```

Rosters are saved to `roster.csv` (v1), `roster_v2.csv` (v2) and `roster_v3.csv` (v3). Version 3 also saves `scenarios.csv` and `scenarios.png`. Change `SEATS`, `MIN_DAYS` or `MAX_DAYS` at the top of `roster_v1.py` to test other scenarios.

## Roadmap

- [x] v1: core model (seats, attendance, preferences)
- [x] v2: fairness (lift the least-satisfied person) and team days (teammates share at least one office day)
- [x] v3: plain-English diagnosis when no roster is possible, and what-if analysis across seat counts and policies
- [ ] v4: leave, part-time staff and individual unavailable days
- [ ] v5: web app (Streamlit) to upload a CSV and download a roster

All data in this repository is randomly generated.
