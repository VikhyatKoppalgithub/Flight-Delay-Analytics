# 04 — Recommendations

Four recommendations, ordered by expected return. Each states what to do, what
the evidence is, what it is worth, who owns it, and — for the one that requires
committing real money — how to test it before committing.

---

## R-1 — Move controllable-delay effort to the morning bank

**Recommendation.** Reallocate station resourcing — pushback crews, ground
handling, boarding staff, line maintenance response — toward departures between
05:00 and 11:00, and hold morning stations to a controllable-delay target
separate from the all-day number.

**Evidence.** A root delay departing at 08:00 goes on to delay 0.75 further
flights; the same delay at 21:00 delays 0.06 (Finding 3). Amplification peaks at
2.44x late morning. Meanwhile 55.5M minutes of carrier-controllable root delay
originated between 05:00 and 11:00 over the window (Finding 5).

**Value.** Preventing 20% of morning controllable root delay removes ~23.3M
network delay minutes, roughly **$459M a year** in direct operating cost across
the industry — and the same proportional logic applies at a single carrier.

**Why this and not buffer.** See R-2. This is the only lever that works before
noon, because before noon there is no inbound delay for slack to absorb.

**Owner.** Station Operations, with Network Operations setting the target.
**Effort.** Medium — resourcing reallocation, no schedule change, no system change.

---

## R-2 — Do not add schedule buffer across the board

**Recommendation.** Reject blanket increases to scheduled turn time. Treat any
buffer proposal as requiring a station-and-hour-specific business case.

**Evidence.** Simulating +10 minutes of slack on every turn and re-running the
propagation model gives a buffer efficiency — delay minutes avoided per buffer
minute spent — of 0.014 before 09:00 and a *peak* of 0.185 at 19:00 (Finding 4).
**No hour of the operating day reaches 1.0.** Buffer added early is wasted because
the aircraft slept at the station and is not late yet; buffer added late catches
real delay but has almost no remaining day to protect.

**Value.** Avoided cost rather than realised saving. A 10-minute network-wide turn
increase at a carrier the size of Southwest would consume millions of minutes of
schedule to recover a fraction of them in delay.

**What this recommendation is not.** It is not "buffer never works." It is that
buffer must be targeted, and that the targeting must come from the turn-level
table rather than from an average. `mart_turn_slack_opportunity` ranks 1,241
carrier-station combinations by exactly this.

**Owner.** Schedule Planning.
**Effort.** Low — this is a decision not to spend.

---

## R-3 — Fix the highest-volume tight-turn stations individually

**Recommendation.** Review these carrier-station combinations first. They are
where the propagation model says the most inherited delay is being generated.

| Rank | Carrier | Station | Turns | Median slack | Tight turns | Minutes saved (+10) | Efficiency |
|---|---|---|---:|---:|---:|---:|---:|
| 1 | Southwest | DEN | 386,648 | 13 min | 59.3% | 663,315 | 0.172 |
| 2 | American | DFW | 614,797 | 28 min | 25.8% | 633,898 | 0.103 |
| 3 | Southwest | LAS | 344,892 | 11 min | 55.5% | 581,669 | 0.169 |
| 4 | Southwest | DAL | 282,961 | 10 min | 59.1% | 460,450 | 0.163 |
| 5 | Delta | ATL | 929,353 | 40 min | 16.2% | 421,534 | 0.045 |

Read rank 5 against rank 1. Delta at Atlanta runs more than twice Southwest's
Denver turn volume and would save a third as many minutes from the same
intervention, because it already schedules 40 minutes of median slack against
Southwest's 13. Atlanta does not have a turn problem. Denver does.

**Owner.** Schedule Planning with the relevant station leadership.
**Effort.** Medium per station.

---

## R-4 — Report inherited share as a standing operational KPI

**Recommendation.** Add inherited share — inherited delay as a percentage of total
delay — to the monthly operations review, at carrier and station level, beside A14
and completion factor.

**Evidence.** The measure separates carriers cleanly and explains the ranking
better than the ranking itself does: Delta 28.4% inherited, Southwest 50.4%,
American 45.2% (Finding 6). A carrier whose inherited share is rising is
accumulating a schedule problem regardless of what its A14 is doing, and no
current standard report would show it.

**Owner.** Network Operations / BI.
**Effort.** Low — the field exists in `mart_carrier_monthly`.

---

# Testing R-1 before committing to it

R-1 reallocates real resourcing, so it should be piloted rather than rolled out.
The design below is what would be proposed to the sponsor.

**Hypothesis.** Additional station resourcing on morning departures reduces the
share of morning departures leaving 15+ minutes late, and the reduction propagates
into fewer downstream delayed legs on the same airframes.

**Unit of randomisation.** Station-day. Randomising individual flights is not
possible — the intervention is staffing, which applies to everything on the ramp
that morning.

**Primary metric.** Share of 05:00–11:00 departures with `dep_delay >= 15`.

**Secondary metric.** Mean downstream inherited minutes on the same airframes'
later legs — the mechanism check. R-1 only makes sense if the morning improvement
shows up downstream, and this is what would confirm the causal story rather than a
local effect.

**Guardrails.** Turn cost per departure; afternoon and evening on-time performance
at the same station, to confirm the resource was added rather than moved from
later in the day; completion factor, so the pilot cannot succeed by cancelling.

**Baseline and sizing.** Southwest morning departures at Denver run 17.1% late
across the window, at ~88 departures a day. Two-proportion test, 80% power,
α = 0.05 two-sided:

| Detectable effect | Sample per arm | Days per arm at DEN morning volume |
|---|---:|---:|
| 2 pp | 5,304 | ~60 |
| 3 pp | 2,297 | ~26 |
| 5 pp | 783 | ~9 |

**Recommended design.** Target a 3 pp effect, ~26 treated station-days plus an
equal control, run over a contiguous 8-week block to cover both weekday and
weekend rotation patterns.

**Analysis plan, fixed before the pilot runs.** Difference-in-differences against
the untreated stations over the same dates, which absorbs weather and system-wide
airspace events that hit both arms. One analysis at the end — no interim looks,
because repeatedly testing a running experiment inflates the false positive rate
well beyond the stated 5%. If a mid-pilot read is required for operational
reasons, an alpha-spending boundary is set in advance.

**What would make this fail honestly.** If morning departure performance improves
but downstream inherited minutes do not, the mechanism in Finding 2 is wrong at
station level and R-1 should be withdrawn even though its primary metric moved.
