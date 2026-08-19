"""Delay Propagation Explorer — an interactive view of the warehouse.

The published dashboard answers a fixed set of questions. This answers whichever
one you ask: every chart re-queries the 33.6M-row fact table live against the
current filter, which DuckDB returns in well under a tenth of a second.

    streamlit run app/explorer.py

The Rotation Inspector is the part worth opening first. It takes one airframe on
one day and draws the day it actually flew against the day it was scheduled to
fly, so a cascade can be watched leg by leg rather than read as a statistic.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from app import charts
from app.query import Filters, q

st.set_page_config(page_title="Delay Propagation Explorer", page_icon="✈️", layout="wide")

BLOCK_MINUTE_USD = 98.41


# --------------------------------------------------------------------- filters

@st.cache_data(show_spinner=False)
def reference():
    carriers = q("SELECT carrier, carrier_name, carrier_type FROM dim_carrier ORDER BY flights DESC")
    airports = q("""SELECT airport_code, city, size_band FROM dim_airport
                    WHERE size_band IN ('Large','Medium','Small') ORDER BY departures DESC""")
    span = q("SELECT min(flight_date) lo, max(flight_date) hi FROM fct_flight")
    return carriers, airports, span.lo[0], span.hi[0]


CARRIERS, AIRPORTS, DATE_LO, DATE_HI = reference()
CARRIER_LABEL = dict(zip(CARRIERS.carrier, CARRIERS.carrier + " — " + CARRIERS.carrier_name))
AIRPORT_LABEL = dict(zip(AIRPORTS.airport_code, AIRPORTS.airport_code + " — " + AIRPORTS.city))

st.title("Delay Propagation Explorer")
st.caption(
    "33,653,101 US domestic flights, January 2021 – December 2025. "
    "Every chart re-queries the warehouse against the filter below."
)

# One filter row scoping everything, rather than per-chart controls: charts that
# filter independently are how two numbers on the same screen come to disagree.
with st.container(border=True):
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        carriers = st.multiselect(
            "Carrier", options=list(CARRIER_LABEL), format_func=CARRIER_LABEL.get,
            default=[], placeholder="All carriers",
        )
    with c2:
        airports = st.multiselect(
            "Origin airport", options=list(AIRPORT_LABEL), format_func=AIRPORT_LABEL.get,
            default=[], placeholder="All airports",
        )
    with c3:
        span = st.date_input(
            "Date range", value=(DATE_LO, DATE_HI),
            min_value=DATE_LO, max_value=DATE_HI, format="YYYY-MM-DD",
        )

date_from, date_to = span if isinstance(span, tuple) and len(span) == 2 else (DATE_LO, DATE_HI)
F = Filters(carriers, airports, date_from, date_to)
where, params = F.where()

overview, propagation, rotation, stations = st.tabs(
    ["Overview", "Propagation", "Rotation inspector", "Where to intervene"]
)


# -------------------------------------------------------------------- overview

with overview:
    kpi = q(f"""
        SELECT count(*) flights,
               100.0*avg(is_on_time_a14::INT) a14,
               100.0*avg(completed::INT) completion,
               100.0*avg(cancelled::INT) cancelled,
               avg(arr_delay) FILTER (WHERE completed) mean_delay,
               quantile_cont(arr_delay, 0.90) FILTER (WHERE completed) p90,
               sum(root_delay_minutes) root_min,
               sum(inherited_delay_minutes) inherited_min
        FROM fct_flight WHERE {where}
    """, params)

    if not kpi.flights[0]:
        st.warning("No flights match this filter.")
        st.stop()

    k = kpi.iloc[0]
    cols = st.columns(5)
    cols[0].metric("Flights", f"{k.flights:,.0f}")
    cols[1].metric("On-time arrival (A14)", f"{k.a14:.2f}%")
    cols[2].metric("Completion factor", f"{k.completion:.2f}%")
    cols[3].metric("Mean arrival delay", f"{k.mean_delay:.1f} min")
    cols[4].metric("90th percentile delay", f"{k.p90:.0f} min")
    st.caption(
        "Cancelled and diverted flights are in the A14 denominator. Excluding them lets "
        "an airline improve its on-time rate by cancelling its worst flights, which is why "
        "completion factor sits beside it."
    )

    st.subheader("Where the delay minutes come from")
    total = k.root_min + k.inherited_min
    if total:
        st.plotly_chart(charts.split_bar(k.root_min, k.inherited_min),
                        use_container_width=True, config={"displayModeBar": False})
        share = 100 * k.inherited_min / total
        st.markdown(
            f"**{share:.1f}%** of delay in this slice was inherited from an earlier leg — "
            f"{k.inherited_min/1e6:,.1f}M minutes, about "
            f"**${k.inherited_min * BLOCK_MINUTE_USD / 1e9:,.2f}B** in direct operating cost. "
            "Inherited delay has no cause of its own and cannot be fixed at the flight that "
            "reports it."
        )

    st.subheader("On-time arrival by month")
    trend = q(f"""
        SELECT make_date(year, month, 1) AS month,
               100.0*avg(is_on_time_a14::INT) AS a14,
               100.0*sum(inherited_delay_minutes)
                   /nullif(sum(root_delay_minutes+inherited_delay_minutes),0) AS inherited_pct
        FROM fct_flight WHERE {where} GROUP BY 1 ORDER BY 1
    """, params)
    st.plotly_chart(charts.line(trend, "month", "a14", ylabel="On-time arrival %", yfmt=":.1f"),
                    use_container_width=True, config={"displayModeBar": False})
    with st.expander("Table view"):
        st.dataframe(trend, use_container_width=True, hide_index=True)


# ----------------------------------------------------------------- propagation

with propagation:
    st.subheader("Damage: further flights delayed by one root delay")
    st.caption("By the root delay's scheduled departure hour — " + F.describe())
    dmg = q(f"""
        SELECT root_dep_hour_local AS hour, count(*) AS roots,
               avg(downstream_legs) AS legs, avg(downstream_delay_minutes) AS minutes,
               avg(amplification_ratio) AS amplification
        FROM mart_cascade
        WHERE root_dep_hour_local BETWEEN 5 AND 22 AND {where.replace('origin', 'root_origin')}
        GROUP BY 1 ORDER BY 1
    """, params)
    if len(dmg):
        st.plotly_chart(charts.line(dmg, "hour", "legs", color=charts.INHERITED,
                                    ylabel="Downstream legs delayed",
                                    xlabel="Scheduled departure hour of the root delay"),
                        use_container_width=True, config={"displayModeBar": False})

    st.subheader("Repair: delay minutes saved per buffer minute spent")
    st.caption("Simulating +10 minutes of slack on every turn, then re-running the propagation model")
    buf = q(f"""
        SELECT sched_dep_hour_local AS hour, count(*) AS turns,
               (sum(greatest(coalesce(prev_arr_delay,0) - turn_slack_minutes,0))
              - sum(greatest(coalesce(prev_arr_delay,0) - (turn_slack_minutes+10),0)))
                / (10.0*count(*)) AS efficiency
        FROM fct_rotation_leg
        WHERE is_continuation AND sched_dep_hour_local BETWEEN 5 AND 22 AND {where}
        GROUP BY 1 ORDER BY 1
    """, params)
    if len(buf):
        st.plotly_chart(
            charts.line(buf, "hour", "efficiency", color=charts.ROOT,
                        ylabel="Minutes saved per buffer minute",
                        xlabel="Scheduled departure hour of the turn", threshold=1.0, yfmt=":.3f"),
            use_container_width=True, config={"displayModeBar": False})
        st.info(
            "The two curves disagree, which is the finding. Damage peaks in the morning; the "
            "value of buffer peaks in the evening. Aircraft turning early slept at the station "
            "and are not late yet, so slack has nothing to absorb — and no hour reaches "
            "break-even, so blanket padding does not pay for itself at any time of day. "
            "Before noon the only lever is preventing the delay.",
            icon="⚠️",
        )
    with st.expander("Table view"):
        st.dataframe(dmg.merge(buf, on="hour", how="outer"),
                     use_container_width=True, hide_index=True)


# ----------------------------------------------------------- rotation inspector

with rotation:
    st.subheader("One aircraft, one day")
    st.markdown(
        "Pick an airframe and a date to see the day it flew against the day it was scheduled "
        "to fly. Legs drawn in **orange** inherited delay from the leg before; legs in "
        "**blue** broke on their own."
    )

    worst = q(f"""
        SELECT tail_number, flight_date, count(*) AS legs,
               max(cascade_length) AS longest_cascade,
               sum(inherited_delay_minutes) AS inherited_minutes,
               max(arr_delay) AS worst_arrival
        FROM fct_rotation_leg
        WHERE {where}
        GROUP BY 1, 2 HAVING max(cascade_length) >= 3
        ORDER BY inherited_minutes DESC LIMIT 60
    """, params)

    if not len(worst):
        st.warning("No multi-leg cascades in this filter. Widen the date range or clear a filter.")
    else:
        st.caption(
            f"The {len(worst)} worst cascade days in the current filter, ranked by inherited "
            "minutes — so the inspector opens on a day where something actually happened."
        )
        options = {
            f"{r.tail_number} · {r.flight_date:%Y-%m-%d} · {r.legs} legs · "
            f"{r.inherited_minutes:,.0f} inherited min · chain of {r.longest_cascade}": (
                r.tail_number, r.flight_date)
            for r in worst.itertuples()
        }
        picked = st.selectbox("Aircraft and date", list(options), index=0)
        tail, day = options[picked]

        legs = q("""
            SELECT origin, dest, sched_dep_utc, sched_arr_utc, actual_dep_utc, actual_arr_utc,
                   dep_delay, arr_delay, inherited_delay_minutes, turn_slack_minutes,
                   sched_turn_minutes, cascade_position, cascade_length, primary_cause,
                   is_continuation
            FROM fct_rotation_leg
            WHERE tail_number = ? AND flight_date = ? ORDER BY sched_dep_utc
        """, (tail, day))

        if len(legs):
            base = legs.sched_dep_utc.min()
            mins = lambda s: (s - base).dt.total_seconds() / 60
            legs["leg_seq"] = range(1, len(legs) + 1)
            legs["sched_offset"] = mins(legs.sched_dep_utc)
            legs["actual_offset"] = mins(legs.actual_dep_utc)
            legs["sched_minutes"] = (legs.sched_arr_utc - legs.sched_dep_utc).dt.total_seconds() / 60
            legs["actual_minutes"] = (legs.actual_arr_utc - legs.actual_dep_utc).dt.total_seconds() / 60
            for col, src in [("sched_dep_hhmm", "sched_dep_utc"), ("sched_arr_hhmm", "sched_arr_utc"),
                             ("actual_dep_hhmm", "actual_dep_utc"), ("actual_arr_hhmm", "actual_arr_utc")]:
                legs[col] = legs[src].dt.strftime("%H:%M")

            st.plotly_chart(charts.rotation_timeline(legs),
                            use_container_width=True, config={"displayModeBar": False})
            st.caption(
                "Outlined bars are the schedule, solid bars what was flown; the x-axis is minutes "
                "from the day's first scheduled departure. Times are UTC — a rotation crosses "
                "timezones, so local clock times would not be comparable along one axis."
            )

            first_inherit = legs[(legs.inherited_delay_minutes > 0) & legs.is_continuation]
            if len(first_inherit):
                row = first_inherit.iloc[0]
                st.markdown(
                    f"The cascade starts at leg **{row.leg_seq}** "
                    f"({row.origin}→{row.dest}): the inbound aircraft was late, the turn held "
                    f"**{row.turn_slack_minutes:.0f} minutes** of slack against a scheduled "
                    f"**{row.sched_turn_minutes:.0f}**, and **{row.inherited_delay_minutes:.0f} "
                    f"minutes** went through to the next departure. Total inherited across the "
                    f"day: **{legs.inherited_delay_minutes.sum():,.0f} minutes**."
                )

            broken = int((~legs.is_continuation).sum())
            table = legs[["leg_seq", "origin", "dest", "sched_dep_hhmm", "actual_dep_hhmm",
                          "dep_delay", "arr_delay", "sched_turn_minutes", "turn_slack_minutes",
                          "inherited_delay_minutes", "is_continuation", "primary_cause"]].rename(
                columns={
                    "leg_seq": "Leg", "origin": "From", "dest": "To",
                    "sched_dep_hhmm": "Sched dep", "actual_dep_hhmm": "Actual dep",
                    "dep_delay": "Dep delay", "arr_delay": "Arr delay",
                    "sched_turn_minutes": "Sched turn", "turn_slack_minutes": "Slack",
                    "inherited_delay_minutes": "Inherited", "is_continuation": "In rotation",
                    "primary_cause": "Primary cause"})
            st.dataframe(table, use_container_width=True, hide_index=True,
                         column_config={"In rotation": st.column_config.CheckboxColumn(
                             "In rotation", help="Whether this leg continues the previous one")})
            if broken:
                st.caption(
                    f"**{broken} of {len(legs)} legs are not marked as continuing the rotation.** "
                    "A leg fails that test when the previous leg landed somewhere else, or when "
                    "the scheduled turn is negative — the aircraft is booked out before its "
                    "inbound is due in. That is not a data error so much as a tail-chain break: "
                    "an aircraft swap, a ferry or maintenance leg absent from the passenger feed, "
                    "or a schedule changed after the fact. The propagation model excludes these "
                    "rather than inventing a turn that never happened, which is why some legs "
                    "here show inherited minutes reported by the airline against a turn the model "
                    "does not count.")


# -------------------------------------------------------------------- stations

with stations:
    st.subheader("Where a turn buffer would absorb the most delay")
    st.caption(
        "Ranked by delay minutes a +10 minute turn buffer would absorb, from the propagation "
        "model. Efficiency is minutes saved per buffer minute spent — break-even is 1.0."
    )
    carrier_clause, cparams = "", ()
    if F.carriers:
        carrier_clause = f" AND o.carrier IN ({','.join('?' * len(F.carriers))})"
        cparams = tuple(F.carriers)
    if F.airports:
        carrier_clause += f" AND o.airport_code IN ({','.join('?' * len(F.airports))})"
        cparams += tuple(F.airports)

    opp = q(f"""
        SELECT o.carrier_name AS carrier, o.airport_code AS station, o.city,
               o.turns, o.median_sched_turn_minutes AS sched_turn,
               o.min_feasible_turn_minutes AS min_turn, o.median_slack_minutes AS slack,
               o.tight_turn_pct AS tight_pct, o.minutes_saved_plus_10 AS minutes_saved,
               o.efficiency_plus_10 AS efficiency,
               o.delay_cost_avoided_usd_plus_10 AS cost_avoided_usd
        FROM mart_turn_slack_opportunity o
        WHERE TRUE {carrier_clause}
        ORDER BY o.minutes_saved_plus_10 DESC LIMIT 40
    """, cparams)

    if not len(opp):
        st.warning("No stations meet the 2,000-turn minimum under this filter.")
    else:
        top = opp.head(12).copy()
        top["label"] = top.carrier.str.replace(" Airlines", "", regex=False) + " · " + top.station
        st.plotly_chart(
            charts.bars(top, "label", "minutes_saved", ylabel="Delay minutes absorbed"),
            use_container_width=True, config={"displayModeBar": False})
        st.dataframe(
            opp, use_container_width=True, hide_index=True,
            column_config={
                "minutes_saved": st.column_config.ProgressColumn(
                    "Minutes absorbed", format="%.0f",
                    min_value=0, max_value=float(opp.minutes_saved.max())),
                "cost_avoided_usd": st.column_config.NumberColumn("Cost avoided", format="$%.0f"),
                "efficiency": st.column_config.NumberColumn("Efficiency", format="%.3f"),
                "tight_pct": st.column_config.NumberColumn("Tight turns", format="%.1f%%"),
            })
        st.caption(
            "Buffer is not free: every added minute is paid on every turn, including the "
            "overwhelming majority that were never going to be late. The utilisation cost of "
            "ground time is not in this feed, so this ranks candidates and sizes the delay "
            "benefit — it does not claim a net P&L number."
        )
