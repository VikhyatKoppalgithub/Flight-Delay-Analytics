# 02 — KPI Definitions

Every metric used in this project, defined precisely enough that two analysts
computing it independently would get the same number. Where a definition embeds a
judgement, the judgement is stated rather than buried.

---

## Core operational KPIs

### A14 — On-Time Arrival Rate
**Definition:** Share of scheduled flights arriving fewer than 15 minutes after
scheduled gate arrival.
**Formula:** `flights with arr_delay < 15 / all scheduled flights`
**Denominator includes cancelled and diverted flights.** This is the single most
important choice in this document. The common alternative — computing A14 over
completed flights only — means an airline that cancels its 400 worst flights on a
bad day *improves* its reported on-time rate. Cancellations are the worst possible
outcome for a passenger and must not be a way to score better.
**Source field:** `fct_flight.is_on_time_a14`

### Completion Factor
**Definition:** Share of scheduled flights that operated and were not diverted.
**Formula:** `completed flights / scheduled flights`
**Why it is always reported next to A14:** the two can only be gamed against each
other. Read alone, either can be improved by damaging the other.
**Source field:** `mart_carrier_monthly.completion_factor_pct`

### Cancellation Rate
**Definition:** Share of scheduled flights cancelled, for any reason.
**Source field:** `mart_carrier_monthly.cancellation_rate_pct`

### P90 Arrival Delay
**Definition:** 90th percentile of arrival delay across completed flights.
**Why:** the mean arrival delay across the window is 6.6 minutes, which describes
nobody's experience. The P90 is 41 minutes. The distribution is heavily
right-skewed and the tail is where the cost and the customer damage live; a mean
reported without a percentile beside it actively misleads.

---

## Delay attribution KPIs

BTS requires carriers to attribute delay across five causes on any flight arriving
15 or more minutes late. Those five are regrouped here into two, because four of
them describe this flight and one describes a different one.

### Root Delay
**Definition:** Delay minutes originating with this flight.
**Formula:** `carrier_delay + weather_delay + nas_delay + security_delay`
**Source field:** `fct_flight.root_delay_minutes`

### Inherited Delay
**Definition:** Delay minutes this flight received because the aircraft arrived
late from its previous leg.
**Formula:** `late_aircraft_delay`
**Interpretation:** this is not a cause. It is displaced consequence. It is
addressable only at the leg that started it.
**Source field:** `fct_flight.inherited_delay_minutes`

### Inherited Share
**Definition:** `inherited / (root + inherited)`, as a percentage.
**What it tells you:** how much of a carrier's delay is self-inflicted downstream
of its own schedule design, versus caused by events on the day. A high inherited
share is a schedule signal, not an operations signal.

### Controllable Root Delay
**Definition:** `carrier_delay` alone — crew, maintenance, boarding, fuelling,
baggage, catering.
**Why it is separated from external root delay:** weather and airspace constraints
can be absorbed but not prevented. Carrier delay can be prevented, which makes it
the only root category a station team can be held to.

---

## Rotation and propagation KPIs

### Scheduled Turn
**Definition:** Minutes between an aircraft's scheduled arrival and its next
scheduled departure, at the same station, same airframe.
**Constraint:** valid only where the previous leg's destination equals this leg's
origin, and the gap is 0–720 minutes.

### Minimum Feasible Turn
**Definition:** 5th percentile of turns that operator has actually achieved at that
station, measured over the full window.
**Why measured rather than published:** minimum turn times are not in this feed,
and a published figure would be an assumption. The 5th percentile is what the
operator hits when pressed — an observed floor, not an aspiration.
**Fallback:** carrier-wide, then network-wide, where the station sample is under
100 turns.
**Source table:** `ref_min_turn`

### Turn Slack
**Definition:** `scheduled_turn − minimum_feasible_turn`, floored at zero.
**Interpretation:** the delay-absorbing capacity the schedule bought at this turn.

### Cascade Length
**Definition:** Number of consecutive subsequent legs flown by the same airframe
that each inherited delay from the one before.
**Source field:** `mart_cascade.downstream_legs`

### Amplification Ratio
**Definition:** `(root_delay + all downstream inherited delay) / root_delay`
**Interpretation:** total network minutes lost per minute lost by the originating
flight. A value of 2.4 means the delay more than doubled on its way through the day.

### Buffer Efficiency
**Definition:** Delay minutes avoided per buffer minute added, simulated by adding
N minutes of slack to every turn and re-running the propagation model.
**Formula:** `(predicted_base − predicted_plus_N) / (N × turns)`
**Break-even is 1.0.** Below it, the schedule time spent exceeds the delay time
saved. No hour of the operating day reaches 1.0 — see Finding 4.

---

## Cost KPIs

### Direct Cost of Delay
**Definition:** Delay minutes × $98.41.
**Source of the rate:** Airlines for America, 2025 average direct cost per aircraft
block minute, built from DOT Form 41 filings (crew, fuel, maintenance, ownership,
other direct). https://www.airlines.org/dataset/u-s-passenger-carrier-delay-costs/
**One rate is applied to all five years, deliberately.** Using each year's own rate
would blend a change in operational performance with a change in the price of jet
fuel. Holding it constant puts every year in 2025 dollars so the comparison is
about minutes, not markets.
**This is a lower bound.** It excludes passenger time, misconnects, rebooking,
compensation, crew rest cascades and lost future bookings. A4A estimates passenger
time cost separately and at comparable magnitude.
