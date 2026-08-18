# Flight Delay Propagation Analysis

**33.7 million US domestic flights, 2021–2025. 38.8% of all delay in the system
was not caused by the flight that reported it.**

This project reconstructs every aircraft rotation in five years of US Bureau of
Transportation Statistics data — chaining flights by tail number into the sequence
each airframe actually flew — in order to separate delay that *originated* with a
flight from delay that merely *arrived* on it.

That distinction turns out to change the answer to the operational question
everyone actually asks: where should we intervene?

---

## The result

**A root delay departing at 08:00 goes on to delay 0.75 further flights. The same
delay at 21:00 delays 0.06.** Thirteen times the damage for the same lost minutes,
because the morning aircraft still has a day ahead of it to break.

The obvious response is to protect the morning with extra ground time. Simulating
that says it would be close to worthless — and the reason is the interesting part:

| Turn hour | Buffer efficiency (delay min saved per buffer min spent) |
|---|---:|
| 05:00–08:00 | 0.014 |
| 12:00 | 0.102 |
| 19:00 (peak) | 0.185 |

Aircraft turning at 06:00 slept at the station. They are not late yet, so slack has
nothing to absorb. Buffer only earns where late aircraft actually are — the
afternoon — by which point amplification has fallen from 2.44x to 1.34x and most of
the day's damage is done. **No hour reaches break-even.**

So the recommendation is not schedule buffer. It is prevention of
carrier-controllable delay in the morning bank, which is worth roughly **$459M a
year** in direct operating cost at a 20% reduction — [with a pilot design and
sizing to test it first](docs/04-recommendations.md).

Full write-up: **[docs/03-findings.md](docs/03-findings.md)**

---

## Why the model can be trusted

Delay passes through a turn only to the extent the ground time cannot absorb it:

```
predicted_inherited = max(0, inbound_delay − slack)
slack = scheduled_turn − fastest_turn_that_operator_has_achieved_here
```

BTS separately requires airlines to report how many minutes of each delay were
caused by a late inbound aircraft. So the feed already contains the answer this
model is trying to predict, computed by a completely different route.

Across 5.4M turns receiving an aircraft 15+ minutes late, the model predicts a mean
of **23.3** minutes passed on. The airlines reported **21.2**. Correlation:
**0.784**.

The dose-response is monotonic — among turns receiving an aircraft 30–60 minutes
late, those with under 15 minutes of slack departed late 96% of the time; those
with 90+ minutes, 15%.

---

## December 2022, with a control group

A winter storm hit on 21–23 December 2022. Every carrier flew into the same
weather, which makes what followed a natural experiment.

| Date | Southwest cancelled | All other carriers |
|---|---:|---:|
| Dec 22 | 26.2% | 9.6% |
| Dec 24 | 43.7% | 15.7% |
| **Dec 26** | **77.5%** | **6.7%** |
| Dec 28 | 64.4% | 2.4% |

Both break together. By the 26th the control group has recovered and Southwest
peaks. The weather stopped; the cascade did not — which is the thesis of this
project at full scale.

---

## Running it

```bash
pip install -r requirements.txt
python -m pipeline.download          # 60 monthly extracts from BTS, ~1.7 GB, ~15 min
python -m pipeline.ingest            # CSV -> typed parquet, 15 GB -> 0.76 GB, ~2 min
python -m pipeline.build_warehouse   # 15 SQL models -> DuckDB star schema, ~4 min
python -m pytest                     # 28 data quality tests
python -m analysis.findings --write  # regenerate docs/03-findings.md
python -m analysis.export_bi         # CSV extracts for Power BI / Tableau
```

Nothing is committed that can be rebuilt: `data/` is gitignored and every figure
in `docs/` is regenerated from the warehouse by `analysis/findings.py`, so no
number in the write-up can drift from the data behind it.

---

## How it is built

```
pipeline/     download → typed parquet → DuckDB warehouse
sql/
  01_staging/     BTS feed with clock fields resolved to UTC; airport reference
  02_dimensions/  carrier, airport, calendar
  03_facts/       flight fact, rotation chaining, turn benchmarks, propagation
  04_marts/       carrier / station / route KPIs, cascades, buffer simulation
tests/        28 data quality tests, run against the built warehouse
analysis/     findings generator, BI export, data dictionary generator
docs/         business case, KPI definitions, findings, recommendations
dashboards/   CSV extracts sized for Power BI and Tableau
```

**Data:** [BTS Reporting Carrier On-Time Performance](https://www.transtats.bts.gov/Fields.asp?gnoyr_VQ=FGJ),
60 monthly extracts, 110 columns, public domain. Airport timezones and coordinates
from [OpenFlights](https://github.com/jpatokal/openflights). Cost rate from
[Airlines for America](https://www.airlines.org/dataset/u-s-passenger-carrier-delay-costs/)
(2025: $98.41 per block minute).

**Stack:** Python, DuckDB, SQL, pytest, Power BI / Tableau. No dbt — the model
layer is plain SQL run in dependency order by a 60-line runner, laid out in dbt's
conventions so it can be ported if it ever needs to be.

---

## Three decisions worth explaining in an interview

**Cancelled flights stay in the on-time denominator.** The common alternative
computes A14 over completed flights only — which means an airline that cancels its
400 worst flights on a bad day *improves* its reported on-time rate. Completion
factor is reported beside A14 for the same reason: the two can only be gamed
against each other.

**Minimum turn time is measured, not assumed.** It is not in the feed, and a
published figure would be an assumption. The 5th percentile of turns an operator
actually achieved at a station is an observed floor — what they hit when pressed.

**Every clock field is converted to UTC before any arithmetic.** BTS stores six
clock fields as HHMM in the local time of the relevant airport. Arrival instants
are derived forward from the departure instant using scheduled block time and
reported delay, which is exact by construction and avoids the date-wrap bugs that
reconstructing them from local arrival times would introduce. A test asserts that
Chicago resolves to exactly two UTC offsets across the window — if daylight saving
were not being applied, it would be one.

---

## Known limits

Every dollar figure here is a **lower bound**. BTS is a flight-level feed with no
passengers in it, so misconnects, rebooking and compensation — plausibly the
largest cost of delay — are invisible. Crew legality cascades independently and is
also absent. BTS reports the *operating* carrier, so regional operators appear
under their own codes rather than the brands passengers booked.

Full list, including two source-data defects the test suite caught:
[docs/06-assumptions-and-limitations.md](docs/06-assumptions-and-limitations.md)
