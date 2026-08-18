# 06 — Assumptions and Limitations

What this analysis assumes, what it cannot see, and where it would break. Listed
because a finding whose limits are not stated is not a finding, it is a claim.

---

## Modelling assumptions

### The propagation model is a single subtraction
`predicted_inherited = max(0, inbound_delay − slack)` treats a turn as a queue with
a fixed service floor. It has no term for whether the crew was legal, whether the
gate was occupied, or whether a passenger connection was being held deliberately.

*Why it is defensible anyway:* it correlates at **0.784** with what the airlines
independently reported (Finding 2), which is high for a model this simple. It is
used to rank interventions, not to predict individual flights.

### Minimum feasible turn is inferred from behaviour
The 5th percentile of turns actually achieved stands in for a published minimum
turn time. If an operator has never been pushed at a station, its inferred floor
is too high and the station's slack is understated.

*Mitigation:* stations under 100 turns fall back to a carrier-level benchmark, and
under 2,000 turns they are excluded from `mart_turn_slack_opportunity` entirely.

### Twelve hours is the cutoff for a turn
Gaps over 720 minutes are treated as overnight sits that absorb any inbound delay.
The number is a judgement. Cascades would lengthen slightly at a higher threshold
and shorten at a lower one; the shape of Findings 3 and 4 does not depend on it.

### One cost rate across five years
$98.41 per block minute (A4A 2025) is applied to 2021–2025 alike, so cost
comparisons across years reflect minutes rather than fuel prices. Year-specific
rates would change every absolute dollar figure and none of the rankings.

---

## What the data cannot see

### Passengers
BTS is a flight-level feed. There are no itineraries, no connections, no load
factors. Misconnected passengers are plausibly the largest single cost of delay
and are entirely invisible here. **Every dollar figure in this project is a lower
bound on the cost of delay, not an estimate of it.**

### Crew
Crew legality cascades on its own timetable and can ground an on-time aircraft.
The December 2022 event in Finding 7 was substantially a crew-scheduling failure,
and this analysis can only observe its aircraft-side shadow.

### The cost of ground time
Buffer efficiency is expressed in delay minutes avoided per buffer minute spent.
Converting the denominator to dollars requires fleet utilisation economics that are
not in this feed, which is why R-2 stops at "do not add buffer broadly" rather than
claiming a net P&L number.

### Marketing carrier
BTS reports the operating carrier. A passenger flying "United 4801" operated by
Republic appears under Republic. Regional operators cannot be rolled back into the
brands their passengers actually booked, because operators such as SkyWest fly for
four different brands simultaneously and the feed does not say which flight belongs
to which. The carrier ranking in Finding 6 must be read with this in mind.

### International and cargo
Domestic scheduled passenger service only.

---

## Known defects in the source feed

Both were found by the test suite rather than by inspection, and both are flagged
in the warehouse rather than silently dropped.

| Defect | Count | Handling |
|---|---:|---|
| Flights arriving 15+ min late with all five cause fields reported as zero | 15 | `has_complete_attribution = false`; excluded from cause analysis |
| Flights with a negative scheduled block time (one has DFW–GCK landing 272 minutes before departure) | 14 | `is_schedule_valid = false`; no arrival instants derived |

Both are pinned by tests, so a future month arriving with thousands of either
fails the build instead of quietly entering the averages.

---

## Threats to the headline findings

**Finding 3 (morning multiplier) could be an artefact of exposure.** A morning
flight has more remaining legs in its day than an evening flight, so of course it
has more downstream legs to damage. This is not a confound — it is the mechanism —
but it means the finding should be read as "a delay early in an airframe's day is
more expensive," not "mornings are operationally worse." The amplification ratio,
which normalises by root delay size, is the safer of the two measures.

**Finding 4 depends on the buffer simulation being counterfactually valid.** Adding
slack to a schedule changes airline behaviour: aircraft utilisation falls, and
planners may re-optimise rotations to recover it. The simulation holds rotations
fixed. It answers "what would this slack have absorbed on these actual days,"
which is the right question for sizing, and not "what would the airline have done
with a looser schedule," which it cannot answer.

**Finding 7 has a control group but not a randomised one.** Southwest's rotation
structure differs from its peers in ways that correlate with the outcome. The
comparison establishes that the divergence was not weather — the storm hit both
arms and one recovered — and it does not isolate which of Southwest's
characteristics caused the collapse.
