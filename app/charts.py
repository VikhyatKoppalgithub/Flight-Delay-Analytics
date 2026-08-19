"""Plotly chart builders, sharing the palette used everywhere else in the project.

The two categorical slots carry a fixed meaning across the whole project and are
never reassigned: blue is delay that ORIGINATED with a flight, orange is delay
INHERITED from an earlier leg. A reader who learns the mapping on one chart can
carry it to every other one.
"""

from __future__ import annotations

import plotly.graph_objects as go

ROOT = "#2a78d6"       # categorical slot 1 — originated here
INHERITED = "#eb6834"  # categorical slot 2 — arrived from upstream
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"


def _base(fig: go.Figure, height: int = 320, ylabel: str = "", xlabel: str = "") -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=12, color=INK),
        showlegend=False,
        hoverlabel=dict(bgcolor=SURFACE, font_size=12, bordercolor=AXIS),
        bargap=0.28,
    )
    fig.update_xaxes(
        title=dict(text=xlabel, font=dict(size=11.5, color=MUTED)),
        showgrid=False, zeroline=False, linecolor=AXIS, linewidth=1,
        tickfont=dict(size=11.5, color=MUTED),
    )
    fig.update_yaxes(
        title=dict(text=ylabel, font=dict(size=11.5, color=MUTED)),
        gridcolor=GRID, gridwidth=1, zeroline=False, showline=False,
        tickfont=dict(size=11.5, color=MUTED),
    )
    return fig


def line(df, x, y, color=ROOT, ylabel="", xlabel="", height=320, yfmt=":.2f", threshold=None):
    fig = go.Figure(go.Scatter(
        x=df[x], y=df[y], mode="lines",
        line=dict(color=color, width=2, shape="linear"),
        hovertemplate=f"%{{x}}<br><b>%{{y{yfmt}}}</b><extra></extra>",
    ))
    if len(df):
        peak = df.loc[df[y].idxmax()]
        fig.add_trace(go.Scatter(
            x=[peak[x]], y=[peak[y]], mode="markers+text",
            marker=dict(color=color, size=9, line=dict(color=SURFACE, width=2)),
            text=[f"{peak[y]:.2f}"], textposition="top center",
            textfont=dict(size=12, color=INK), hoverinfo="skip",
        ))
    if threshold is not None:
        fig.add_hline(y=threshold, line=dict(color=AXIS, width=1.5),
                      annotation_text="Break-even", annotation_position="top right",
                      annotation_font=dict(size=11, color=MUTED))
    return _base(fig, height, ylabel, xlabel)


def bars(df, x, y, color=INHERITED, ylabel="", xlabel="", height=320, yfmt=":,.0f"):
    fig = go.Figure(go.Bar(
        x=df[x], y=df[y], marker=dict(color=color, line=dict(width=0)),
        hovertemplate=f"%{{x}}<br><b>%{{y{yfmt}}}</b><extra></extra>",
    ))
    return _base(fig, height, ylabel, xlabel)


def split_bar(root_minutes: float, inherited_minutes: float, height: int = 120) -> go.Figure:
    total = root_minutes + inherited_minutes
    fig = go.Figure()
    for value, name, colour in [
        (root_minutes, "Originated with this flight", ROOT),
        (inherited_minutes, "Inherited from an earlier leg", INHERITED),
    ]:
        share = 100 * value / total if total else 0
        fig.add_trace(go.Bar(
            x=[value], y=[""], orientation="h", name=name,
            marker=dict(color=colour, line=dict(color=SURFACE, width=2)),
            text=[f"{value/1e6:,.1f}M min · {share:.1f}%"],
            textposition="inside", insidetextanchor="middle",
            textfont=dict(color="#ffffff", size=13),
            hovertemplate=f"<b>{name}</b><br>%{{x:,.0f}} minutes<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    fig = _base(fig, height)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(showlegend=True, legend=dict(
        orientation="h", yanchor="bottom", y=1.02, x=0, traceorder="normal",
        font=dict(size=12, color=MUTED)))
    return fig


def rotation_timeline(legs, height_per_leg: int = 34) -> go.Figure:
    """One aircraft's day: scheduled block against what it actually flew.

    Each leg gets two bars on the same row -- the schedule in outline, the actual
    in solid -- so the drift between them accumulates visibly down the chart. A
    leg whose delay was inherited is drawn in orange, one that broke on its own
    in blue, which makes the moment a cascade starts easy to spot.
    """
    fig = go.Figure()
    for _, leg in legs.iterrows():
        row = f"{leg.leg_seq}. {leg.origin}→{leg.dest}"
        inherited = leg.inherited_delay_minutes > 0
        fig.add_trace(go.Bar(
            x=[leg.sched_minutes], y=[row], orientation="h", base=[leg.sched_offset],
            marker=dict(color="rgba(0,0,0,0)", line=dict(color=AXIS, width=1.5)),
            width=0.62, hovertemplate=(
                f"<b>Scheduled</b> {leg.sched_dep_hhmm}–{leg.sched_arr_hhmm}"
                f"<br>{leg.sched_minutes:.0f} min block<extra></extra>"),
            showlegend=False,
        ))
        fig.add_trace(go.Bar(
            x=[leg.actual_minutes], y=[row], orientation="h", base=[leg.actual_offset],
            marker=dict(color=INHERITED if inherited else ROOT, line=dict(width=0)),
            width=0.34, hovertemplate=(
                f"<b>Actual</b> {leg.actual_dep_hhmm}–{leg.actual_arr_hhmm}"
                f"<br>Departed {leg.dep_delay:+.0f} min, arrived {leg.arr_delay:+.0f} min"
                f"<br>Inherited {leg.inherited_delay_minutes:.0f} min"
                f" · slack {leg.turn_slack_minutes:.0f} min<extra></extra>"),
            showlegend=False,
        ))
    fig = _base(fig, height=max(180, height_per_leg * len(legs) + 90),
                xlabel="Minutes from the first scheduled departure of the day")
    fig.update_layout(barmode="overlay")
    fig.update_yaxes(autorange="reversed", gridcolor=SURFACE,
                     tickfont=dict(size=12, color=INK))
    fig.update_xaxes(showgrid=True, gridcolor=GRID)
    return fig
