"""Shared presentation layer: theme-aware chart styling, page chrome (header band,
cards, KPI tiles), the light/dark toggle, and cached data access.

Native theming lives in .streamlit/config.toml ([theme.light] / [theme.dark]).
The small amount of custom CSS below only targets elements we create with
explicit keys (`.st-key-*` classes): cards, KPI tiles, the hero tile and the
header band.
"""
from __future__ import annotations

import json
import re

import pandas as pd
import plotly.express as _px
import plotly.graph_objects as go
import streamlit as st

from dashboard import queries as q

FONT = "Inter, system-ui, -apple-system, Segoe UI, sans-serif"

# Validated reference palette (dataviz skill): separate steps per mode, same hue order.
PALETTES = {
    "light": dict(series=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
                  seq=["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
                  div_mid="#f0efec", ink="#14213D", ink2="#52514e", muted="#898781",
                  grid="rgba(20,33,61,0.08)", axis="#c3c2b7", hover_bg="#FFFFFF", mark_gap="#FFFFFF"),
    "dark": dict(series=["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
                 seq=["#1b2a48", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
                 div_mid="#383835", ink="#F0EFEC", ink2="#C3C2B7", muted="#9a988f",
                 grid="rgba(255,255,255,0.07)", axis="#3a4560", hover_bg="#172036", mark_gap="#172036"),
}
PAGE_PATHS = ["/", "/executive", "/customers", "/categories", "/experiment", "/opportunities"]


# ----------------------------------------------------------------- mode handling
def mode() -> str:
    """Active appearance. Right after the toggle reloads the page, the query
    param is authoritative (st.context.theme can lag on a session's first run)."""
    qp = st.query_params.get("theme")
    if qp in ("light", "dark"):
        return qp
    return st.context.theme.type or "light"


def pal() -> dict:
    return PALETTES[mode()]


def theme_toggle() -> None:
    """Small pill button that flips Streamlit's stored appearance for every page
    of this app and reloads. Uses Streamlit's own `stActiveTheme-<path>-v2`
    localStorage key, so the native Settings > Theme menu stays in sync."""
    target = "light" if mode() == "dark" else "dark"
    icon = ":material/light_mode:" if target == "light" else ":material/dark_mode:"
    if st.button(target.capitalize(), icon=icon, key="theme_toggle", help=f"Switch to {target} mode"):
        value = json.dumps(target.capitalize())
        st.html(f"""<script>
            for (const p of {json.dumps(PAGE_PATHS)}) {{
              window.localStorage.setItem(`stActiveTheme-${{p}}-v2`, {json.dumps(value)});
            }}
            const u = new URL(window.location.href);
            u.searchParams.set("theme", "{target}");
            window.location.replace(u.toString());
        </script>""", unsafe_allow_javascript=True)


# ----------------------------------------------------------------- CSS (keyed elements only)
def inject_css() -> None:
    dark = mode() == "dark"
    card_bg = "#172036" if dark else "#FFFFFF"
    border = "#26314D" if dark else "#E9E6DF"
    shadow = ("0 1px 2px rgba(0,0,0,.35), 0 10px 28px rgba(0,0,0,.28)" if dark
              else "0 1px 2px rgba(20,33,61,.05), 0 10px 28px rgba(20,33,61,.07)")
    band = ("linear-gradient(120deg,#1B2747 0%,#22325C 55%,#2C3F72 100%)" if dark
            else "linear-gradient(120deg,#14213D 0%,#1E2D52 55%,#2A3D6E 100%)")
    st.html(f"""<style>
    :root {{ --fl-card:{card_bg}; --fl-border:{border}; --fl-shadow:{shadow}; }}
    [class*="st-key-card-"], [class*="st-key-kpi-"], .st-key-cfg {{
        background: var(--fl-card) !important; border: 1px solid var(--fl-border) !important;
        border-radius: 18px !important; box-shadow: var(--fl-shadow); }}
    [class*="st-key-kpi-"] {{ padding: 4px 6px; transition: transform .15s ease, box-shadow .15s ease; }}
    [class*="st-key-kpi-"]:hover {{ transform: translateY(-2px); }}
    .st-key-kpi-hero {{ background: linear-gradient(135deg,#FF9F5A 0%,#F57328 45%,#E8590C 100%) !important;
        border: none !important; box-shadow: 0 12px 30px rgba(232,89,12,.35); }}
    .st-key-kpi-hero, .st-key-kpi-hero * {{ color: #FFFFFF !important; }}
    .st-key-pagehead {{ background: {band}; border-radius: 22px; padding: 22px 26px 18px 26px;
        box-shadow: 0 14px 34px rgba(20,33,61,.22); }}
    .st-key-pagehead h1, .st-key-pagehead h1 *, .st-key-pagehead p {{ color: #FFFFFF !important; }}
    .st-key-pagehead .stMarkdownBadge, .st-key-pagehead .stMarkdownBadge * {{
        background: rgba(255,255,255,.13) !important; color: #FFFFFF !important; }}
    .st-key-theme_toggle button {{ background: rgba(255,255,255,.10) !important; color: #FFFFFF !important;
        border: 1px solid rgba(255,255,255,.28) !important; }}
    .st-key-theme_toggle button:hover {{ background: rgba(255,255,255,.20) !important; }}
    </style>""")


# ----------------------------------------------------------------- charts
def style(fig: go.Figure, height: int = 320, legend: bool = True, hover: str = "x unified") -> go.Figure:
    """Card-friendly Plotly styling in the active mode: transparent background,
    recessive axes, thin marks, validated categorical colors."""
    p = pal()
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=4, r=4, t=36 if legend else 8, b=4),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=p["ink2"], size=12), title=None, colorway=p["series"],
        hovermode=hover, showlegend=legend,
        hoverlabel=dict(bgcolor=p["hover_bg"], bordercolor=p["axis"], font=dict(family=FONT, color=p["ink"])),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title=None, font=dict(size=12)),
    )
    fig.update_xaxes(showgrid=False, automargin=True, linecolor=p["axis"], tickfont=dict(color=p["muted"]),
                     title_font=dict(color=p["muted"]))
    fig.update_yaxes(gridcolor=p["grid"], automargin=True, zeroline=False, tickfont=dict(color=p["muted"]),
                     title_font=dict(color=p["muted"]))
    fig.update_traces(selector=dict(type="bar"), marker_line_color=p["mark_gap"], marker_line_width=1.5)
    fig.update_traces(selector=dict(type="scatter", mode="lines"), line_width=2.5)
    fig.update_traces(selector=dict(type="scatter", mode="lines+markers"), line_width=2.5, marker_size=6)
    return fig


def plot(fig: go.Figure, alt: str, **kw) -> None:
    st.plotly_chart(style(fig, **kw), config={"displayModeBar": False}, alt=alt, theme=None)


class _ThemedPX:
    """Plotly Express proxy that injects the active mode's categorical palette
    (per call, so concurrent light/dark sessions never share global state)."""

    def __getattr__(self, name):
        fn = getattr(_px, name)

        def wrapped(*a, **kw):
            kw.setdefault("color_discrete_sequence", pal()["series"])
            return fn(*a, **kw)
        return wrapped


px = _ThemedPX()


def diverging() -> list:
    p = pal()
    return [[0, "#d03b3b"], [0.5, p["div_mid"]], [1, p["series"][0]]]


# ----------------------------------------------------------------- layout pieces
def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


def card(title: str, icon: str, caption: str | None = None, key: str | None = None):
    """Rounded, shadowed card with a titled header; use as a context manager."""
    c = st.container(border=True, key=f"card-{key or _slug(title)}")
    c.subheader(title, icon=icon)
    if caption:
        c.caption(caption)
    return c


def kpi(label: str, value, delta=None, *, hero: bool = False, key: str | None = None, **kw) -> None:
    """KPI tile. `hero=True` renders the single highlighted accent tile."""
    with st.container(key="kpi-hero" if hero else f"kpi-{key or _slug(label)}"):
        st.metric(label, value, delta, **kw)


def header(title: str, icon: str, subtitle: str, badges: list[tuple[str, str, str]]) -> None:
    """Bold page-header band: title + context badges on the left, theme toggle on the right."""
    inject_css()
    with st.container(key="pagehead", horizontal=True, vertical_alignment="center"):
        with st.container(gap="small"):
            st.title(title, icon=icon)
            with st.container(horizontal=True, gap="small"):
                for label, color, b_icon in badges:
                    st.badge(label, color=color, icon=b_icon)
            st.caption(subtitle)
        with st.container(width="content"):
            theme_toggle()


# ----------------------------------------------------------------- formatting & data
def pct(x, d=1):
    return "–" if x is None or pd.isna(x) else f"{100 * x:.{d}f}%"


def brl(x, d=0):
    if x is None or pd.isna(x):
        return "–"
    if abs(x) >= 1e6:
        return f"R$ {x / 1e6:,.2f}M"
    return f"R$ {x:,.{d}f}"


@st.cache_data(ttl=600, show_spinner=False)
def cached(fn_name: str, *args):
    return getattr(q, fn_name)(*args)


def filters() -> tuple:
    f = st.session_state["filters"]
    return f["start"], f["end"], f["state"]


def window_badges(start, end, state) -> list[tuple[str, str, str]]:
    return [(f"{start:%b %Y} – {end:%b %Y}", "blue", ":material/calendar_month:"),
            (f"State: {state}", "gray", ":material/location_on:"),
            ("Olist e-commerce proxy", "orange", ":material/database:")]
