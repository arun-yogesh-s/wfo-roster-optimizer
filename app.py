"""
Version 5: a web app for the roster optimiser.

Anyone can open it in a browser, try it on sample data or upload their own
spreadsheets, adjust the settings, and download the roster. All the maths
lives in roster_engine.py; this file only builds the screens.

Run it on your computer with:   streamlit run app.py
"""
import altair as alt
import pandas as pd
import streamlit as st

import roster_engine as engine

DAYS = engine.DAYS
REPO_URL = "https://github.com/arun-yogesh-s/wfo-roster-optimizer"

st.set_page_config(page_title="WFO Roster Optimiser", layout="wide")


# ---------- Helpers ----------
@st.cache_data(show_spinner=False)
def load_sample():
    return (pd.read_csv("sample_data/sample_employees.csv"),
            pd.read_csv("sample_data/sample_availability.csv"))


@st.cache_data(show_spinner=False)
def run_model(employees, status_table, seats, policy_days, team_days, team_share, compare,
              flag_exceptions):
    # cached: the same inputs and settings never get solved twice
    return engine.plan_week(employees, status_table, seats, policy_days,
                            team_days, team_share, compare, flag_exceptions)


def template(columns, rows):
    return pd.DataFrame(rows, columns=columns).to_csv(index=False).encode()


EMPLOYEE_TEMPLATE = template(["employee_id", "team"] + DAYS,
                             [["E001", "Design", 1, 4, 5, 3, 1], ["E002", "PMO", 3, 2, 5, 5, 1]])
AVAILABILITY_TEMPLATE = template(["employee_id", "contract"] + DAYS,
                                 [["E001", "full-time", "available", "available", "leave", "leave", "available"],
                                  ["E002", "part-time", "off", "available", "available", "unavailable", "off"]])

CELL_COLOURS = {
    "Office": "background-color: #DCEBFA; color: #0B3D6B; font-weight: 600",
    "Leave": "background-color: #F1E3D3; color: #6B3E0B",
    "Off": "background-color: #EDEDED; color: #555555",
    "Unavailable": "background-color: #EDEDED; color: #555555",
    engine.EXCEPTION: "background-color: #F9D6D5; color: #8A1C17; font-weight: 700",
}


# ---------- Sidebar: data and settings ----------
with st.sidebar:
    st.header("1. Data")
    source = st.radio("Choose data", ["Sample data (60 employees)", "Upload my own"],
                      label_visibility="collapsed")
    if source == "Upload my own":
        emp_file = st.file_uploader("Employees and day preferences (CSV)", type="csv")
        avail_file = st.file_uploader("This week's availability (CSV, optional)", type="csv")
        st.download_button("Download employees template", EMPLOYEE_TEMPLATE,
                           "employees_template.csv", "text/csv")
        st.download_button("Download availability template", AVAILABILITY_TEMPLATE,
                           "availability_template.csv", "text/csv")
        with st.expander("File format"):
            st.markdown(
                "**Employees:** `employee_id`, `team`, then `Mon`–`Fri` with a preference "
                "from 1 (dislike) to 5 (love).\n\n"
                "**Availability (optional):** `employee_id`, `contract`, then `Mon`–`Fri` "
                "marked `available`, `off` (part-time), `leave` or `unavailable`. "
                "Anyone left out is treated as available all week.\n\n"
                "In Excel, use **File → Save As → CSV**."
            )

    st.header("2. Settings")
    seats = st.number_input("Seats available per day", min_value=1, max_value=5000, value=40, step=1)
    policy_days = st.slider("Office days per week (full-time)", 1, 5, 3,
                            help="Part-timers and people on leave get a pro-rata target.")
    team_days = st.toggle("Give each team a shared office day", value=True)
    team_share = st.slider("Team day needs this share of the team available", 50, 100, 75, step=5,
                           format="%d%%", disabled=not team_days) / 100
    flag_exceptions = st.toggle(
        "Flag individual exceptions instead of stopping", value=True,
        help="If someone's unavailable days stop them meeting the policy, roster them on every "
             "day they can attend and flag the gap as 'Exception needed', so they can request "
             "an exception from their supervisor.")
    compare = st.toggle("Compare with a roster that ignores availability", value=True,
                        help="Doubles the solving time. Switch off for very large teams.")

# ---------- Header ----------
st.title("Work-from-Office Roster Optimiser")
st.markdown(
    "Builds the fairest weekly office roster that fits your desks, your attendance policy "
    "and everyone's preferences, leave and part-time days. "
    f"[How it works]({REPO_URL})"
)

# ---------- Load and check the data ----------
if source == "Upload my own":
    if emp_file is None:
        st.info("Upload an employees file in the sidebar to start, or switch to the sample data. "
                "Templates are in the sidebar.")
        st.stop()
    try:
        raw_employees = pd.read_csv(emp_file)
        raw_availability = pd.read_csv(avail_file) if avail_file is not None else None
    except Exception:
        st.error("That file couldn't be read as a CSV. In Excel, use File → Save As → CSV.")
        st.stop()
else:
    raw_employees, raw_availability = load_sample()

errors, warnings = engine.check_inputs(raw_employees, raw_availability)
for message in errors:
    st.error(message)
if errors:
    st.stop()
for message in warnings:
    st.warning(message)

employees, status_table = engine.prepare(raw_employees, raw_availability)
n_people = len(employees)

if n_people > 300:
    st.caption(f"{n_people} employees: solving may take up to a minute or two.")

with st.spinner("Building the best roster..."):
    result = run_model(employees, status_table, int(seats), policy_days,
                       team_days, team_share, compare, flag_exceptions)

# ---------- No roster possible ----------
if result["problems"]:
    st.error("No valid roster is possible with these settings.")
    st.markdown("**Why, and what to change:**")
    for problem in result["problems"]:
        st.markdown(f"- {problem}")
    st.stop()

if result["timed_out"]:
    st.warning("This is the best roster found within the time limit. It meets every rule, "
               "but a slightly better one may exist.")

shortfalls = result["shortfalls"]
if shortfalls:
    st.warning(
        f"**{len(shortfalls)} employee(s) can't meet the {policy_days}-day policy this week** "
        f"because of days they've marked unavailable. They're rostered on every day they can "
        f"attend, and the gap is flagged **{engine.EXCEPTION}** so they can request an "
        f"exception from their supervisor."
    )
    with st.expander("Who needs an exception"):
        st.dataframe(pd.DataFrame([
            {"Employee": s["employee_id"], "Team": s["team"], "Required": s["required"],
             "Can attend": s["can_attend"], "Short by": s["short_by"],
             "Flagged day(s)": ", ".join(s["days"])} for s in shortfalls]),
            hide_index=True, width="stretch")

# ---------- Headline numbers ----------
per_day = result["per_day"]
cols = st.columns(4)
cols[0].metric("Average satisfaction", f"{result['average']:.1f}%",
               help="Score of the days each person got, as a share of their best possible days.")
cols[1].metric("Least-satisfied person", f"{result['lowest']:.1f}%")
cols[2].metric(f"Busiest day ({per_day.idxmax()})", f"{per_day.max()} / {int(seats)} seats")
if result["naive_clashes"] is not None:
    wasted = sum(result["naive_clashes"].values())
    cols[3].metric("No-show desks avoided", wasted,
                   help="Desks a roster that ignores availability would book for people on "
                        "leave, off or unavailable.")
elif result["desks_freed"] > 0:
    cols[3].metric("Desk-days freed by leave and part-time", result["desks_freed"])
else:
    cols[3].metric("Desk-days booked this week", int(per_day.sum()))

# ---------- Tabs ----------
tab_roster, tab_days, tab_teams, tab_whatif = st.tabs(
    ["Roster", "Daily occupancy", "Team days", "What-if analysis"])

with tab_roster:
    roster = result["roster"]
    views = ["All teams"] + (["Needs exception"] if shortfalls else []) \
        + sorted(roster["team"].unique())
    chosen = st.selectbox("Show", views)
    if chosen == "All teams":
        shown = roster
    elif chosen == "Needs exception":
        shown = roster[roster["short_by"] > 0]
    else:
        shown = roster[roster["team"] == chosen]
    display = shown.rename(columns={"employee_id": "Employee", "team": "Team",
                                    "contract": "Contract", "office_days": "Office days",
                                    "short_by": "Short by"})
    display["Satisfaction %"] = shown["satisfaction_%"].map(
        lambda v: "away all week" if pd.isna(v) else f"{v:.1f}")
    display = display.drop(columns="satisfaction_%")
    if not shortfalls:
        display = display.drop(columns="Short by")
    st.dataframe(
        display.style.map(lambda v: CELL_COLOURS.get(v, ""), subset=DAYS),
        hide_index=True, width="stretch", height=480,
    )
    st.download_button("Download roster (CSV)", roster.to_csv(index=False).encode(),
                       "office_roster.csv", "text/csv", type="primary")

with tab_days:
    occupancy = pd.DataFrame({"Day": DAYS, "In office": per_day.to_numpy()})
    bars = alt.Chart(occupancy).mark_bar(color="#3B7DD8").encode(
        x=alt.X("Day", sort=DAYS, title=None),
        y=alt.Y("In office", title="People in office"),
        tooltip=["Day", "In office"],
    )
    capacity = alt.Chart(pd.DataFrame({"Seats": [int(seats)]})).mark_rule(
        color="#C0392B", strokeDash=[6, 4], size=2).encode(y="Seats")
    st.altair_chart(bars + capacity, width="stretch")
    st.caption("Dashed line = seats available.")
    if result["naive_clashes"] is not None:
        c = result["naive_clashes"]
        st.markdown(
            f"A roster that ignored availability would have booked **{c['leave']}** desks for "
            f"people on leave, **{c['off']}** for part-timers on their day off and "
            f"**{c['unavailable']}** for people who can't come in."
        )

with tab_teams:
    if not team_days:
        st.info("Team days are switched off in the sidebar.")
    else:
        team_table = pd.DataFrame(
            [{"Team": t, "Shared day": day, "In office": n_in, "Away that day": n_away}
             for t, (day, n_in, n_away) in sorted(result["shared_days"].items())])
        st.dataframe(team_table, hide_index=True, width="stretch")
        st.caption("Members who are off, on leave or unavailable on their team's day are excused.")

with tab_whatif:
    st.markdown("See how seat count and office policy change satisfaction, before you decide.")
    low_default = max(1, int(seats) - 10)
    seat_range = st.slider("Seat range", 1, max(int(seats) * 2, 20),
                           (low_default, int(seats) + 10))
    step = max(1, (seat_range[1] - seat_range[0]) // 8)
    policies = [p for p in (policy_days - 1, policy_days, policy_days + 1) if 1 <= p <= 5]
    if st.button("Run what-if analysis"):
        options = list(range(seat_range[0], seat_range[1] + 1, step))
        rows, progress = [], st.progress(0.0)
        total = len(options) * len(policies)
        for i, (policy, s) in enumerate([(p, s) for p in policies for s in options]):
            out = run_model(employees, status_table, s, policy, team_days, team_share, False,
                            flag_exceptions)
            possible = not out["problems"]
            rows.append({"Office days": f"{policy} days/week", "Seats": s,
                         "Average satisfaction": out["average"] if possible else None,
                         "Least-satisfied person": out["lowest"] if possible else None})
            progress.progress((i + 1) / total)
        progress.empty()
        table = pd.DataFrame(rows)
        long = table.melt(["Office days", "Seats"], var_name="Measure", value_name="Satisfaction %")
        chart = alt.Chart(long.dropna()).mark_line(point=True).encode(
            x=alt.X("Seats:Q"),
            y=alt.Y("Satisfaction %:Q", scale=alt.Scale(zero=False)),
            color="Office days:N",
            tooltip=["Office days", "Seats", alt.Tooltip("Satisfaction %:Q", format=".1f")],
        ).properties(height=260).facet(column=alt.Column("Measure:N", title=None))
        st.altair_chart(chart)
        impossible = table[table["Average satisfaction"].isna()]
        if not impossible.empty:
            st.caption("No roster possible for: " + ", ".join(
                f"{r['Office days']} at {r['Seats']} seats" for _, r in impossible.iterrows()))

st.divider()
st.caption(f"Built by Arun Yogesh Subramanian · Python, SciPy (HiGHS) and Streamlit · "
           f"[Source code]({REPO_URL})")
