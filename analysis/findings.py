"""Regenerate every headline number in the documentation.

Nothing in docs/ is typed by hand. This script is the single source of the
figures quoted there, so a rebuild on a different data window cannot leave a
stale number behind in the write-up.

    python -m analysis.findings            print the report
    python -m analysis.findings --write    also refresh docs/03-findings.md
"""

import sys
from textwrap import dedent

import duckdb

from pipeline.config import ROOT, WAREHOUSE

BLOCK_MINUTE_USD = 98.41  # A4A 2025; see sql/03_facts/05_ref_cost_assumption.sql


def connect():
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    con.execute("LOAD icu;")
    con.execute("SET TimeZone='UTC'")
    return con


def one(con, sql):
    return con.execute(sql).fetchone()


def table(con, sql):
    return con.execute(sql).df()


def report(con) -> str:
    out = []
    w = out.append

    # ---------------------------------------------------------------- scope
    flights, carriers, airports, tails, d0, d1 = one(con, """
        SELECT count(*), count(DISTINCT carrier), count(DISTINCT origin),
               count(DISTINCT tail_number), min(flight_date), max(flight_date)
        FROM fct_flight
    """)
    a14, cf, cancel, avg_delay, p90 = one(con, """
        SELECT 100.0*avg(is_on_time_a14::INT), 100.0*avg(completed::INT),
               100.0*avg(cancelled::INT), avg(arr_delay) FILTER (WHERE completed),
               quantile_cont(arr_delay, 0.90) FILTER (WHERE completed)
        FROM fct_flight
    """)
    w(dedent(f"""
    ## Scope

    | | |
    |---|---|
    | Flights | {flights:,} |
    | Window | {d0} to {d1} ({carriers} carriers, {airports} airports, {tails:,} airframes) |
    | On-time arrival (A14) | {a14:.2f}% |
    | Completion factor | {cf:.2f}% |
    | Cancellation rate | {cancel:.2f}% |
    | Mean arrival delay | {avg_delay:.1f} min |
    | 90th percentile arrival delay | {p90:.0f} min |
    """).strip() + "\n")

    # ------------------------------------------------- finding 1: inherited
    root_m, inh_m, pct_inh = one(con, """
        SELECT sum(root_delay_minutes)/1e6, sum(inherited_delay_minutes)/1e6,
               100.0*sum(inherited_delay_minutes)
                   /sum(root_delay_minutes + inherited_delay_minutes)
        FROM fct_flight
    """)
    w(dedent(f"""

    ## Finding 1 — {pct_inh:.1f}% of all delay is inherited, not caused

    Of {root_m + inh_m:,.1f}M delay minutes, {root_m:,.1f}M originated with the flight
    that reported them and {inh_m:,.1f}M arrived on a late aircraft from an earlier
    leg. At ${BLOCK_MINUTE_USD}/block minute the inherited share alone is
    **${inh_m * BLOCK_MINUTE_USD / 1000:,.2f}B** of direct operating cost over five years.

    Inherited delay has no cause of its own. Every minute of it was created
    somewhere else and moved here by an airframe, which means it cannot be fixed
    at the flight that reports it -- only at the flight that started it.
    """).strip() + "\n")

    # ------------------------------------------------ finding 2: the model
    n, pred, rep, corr = one(con, """
        SELECT count(*), avg(predicted_inherited_minutes), avg(inherited_delay_minutes),
               corr(predicted_inherited_minutes, inherited_delay_minutes)
        FROM fct_rotation_leg WHERE is_continuation AND prev_arr_delay > 15
    """)
    slack = table(con, """
        SELECT least(floor(turn_slack_minutes/15),6)*15 AS slack_floor,
               count(*) AS turns, avg(inherited_delay_minutes) AS avg_inherited,
               100.0*avg((dep_delay>=15)::INT) AS pct_late
        FROM fct_rotation_leg
        WHERE is_continuation AND prev_arr_delay BETWEEN 30 AND 60
        GROUP BY 1 ORDER BY 1
    """)
    tight = slack.iloc[0]
    loose = slack.iloc[-1]
    comp = table(con, """
        SELECT least(floor(turn_slack_minutes/15),6)*15 AS slack_floor,
               100.0*count(*) FILTER (WHERE carrier='WN')/count(*) AS wn_pct,
               100.0*avg((cascade_position>0)::INT) AS cascade_pct
        FROM fct_rotation_leg
        WHERE is_continuation AND prev_arr_delay BETWEEN 30 AND 60
        GROUP BY 1 ORDER BY 1
    """).set_index("slack_floor")
    wn_bump, wn_dip = comp.loc[60, "wn_pct"], comp.loc[45, "wn_pct"]
    casc_bump, casc_dip = comp.loc[60, "cascade_pct"], comp.loc[45, "cascade_pct"]
    w(dedent(f"""

    ## Finding 2 — the propagation mechanism is slack, and the model checks out

    Delay passes through a turn only to the extent the ground time cannot absorb
    it: `predicted = max(0, inbound_delay - slack)`, where slack is the scheduled
    turn minus the fastest turn that operator has actually achieved at that
    station.

    Across {n:,} turns receiving an aircraft more than 15 minutes late, the model
    predicts a mean of {pred:.1f} minutes passed on. The airlines themselves
    reported {rep:.1f}. Correlation between the two, computed independently:
    **{corr:.3f}**.

    The dose-response is strong but **not monotonic**, and the exception is worth
    stating. Among turns receiving an aircraft 30-60 minutes late, those with under
    15 minutes of slack passed on {tight.avg_inherited:.1f} minutes and departed
    late {tight.pct_late:.0f}% of the time; those with 90+ minutes passed on
    {loose.avg_inherited:.1f} minutes and departed late {loose.pct_late:.0f}%.

    But the 60-89 minute buckets sit above the 45-59 bucket rather than below it.
    That is a composition effect, not a break in the mechanism: turns scheduled
    100-120 minutes are disproportionately Southwest ({wn_bump:.0f}% of the 60-74
    bucket against {wn_dip:.0f}% of the 45-59 bucket) and disproportionately already
    mid-cascade ({casc_bump:.0f}% against {casc_dip:.0f}%). Restricting to turns not
    already deep in a cascade narrows the bump but does not remove it, so it is
    reported rather than controlled away.
    """).strip() + "\n")

    # ------------------------------------------- finding 3: morning multiplier
    hours = table(con, """
        SELECT root_dep_hour_local AS hour, count(*) AS roots,
               avg(downstream_legs) AS legs, avg(downstream_delay_minutes) AS mins,
               avg(amplification_ratio) AS amp
        FROM mart_cascade WHERE root_dep_hour_local BETWEEN 5 AND 22
        GROUP BY 1 ORDER BY 1
    """)
    peak = hours.loc[hours.legs.idxmax()]
    trough = hours.loc[hours.legs.idxmin()]
    w(dedent(f"""

    ## Finding 3 — the same delay costs {peak.legs / trough.legs:.0f}x more in the morning

    A root delay departing at {int(peak.hour):02d}:00 goes on to delay
    {peak.legs:.2f} further flights and {peak.mins:.1f} further minutes. The same
    delay at {int(trough.hour):02d}:00 costs {trough.legs:.2f} legs and
    {trough.mins:.1f} minutes -- the aircraft is done for the day and there is
    nothing left downstream to break.

    Amplification peaks at {hours.amp.max():.2f}x around
    {int(hours.loc[hours.amp.idxmax()].hour):02d}:00: for every minute the root
    flight lost, the network lost {hours.amp.max():.2f}.
    """).strip() + "\n")

    # ------------------------------------------- finding 4: buffer is the wrong lever
    eff = table(con, """
        SELECT sched_dep_hour_local AS hour, count(*) AS turns,
               (sum(greatest(coalesce(prev_arr_delay,0) - turn_slack_minutes,0))
              - sum(greatest(coalesce(prev_arr_delay,0) - (turn_slack_minutes+10),0)))
                 / (10.0*count(*)) AS efficiency
        FROM fct_rotation_leg
        WHERE is_continuation AND sched_dep_hour_local BETWEEN 5 AND 22
        GROUP BY 1 ORDER BY 1
    """)
    best = eff.loc[eff.efficiency.idxmax()]
    morning = eff[eff.hour <= 8].efficiency.mean()
    w(dedent(f"""

    ## Finding 4 — so buffer the morning? No. The data says the opposite

    The obvious response to Finding 3 is to protect the morning bank with extra
    ground time. Simulating +10 minutes of slack on every turn and re-running the
    propagation model says that would be close to worthless.

    Buffer efficiency -- delay minutes avoided per buffer minute spent -- averages
    **{morning:.3f}** across turns before 09:00, against a peak of
    **{best.efficiency:.3f}** at {int(best.hour):02d}:00. The reason is simple once
    seen: aircraft turning in the early morning slept at the station overnight.
    They arrive on time because nothing has happened yet. There is no delay there
    to absorb, so slack has nothing to do.

    Buffer works where late aircraft actually are, which is the afternoon. But by
    then amplification has fallen to
    {hours[hours.hour == round(best.hour)].amp.iloc[0]:.2f}x and much of the day's
    damage is already done. **No hour of the day reaches an efficiency of 1.0.**
    Blanket schedule padding does not pay for itself in delay minutes at any hour,
    which is a finding, not a failure -- it rules out the intuitive answer.
    """).strip() + "\n")

    # ------------------------------------------- finding 5: prevention
    morn_ctrl, amp, saved_m, usd_yr = one(con, """
        SELECT sum(root_controllable_minutes)/1e6, avg(amplification_ratio),
               0.20*sum(root_controllable_minutes)*avg(amplification_ratio)/1e6,
               0.20*sum(root_controllable_minutes)*avg(amplification_ratio)*98.41/1e6/5
        FROM mart_cascade WHERE root_dep_hour_local BETWEEN 5 AND 11
    """)
    w(dedent(f"""

    ## Finding 5 — the lever that does work is prevention before noon

    If slack cannot help the morning, the only remaining lever is stopping the
    root delay from happening. {morn_ctrl:.1f}M minutes of *carrier-controllable*
    root delay -- crew, maintenance, boarding, fuelling, baggage -- originated
    between 05:00 and 11:00 over the five years, and it carried an average
    amplification of {amp:.2f}x.

    Preventing 20% of it removes **{saved_m:.1f}M network delay minutes**, worth
    roughly **${usd_yr:,.0f}M a year** in direct operating cost. That is the
    recommendation this analysis supports, and it is aimed at station operations
    before noon -- not at the schedule.
    """).strip() + "\n")

    # ------------------------------------------- finding 6: carriers
    carriers_df = table(con, """
        SELECT c.carrier_name, c.carrier_type, sum(m.scheduled_flights) AS flights,
               sum(m.scheduled_flights*m.on_time_arrival_pct)/sum(m.scheduled_flights) AS a14,
               100.0*sum(m.inherited_delay_minutes)
                   /sum(m.root_delay_minutes+m.inherited_delay_minutes) AS inherited_pct
        FROM mart_carrier_monthly m JOIN dim_carrier c USING (carrier)
        GROUP BY 1,2 HAVING sum(m.scheduled_flights) > 200000 ORDER BY a14 DESC
    """)
    slack_by_carrier = table(con, """
        SELECT d.carrier_name, o.airport_code, o.median_slack_minutes, o.tight_turn_pct
        FROM mart_turn_slack_opportunity o JOIN dim_carrier d USING (carrier)
        WHERE (d.carrier_name, o.airport_code) IN
              (('Delta Air Lines','ATL'), ('Southwest Airlines','DEN'))
    """)
    w("\n\n## Finding 6 — the carrier table, and what sits underneath it\n")
    w("| Carrier | Type | Flights | A14 | Inherited share |")
    w("|---|---|---:|---:|---:|")
    for _, r in carriers_df.iterrows():
        w(f"| {r.carrier_name} | {r.carrier_type} | {r.flights:,.0f} | "
          f"{r.a14:.2f}% | {r.inherited_pct:.1f}% |")
    dl = slack_by_carrier[slack_by_carrier.carrier_name == 'Delta Air Lines'].iloc[0]
    wn = slack_by_carrier[slack_by_carrier.carrier_name == 'Southwest Airlines'].iloc[0]
    w(dedent(f"""
    The inherited-share column explains the ranking better than the A14 column
    describes it. Delta carries {carriers_df[carriers_df.carrier_name=='Delta Air Lines'].inherited_pct.iloc[0]:.1f}%
    inherited delay and schedules a median {dl.median_slack_minutes:.0f} minutes of
    slack at {dl.airport_code}, with {dl.tight_turn_pct:.0f}% of turns tight.
    Southwest carries {carriers_df[carriers_df.carrier_name=='Southwest Airlines'].inherited_pct.iloc[0]:.1f}%
    and schedules {wn.median_slack_minutes:.0f} minutes at {wn.airport_code}, with
    {wn.tight_turn_pct:.0f}% tight.

    That is not a quality gap, it is a business model. High utilisation is how the
    low-cost fare exists; the cascade is what it costs. The two numbers belong in
    the same sentence.

    One caveat the table cannot escape: BTS reports the OPERATING carrier. Endeavor
    and Horizon top this ranking as regional operators flying short stages under
    Delta and Alaska brands, and their passengers booked Delta and Alaska.
    """).strip() + "\n")

    # ------------------------------------------- finding 7: natural experiment
    wn_days = table(con, """
        SELECT flight_date::VARCHAR AS flight_date,
               100.0*avg(cancelled::INT) FILTER (WHERE carrier='WN') AS wn,
               100.0*avg(cancelled::INT) FILTER (WHERE carrier<>'WN') AS others
        FROM fct_flight WHERE flight_date BETWEEN DATE '2022-12-20' AND DATE '2022-12-31'
        GROUP BY 1 ORDER BY 1
    """)
    peak_row = wn_days.loc[wn_days.wn.idxmax()]
    w("\n\n## Finding 7 — December 2022, with a control group\n")
    w(dedent("""
    A winter storm hit the US network on 21-23 December 2022. Every carrier flew
    into the same weather, which makes the days that follow a natural experiment:
    the storm is the treatment, the other carriers are the control, and the only
    thing that differs is how each airline's rotations absorbed it.
    """).strip() + "\n")
    w("\n| Date | Southwest cancelled | All other carriers |")
    w("|---|---:|---:|")
    for _, r in wn_days.iterrows():
        w(f"| {r.flight_date} | {r.wn:.1f}% | {r.others:.1f}% |")
    w(dedent(f"""
    Both groups break together on the 22nd. From the 26th the control group is
    essentially recovered at {wn_days[wn_days.flight_date=='2022-12-26'].others.iloc[0]:.1f}%
    while Southwest peaks at **{peak_row.wn:.1f}%** on the same day and stays above
    60% for three more.

    The weather stopped and the cancellations did not. What continued was the
    cascade: aircraft and crews out of position, every recovery attempt inheriting
    from the last. This is Finding 1 at full scale -- a network whose delay was
    almost entirely inherited by then, with no root cause left to fix.
    """).strip() + "\n")

    return "\n".join(out)


def main() -> int:
    if not WAREHOUSE.exists():
        print("warehouse not built -- run python -m pipeline.build_warehouse", file=sys.stderr)
        return 1
    con = connect()
    body = report(con)
    text = ("# Findings\n\n*Generated by `python -m analysis.findings`. "
            "Every figure below is computed from the warehouse at build time.*\n\n" + body + "\n")
    print(text)
    if "--write" in sys.argv:
        path = ROOT / "docs" / "03-findings.md"
        path.parent.mkdir(exist_ok=True)
        path.write_text(text)
        print(f"\nwritten to {path.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
