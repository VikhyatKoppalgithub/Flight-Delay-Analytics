# 01 — Business Case

**Project:** Delay Propagation & Schedule Buffer Analysis
**Analyst:** Vikhyat Yashvanth Koppal
**Data:** US DOT / Bureau of Transportation Statistics, On-Time Performance, Jan 2021 – Dec 2025
**Status:** Analysis complete, recommendations pending sponsor review

---

## 1. The question behind the question

Every airline operations review opens with the same chart: on-time performance by
month, against target, by carrier. It is a chart about outcomes, and it reliably
produces the same meeting — the number is down, everyone agrees delays are bad,
someone commits to reducing them, and nothing in the schedule changes.

The chart cannot produce a decision because it does not distinguish between two
completely different things that both show up as "a late flight":

- a flight that went wrong, and
- a flight that was fine but was given a late aircraft.

Those need opposite responses. The first is an operations problem at a station.
The second is a *schedule* problem, and the station where it surfaces is not the
station that caused it. Averaging them together produces a number that no one can
act on, which is why the meeting repeats.

**The business question this project answers:** of the delay we absorb every year,
how much originates with us, how much is inherited from earlier flights, and
where is the highest-return place to intervene?

## 2. Why it is worth answering

US carriers ran **33.7 million** domestic flights over the five-year window at a
**77.97%** on-time arrival rate. Every minute of delay costs roughly **$98** in
direct operating cost alone — crew, fuel, maintenance, ownership — before any
passenger compensation, rebooking or lost future booking.

The analysis finds **182.5 million minutes** of inherited delay across the window,
about **$17.96 billion** in direct cost. That is not a rounding error on the
operation; it is a line item large enough to justify a dedicated workstream, and
it is currently invisible because no standard report separates it out.

## 3. Scope

**In scope**
- All US domestic scheduled passenger flights reported to BTS, 2021–2025
- Delay attribution: what originated here versus what arrived on a late aircraft
- Aircraft rotation reconstruction and cascade tracing by tail number
- Turn-time slack measurement and a buffer simulation
- Carrier, station and route KPI reporting

**Out of scope, and why**
- *Passenger itineraries and misconnects.* BTS is a flight-level feed with no
  passenger records. Missed connections are a large share of the true cost of
  delay and cannot be measured here at all.
- *Crew scheduling.* Crew legality cascades independently of aircraft and was a
  primary driver of the December 2022 event examined in Finding 7. Not in the feed.
- *Fleet economics.* Ground time has a utilisation cost that requires fleet
  planning data. This is why the buffer analysis reports delay minutes avoided
  and stops short of a net P&L figure.
- *International flights.* BTS on-time reporting covers domestic segments.

## 4. Success criteria

| # | Criterion | Result |
|---|---|---|
| SC-1 | Quantify inherited vs. originated delay across the full window | Met — Finding 1 |
| SC-2 | Establish a propagation mechanism that can be independently validated | Met — Finding 2, r = 0.784 against airline-reported attribution |
| SC-3 | Identify when in the operating day intervention has the highest return | Met — Findings 3 and 4 |
| SC-4 | Produce a ranked, sized intervention list a station team can act on | Met — Finding 5 and `mart_turn_slack_opportunity` |
| SC-5 | Every figure reproducible from source with one command | Met — see README §Reproducing |

## 5. Stakeholders

| Role | Interest | What they need from this |
|---|---|---|
| VP Network Operations | Owns the on-time target | Where to spend the operational effort |
| Schedule Planning | Owns turn times and block times | Whether buffer is the right lever, and where |
| Station Operations | Owns the turn | Which stations and which hours to focus on |
| Finance | Owns the cost case | A defensible dollar figure with stated bounds |
| Data Governance | Owns the feed | Documented lineage, quality tests, known defects |

## 6. The analytical bet, stated up front

This project assumes that **delay is a network phenomenon, not a flight
phenomenon**, and that the correct unit of analysis is the aircraft rotation
rather than the flight. If that assumption is wrong, the entire framing collapses
and the standard by-flight reporting is adequate.

Finding 2 is the test of that bet. It passes.
