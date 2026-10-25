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

Built with Python, pandas and SciPy (HiGHS solver). Runs natively on Windows, Intel Macs and Apple-chip Macs.

## How to run

```
pip install -r requirements.txt
python generate_data.py
python roster_v1.py
```

The roster is saved to `roster.csv`. Change `SEATS`, `MIN_DAYS` or `MAX_DAYS` at the top of `roster_v1.py` to test other scenarios.

## Roadmap

- [x] v1: core model (seats, attendance, preferences)
- [ ] v2: fairness (lift the least-satisfied person) and team days (teammates share at least one office day)
- [ ] v3: leave, part-time staff and clear explanations when no roster is possible
- [ ] v4: scenario analysis: what happens if seats drop or the policy changes
- [ ] v5: web app (Streamlit) to upload a CSV and download a roster

All data in this repository is randomly generated.
