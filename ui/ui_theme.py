"""
matchbox/ui/ui_theme.py — SSOT for Streamlit UI visual style.

Responsibilities:
- Expose one `inject()` function that emits a <style> block and sets Streamlit
  theme variables.
- Expose `icon(name, size=16)` that returns inline SVG strings from a tiny
  curated subset of the lucide icon set (so we don't add a dependency or
  fetch at runtime).
- Expose `card(title, body_html, footer_html=None, variant="default")` for
  consistent card rendering.
- Expose `badge(text, variant)` for pill-style status indicators.

Why a separate module:
- Single responsibility. ui.py stays focused on widgets + state.
- DRY. Every card shadow / border / font rule lives here, not sprinkled.
- Least privilege. This module cannot read the DB or the filesystem.
- Open-source hygiene. If we ever swap Streamlit for FastAPI + HTMX, the
  icons and color tokens port directly; only card() / inject() rewires.
"""

from __future__ import annotations

import streamlit as st


# ============================================================
# Design tokens (CSS custom properties). Change here, cascade everywhere.
# ============================================================
# Named after a deliberately small palette. One neutral scale (slate), one
# accent (indigo), three semantic (success / warning / danger). Matches the
# accessible contrast levels used in the CV template.

TOKENS_CSS = """
:root {
  /* Neutrals — slate scale */
  --mb-ink-900: #0f172a;   /* primary text */
  --mb-ink-700: #334155;   /* secondary text */
  --mb-ink-500: #64748b;   /* tertiary / captions */
  --mb-ink-300: #cbd5e1;   /* borders */
  --mb-ink-100: #f1f5f9;   /* background cells */
  --mb-ink-50:  #f8fafc;   /* page background */

  /* Accent — indigo */
  --mb-accent-600: #4f46e5;
  --mb-accent-500: #6366f1;
  --mb-accent-100: #e0e7ff;

  /* Semantic */
  --mb-success-600: #059669;
  --mb-success-100: #d1fae5;
  --mb-warn-600:    #d97706;
  --mb-warn-100:    #fef3c7;
  --mb-danger-600:  #dc2626;
  --mb-danger-100:  #fee2e2;

  /* Surfaces */
  --mb-card-bg:       #ffffff;
  --mb-card-border:   var(--mb-ink-300);
  --mb-card-shadow:   0 1px 2px rgba(15,23,42,0.06), 0 4px 12px rgba(15,23,42,0.04);
  --mb-card-hover:    0 2px 4px rgba(15,23,42,0.08), 0 8px 24px rgba(15,23,42,0.06);
  --mb-radius-md:     10px;
  --mb-radius-sm:     6px;

  /* Typography */
  --mb-font-sans: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
  --mb-font-mono: ui-monospace, "SF Mono", Monaco, Menlo, monospace;
}
"""


# ============================================================
# Global overrides on Streamlit's default chrome
# ============================================================

STREAMLIT_OVERRIDES_CSS = """
/* Page body */
html, body, [class*="st-"] {
  font-family: var(--mb-font-sans);
  color: var(--mb-ink-900);
}

/* Main container padding: tighter than Streamlit's default so our cards breathe */
section.main > div.block-container {
  padding-top: 2rem;
  padding-bottom: 4rem;
  max-width: 1280px;
}

/* Sidebar: softer background, sharper type */
section[data-testid="stSidebar"] {
  background-color: var(--mb-ink-50);
  border-right: 1px solid var(--mb-ink-300);
}
section[data-testid="stSidebar"] h3 {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--mb-ink-500);
  margin-top: 1.25rem;
  margin-bottom: 0.5rem;
}

/* Metric tiles */
div[data-testid="stMetric"] {
  background: var(--mb-card-bg);
  padding: 12px 16px;
  border: 1px solid var(--mb-card-border);
  border-radius: var(--mb-radius-md);
  box-shadow: var(--mb-card-shadow);
}
div[data-testid="stMetricLabel"] {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--mb-ink-500);
}
div[data-testid="stMetricValue"] {
  font-size: 1.5rem;
  font-weight: 600;
}

/* Buttons */
div.stButton > button {
  border-radius: var(--mb-radius-sm);
  border: 1px solid var(--mb-ink-300);
  background: var(--mb-card-bg);
  color: var(--mb-ink-900);
  padding: 6px 14px;
  font-weight: 500;
  font-size: 0.875rem;
  transition: all 120ms ease;
}
div.stButton > button:hover {
  border-color: var(--mb-accent-500);
  color: var(--mb-accent-600);
}
div.stButton > button[kind="primary"] {
  background: var(--mb-accent-600);
  border-color: var(--mb-accent-600);
  color: #fff;
}
div.stButton > button[kind="primary"]:hover {
  background: var(--mb-accent-500);
  border-color: var(--mb-accent-500);
  color: #fff;
}

/* Expanders — make them look like cards */
div[data-testid="stExpander"] {
  background: var(--mb-card-bg);
  border: 1px solid var(--mb-card-border);
  border-radius: var(--mb-radius-md);
  box-shadow: var(--mb-card-shadow);
  margin-bottom: 12px;
  transition: box-shadow 160ms ease;
}
div[data-testid="stExpander"]:hover {
  box-shadow: var(--mb-card-hover);
}
div[data-testid="stExpander"] > details > summary {
  font-size: 0.95rem;
  font-weight: 500;
  padding: 14px 18px;
}

/* Inputs — tighter borders */
div.stTextInput > div > div > input,
div.stNumberInput > div > div > input,
div.stTextArea textarea,
div.stSelectbox > div > div {
  border-radius: var(--mb-radius-sm);
  border: 1px solid var(--mb-ink-300);
}

/* Multiselect pills */
div[data-baseweb="tag"] {
  background-color: var(--mb-accent-100);
  color: var(--mb-accent-600);
  border-radius: var(--mb-radius-sm);
}

/* Custom card class for our Focus-mode cards */
.mb-card {
  background: var(--mb-card-bg);
  border: 1px solid var(--mb-card-border);
  border-radius: var(--mb-radius-md);
  box-shadow: var(--mb-card-shadow);
  padding: 20px 22px;
  margin-bottom: 14px;
  transition: box-shadow 160ms ease, border-color 160ms ease;
}
.mb-card:hover {
  box-shadow: var(--mb-card-hover);
}
.mb-card.tier-1 { border-left: 3px solid var(--mb-accent-600); }
.mb-card.tier-2 { border-left: 3px solid var(--mb-accent-500); }
.mb-card.tier-3 { border-left: 3px solid var(--mb-ink-300); }

.mb-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}
.mb-card-title {
  font-size: 1.05rem;
  font-weight: 600;
  line-height: 1.3;
  color: var(--mb-ink-900);
}
.mb-card-sub {
  font-size: 0.82rem;
  color: var(--mb-ink-500);
  margin-top: 2px;
}
.mb-card-score {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--mb-accent-600);
  white-space: nowrap;
}

.mb-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0;
  font-size: 0.8rem;
  color: var(--mb-ink-700);
}
.mb-card-meta .chip {
  background: var(--mb-ink-100);
  padding: 3px 9px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.mb-card-siblings {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--mb-ink-100);
  border-radius: var(--mb-radius-sm);
  font-size: 0.8rem;
  color: var(--mb-ink-700);
}

/* Badges (pill labels) */
.mb-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 500;
  line-height: 1.4;
}
.mb-badge.default  { background: var(--mb-ink-100);     color: var(--mb-ink-700); }
.mb-badge.success  { background: var(--mb-success-100); color: var(--mb-success-600); }
.mb-badge.warn     { background: var(--mb-warn-100);    color: var(--mb-warn-600); }
.mb-badge.danger   { background: var(--mb-danger-100);  color: var(--mb-danger-600); }
.mb-badge.accent   { background: var(--mb-accent-100);  color: var(--mb-accent-600); }

/* Inline icon sizing rule so card() and badge() can drop in SVGs */
.mb-icon { vertical-align: -2px; }

/* Section headers on main page */
h1.mb-page-title {
  font-size: 1.6rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  margin: 0 0 4px 0;
}
.mb-page-sub {
  color: var(--mb-ink-500);
  font-size: 0.85rem;
  margin-bottom: 28px;
}

/* Native st.container(border=True) — turn it into our card style */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--mb-card-bg);
  border: 1px solid var(--mb-card-border);
  border-radius: var(--mb-radius-md);
  box-shadow: var(--mb-card-shadow);
  padding: 14px 18px;
  margin-bottom: 10px;
  transition: box-shadow 160ms ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
  box-shadow: var(--mb-card-hover);
}

/* Score tile on the left of each card */
.mb-score-tile {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 44px;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--mb-accent-600);
  background: var(--mb-accent-100);
  border-radius: var(--mb-radius-sm);
  padding: 8px 4px;
}
.mb-score-tile.warn   { color: var(--mb-warn-600);   background: var(--mb-warn-100); }
.mb-score-tile.danger { color: var(--mb-danger-600); background: var(--mb-danger-100); }
.mb-score-tile.success{ color: var(--mb-success-600);background: var(--mb-success-100); }

/* Card summary typography */
.mb-row-title {
  font-size: 1.0rem;
  font-weight: 600;
  line-height: 1.3;
  color: var(--mb-ink-900);
  margin-bottom: 4px;
}
.mb-row-sub {
  font-size: 0.82rem;
  color: var(--mb-ink-500);
}

/* Nested sibling cards (one level deeper) */
.mb-sibling-wrap {
  margin-top: 8px;
  padding-left: 18px;
  border-left: 2px solid var(--mb-ink-300);
}
.mb-sibling-wrap .mb-row-title {
  font-size: 0.92rem;
}

/* Info strip (page-level one-liner explaining key actions) */
.mb-info-strip {
  background: var(--mb-ink-100);
  border-left: 3px solid var(--mb-accent-500);
  padding: 10px 14px;
  border-radius: var(--mb-radius-sm);
  font-size: 0.82rem;
  color: var(--mb-ink-700);
  margin-bottom: 18px;
  display: flex;
  align-items: center;
  gap: 8px;
}
"""


# ============================================================
# Icons — a curated subset of lucide (https://lucide.dev).
# Paths copied verbatim so there is no runtime dependency.
# Licensed ISC (lucide license). Keep attribution comment in code.
# ============================================================
# Usage: st.markdown(icon("star") + " Starred", unsafe_allow_html=True)

_ICON_PATHS = {
    # Navigation / state
    "star":         '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    "star-filled":  '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" fill="currentColor"/>',
    "check":        '<polyline points="20 6 9 17 4 12"/>',
    "x":            '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "chevron-down": '<polyline points="6 9 12 15 18 9"/>',
    # Pipeline meta
    "map-pin":      '<path d="M20 10c0 7-8 12-8 12s-8-5-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/>',
    "building":     '<rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01"/>',
    "briefcase":    '<rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    "dollar":       '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    "globe":        '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    "target":       '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    # Actions
    "file-text":    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
    "mail":         '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>',
    "send":         '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
    "link":         '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.72"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.72-1.72"/>',
    "filter":       '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    "refresh":      '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    "search":       '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    # Signals
    "trending-up":  '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
    "flame":        '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
    "alert":        '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "sparkles":     '<path d="M12 3l1.9 5.7L19 10l-5.1 1.3L12 17l-1.9-5.7L5 10l5.1-1.3L12 3z"/>',
    # More actions / navigation
    "external-link":'<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
    "chevron-right":'<polyline points="9 18 15 12 9 6"/>',
    "eye":          '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    "download":     '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    "info":         '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
    "flag":         '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
    "arrow-down":   '<line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/>',
    "plus":         '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "minus":        '<line x1="5" y1="12" x2="19" y2="12"/>',
    "list":         '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
    "thermometer":  '<path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4 4 0 1 0 5 0z"/>',
    "snowflake":    '<line x1="2" y1="12" x2="22" y2="12"/><line x1="12" y1="2" x2="12" y2="22"/><path d="m20 16-4-4 4-4"/><path d="m4 8 4 4-4 4"/><path d="m16 4-4 4-4-4"/><path d="m8 20 4-4 4 4"/>',
    # Lucide icons licensed ISC © 2024 Lucide Contributors
}


def icon(name: str, size: int = 16, stroke_width: float = 2.0, className: str = "mb-icon") -> str:
    """
    Return an inline SVG string for a lucide icon by name.
    Unknown name returns empty string (silent fail; never breaks UI).
    """
    path = _ICON_PATHS.get(name)
    if not path:
        return ""
    return (
        f'<svg class="{className}" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round">{path}</svg>'
    )


# ============================================================
# Components
# ============================================================

def score_tile(score: float | None) -> str:
    """Return HTML for the big coloured score tile shown at the left of each card."""
    if score is None:
        return '<div class="mb-score-tile" style="opacity:0.4">—</div>'
    variant = "success" if score >= 4.2 else ("" if score >= 4.0 else "warn" if score >= 3.5 else "danger")
    return f'<div class="mb-score-tile {variant}">{score:.2f}</div>'


def badge(text: str, variant: str = "default", icon_name: str | None = None) -> str:
    """Return HTML for a pill badge. variant in: default | success | warn | danger | accent."""
    ic = icon(icon_name, size=12) if icon_name else ""
    return f'<span class="mb-badge {variant}">{ic}{text}</span>'


def card(title_html: str, body_html: str, *, footer_html: str | None = None, tier: str | None = None) -> str:
    """
    Render a card wrapper. Pass pre-escaped HTML fragments.
    tier: "tier_1_dream" | "tier_2_target" | "tier_3_watchlist" | None → adds a coloured left border.
    """
    tier_class = ""
    if tier == "tier_1_dream":   tier_class = "tier-1"
    elif tier == "tier_2_target": tier_class = "tier-2"
    elif tier == "tier_3_watchlist": tier_class = "tier-3"

    footer = f'<div class="mb-card-footer">{footer_html}</div>' if footer_html else ""
    return (
        f'<div class="mb-card {tier_class}">'
        f'{title_html}'
        f'{body_html}'
        f'{footer}'
        f'</div>'
    )


# ============================================================
# Public entry point
# ============================================================

def inject(page_title: str = "Matchbox Pipeline", page_icon: str = "📋") -> None:
    """
    Emit the CSS block once per page load. Safe to call multiple times
    (Streamlit dedupes the <style> blocks).
    """
    # Note: st.set_page_config must be called by ui.py BEFORE this. We don't
    # call it here because inject() can be re-invoked after user interaction.
    st.markdown(
        f"<style>{TOKENS_CSS}\n{STREAMLIT_OVERRIDES_CSS}</style>",
        unsafe_allow_html=True,
    )
