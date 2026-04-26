from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from textwrap import dedent
from urllib.parse import urlencode

import folium
import pandas as pd
import requests
import streamlit as st
from streamlit.components.v1 import html as components_html

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import IMAGES_DIR, settings
from app.copilot_router import QUESTION_EXAMPLES, answer_heatstop_copilot
from app.providers.imagery import _find_image_path, analyze_image
from app.services.corridor_intelligence import generate_waiting_zone_intelligence
from app.services.planner import recommend_action_summary, recommend_intervention, summarize_contributors


st.set_page_config(page_title="HeatStop AI", page_icon="☀️", layout="wide")

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap');
      :root {
        --bg: #0b1220;
        --bg-soft: #111a2d;
        --bg-panel: rgba(14, 24, 43, 0.92);
        --bg-panel-2: rgba(18, 30, 52, 0.88);
        --bg-panel-3: rgba(11, 18, 32, 0.96);
        --line: rgba(132, 156, 192, 0.18);
        --line-strong: rgba(132, 156, 192, 0.28);
        --text: #ecf3ff;
        --muted: #9fb1cb;
        --low: #19c3a5;
        --med: #f3ad3d;
        --high: #ff6b3d;
        --critical: #ff4d5a;
        --shadow: 0 20px 60px rgba(2, 8, 23, 0.42);
      }
      html, body, [class*="css"] {
        font-family: 'Space Grotesk', sans-serif;
      }
      .stApp {
        color: var(--text);
        background:
          radial-gradient(circle at top left, rgba(255, 107, 61, 0.18), transparent 24%),
          radial-gradient(circle at 85% 12%, rgba(25, 195, 165, 0.14), transparent 20%),
          linear-gradient(145deg, #070d18 0%, #0b1220 42%, #10192b 100%);
      }
      .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
      }
      .stApp,
      .stApp p,
      .stApp label,
      .stApp span,
      .stApp div,
      .stApp .stMarkdown,
      .stApp [data-testid="stMarkdownContainer"],
      .stApp [data-testid="stCaptionContainer"],
      .stApp [data-testid="stMetricLabel"],
      .stApp [data-testid="stMetricValue"],
      .stApp [data-testid="stMetricDelta"] {
        color: var(--text);
      }
      .stApp h1,
      .stApp h2,
      .stApp h3,
      .stApp h4,
      .stApp h5,
      .stApp h6 {
        color: var(--text);
      }
      .stApp a {
        color: #8fdcff;
      }
      .stApp [data-testid="stAlertContainer"] {
        background: rgba(18, 30, 52, 0.86);
        border: 1px solid var(--line);
      }
      .command-shell {
        padding: 1.6rem 1.7rem 1.4rem 1.7rem;
        border-radius: 28px;
        background:
          linear-gradient(135deg, rgba(255, 107, 61, 0.08), transparent 30%),
          linear-gradient(135deg, rgba(12, 19, 34, 0.98) 0%, rgba(14, 24, 43, 0.94) 100%);
        border: 1px solid rgba(132, 156, 192, 0.16);
        box-shadow: var(--shadow);
        margin-bottom: 1rem;
      }
      .eyebrow {
        display: inline-block;
        padding: 0.34rem 0.65rem;
        border-radius: 999px;
        font-size: 0.78rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        background: rgba(25, 195, 165, 0.12);
        border: 1px solid rgba(25, 195, 165, 0.18);
        color: #8ef0de;
      }
      .hero-title {
        margin: 0.85rem 0 0.35rem 0;
        font-size: 2.55rem;
        line-height: 1.02;
        letter-spacing: -0.04em;
      }
      .hero-subtitle {
        color: var(--muted);
        max-width: 58rem;
        font-size: 1rem;
        line-height: 1.55;
      }
      .insight-card {
        margin-top: 1.15rem;
        padding: 1rem 1.05rem;
        border-radius: 20px;
        background: rgba(15, 25, 42, 0.86);
        border: 1px solid rgba(255, 107, 61, 0.14);
      }
      .scope-card {
        padding: 1rem 1.02rem;
        min-height: 138px;
        border-radius: 20px;
        background: linear-gradient(180deg, rgba(16, 27, 46, 0.95), rgba(10, 17, 31, 0.98));
        border: 1px solid rgba(132, 156, 192, 0.14);
        box-shadow: var(--shadow);
      }
      .scope-card-title {
        margin-top: 0.55rem;
        font-size: 1rem;
        font-weight: 700;
      }
      .scope-card-text {
        margin-top: 0.45rem;
        color: var(--muted);
        font-size: 0.9rem;
        line-height: 1.5;
      }
      .insight-label {
        color: #ffb898;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      .insight-text {
        margin-top: 0.35rem;
        color: var(--text);
        font-size: 1rem;
        line-height: 1.5;
      }
      .control-card,
      .panel-card,
      .map-shell,
      .stop-shell {
        background: var(--bg-panel);
        border: 1px solid var(--line);
        border-radius: 24px;
        box-shadow: var(--shadow);
      }
      .control-card {
        padding: 1rem 1rem 0.5rem 1rem;
        min-height: 100%;
      }
      .control-label,
      .section-kicker,
      .kpi-label {
        color: var(--muted);
        font-size: 0.76rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      .weather-pill-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
      }
      .weather-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.42rem 0.72rem;
        border-radius: 999px;
        font-size: 0.83rem;
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(132, 156, 192, 0.18);
        color: var(--text);
      }
      .weather-pill.heat {
        border-color: rgba(255, 107, 61, 0.22);
        color: #ffceb7;
      }
      .weather-pill.source {
        border-color: rgba(25, 195, 165, 0.2);
        color: #b9fff3;
      }
      .weather-pill.time {
        border-color: rgba(243, 173, 61, 0.2);
        color: #ffe4af;
      }
      .stApp [data-baseweb="select"] > div {
        background: rgba(12, 19, 34, 0.88) !important;
        border: 1px solid rgba(132, 156, 192, 0.2) !important;
        border-radius: 16px !important;
        color: var(--text) !important;
      }
      .stApp [data-baseweb="select"] input,
      .stApp [data-baseweb="select"] * {
        color: var(--text) !important;
      }
      .stApp .stButton > button,
      .stApp [data-testid="stFormSubmitButton"] > button,
      .stApp [data-testid="stFormSubmitButton"] button,
      .stApp button[kind="secondaryFormSubmit"],
      .stApp button[kind="primaryFormSubmit"] {
        width: 100%;
        min-height: 3.1rem;
        border-radius: 16px;
        border: 1px solid rgba(255, 107, 61, 0.25) !important;
        background: linear-gradient(135deg, #ff6238 0%, #ff8e3c 100%) !important;
        color: #fff8f2 !important;
        font-weight: 700;
        box-shadow: 0 14px 30px rgba(255, 107, 61, 0.22);
      }
      .stApp .stButton > button:hover,
      .stApp [data-testid="stFormSubmitButton"] > button:hover,
      .stApp [data-testid="stFormSubmitButton"] button:hover,
      .stApp button[kind="secondaryFormSubmit"]:hover,
      .stApp button[kind="primaryFormSubmit"]:hover {
        background: linear-gradient(135deg, #ff744f 0%, #ffa14f 100%) !important;
        border-color: rgba(255, 107, 61, 0.4) !important;
        color: #fffdfb !important;
      }
      .stApp .stButton > button:disabled,
      .stApp .stButton > button[disabled],
      .stApp [data-testid="stFormSubmitButton"] > button:disabled,
      .stApp [data-testid="stFormSubmitButton"] > button[disabled],
      .stApp [data-testid="stFormSubmitButton"] button:disabled,
      .stApp [data-testid="stFormSubmitButton"] button[disabled],
      .stApp button[kind="secondaryFormSubmit"]:disabled,
      .stApp button[kind="secondaryFormSubmit"][disabled],
      .stApp button[kind="primaryFormSubmit"]:disabled,
      .stApp button[kind="primaryFormSubmit"][disabled] {
        background: rgba(255, 142, 60, 0.42) !important;
        color: rgba(255, 244, 236, 0.82) !important;
        border-color: rgba(255, 107, 61, 0.12) !important;
        box-shadow: none !important;
        opacity: 1 !important;
      }
      .stApp [data-testid="stTextInput"] input,
      .stApp [data-testid="stTextArea"] textarea,
      .stApp [data-testid="stFileUploaderDropzone"] {
        background: rgba(10, 17, 31, 0.92) !important;
        color: var(--text) !important;
        border: 1px solid rgba(132, 156, 192, 0.2) !important;
        border-radius: 16px !important;
      }
      .stApp [data-testid="stTextInput"] input::placeholder,
      .stApp [data-testid="stTextArea"] textarea::placeholder {
        color: rgba(159, 177, 203, 0.76);
      }
      .stApp [data-testid="stFileUploaderDropzone"] button,
      .stApp [data-testid="stFileUploaderDropzone"] [data-baseweb="button"] {
        background: rgba(255, 255, 255, 0.06) !important;
        color: var(--text) !important;
        border: 1px solid rgba(132, 156, 192, 0.18) !important;
        border-radius: 12px !important;
        box-shadow: none !important;
      }
      .stApp [data-testid="stFileUploaderDropzone"] small,
      .stApp [data-testid="stFileUploaderDropzoneInstructions"] span,
      .stApp [data-testid="stFileUploaderDropzoneInstructions"] small {
        color: var(--muted) !important;
      }
      .kpi-grid {
        margin-top: 0.35rem;
      }
      .kpi-card {
        padding: 1.05rem 1.08rem;
        min-height: 148px;
        border-radius: 22px;
        background: linear-gradient(180deg, rgba(17, 28, 48, 0.96) 0%, rgba(12, 19, 34, 0.98) 100%);
        border: 1px solid var(--line);
        box-shadow: var(--shadow);
        position: relative;
        overflow: hidden;
      }
      .kpi-card::before {
        content: "";
        position: absolute;
        inset: 0 auto 0 0;
        width: 4px;
        background: var(--accent, var(--low));
      }
      .kpi-icon {
        font-size: 0.74rem;
        color: var(--accent, var(--low));
        text-transform: uppercase;
        letter-spacing: 0.1em;
      }
      .kpi-value {
        margin-top: 0.75rem;
        font-size: 2rem;
        line-height: 1;
        letter-spacing: -0.04em;
      }
      .kpi-subtitle {
        margin-top: 0.55rem;
        color: var(--muted);
        font-size: 0.92rem;
        line-height: 1.45;
      }
      .section-shell {
        margin-top: 1.1rem;
      }
      .section-head {
        display: flex;
        align-items: end;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0.8rem;
      }
      .section-title {
        font-size: 1.45rem;
        letter-spacing: -0.03em;
      }
      .section-text {
        color: var(--muted);
        max-width: 40rem;
        line-height: 1.5;
      }
      .map-shell,
      .panel-card,
      .stop-shell {
        padding: 1.05rem;
      }
      .action-card {
        padding: 0.95rem 1rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(132, 156, 192, 0.14);
        margin-bottom: 0.75rem;
      }
      .action-card.critical {
        border-color: rgba(255, 77, 90, 0.35);
        background: linear-gradient(135deg, rgba(255, 77, 90, 0.1), rgba(255, 255, 255, 0.03));
      }
      .action-topline {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
      }
      .action-stop {
        font-size: 1rem;
        font-weight: 700;
      }
      .score-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0.3rem 0.6rem;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 700;
        color: #fff;
        background: var(--badge, var(--med));
      }
      .action-reason,
      .action-summary {
        margin-top: 0.42rem;
        color: var(--muted);
        line-height: 1.45;
      }
      .stop-rating-hero {
        margin-top: 0.75rem;
        padding: 0.9rem 1rem;
        border-radius: 18px;
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.025));
        border: 1px solid color-mix(in srgb, var(--rating-color, var(--teal)) 35%, rgba(255, 255, 255, 0.08));
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
      }
      .stop-rating-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
      }
      .stop-rating-title {
        font-size: 0.76rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--muted);
        font-weight: 700;
      }
      .stop-rating-band {
        display: inline-flex;
        align-items: center;
        padding: 0.28rem 0.62rem;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 700;
        color: #fff;
        background: var(--rating-color, var(--teal));
      }
      .stop-rating-value-row {
        display: flex;
        align-items: baseline;
        gap: 0.22rem;
        margin-top: 0.45rem;
      }
      .stop-rating-value {
        font-size: 2.2rem;
        line-height: 1;
        font-weight: 800;
        color: #f8fbff;
      }
      .stop-rating-scale {
        font-size: 1.05rem;
        color: var(--muted);
        font-weight: 700;
      }
      .stop-rating-note {
        margin-top: 0.34rem;
        color: var(--muted);
        font-size: 0.84rem;
        line-height: 1.45;
      }
      .action-links,
      .builder-action-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
        margin-top: 0.8rem;
      }
      .action-link,
      .builder-action-link {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0.52rem 0.8rem;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 700;
        text-decoration: none !important;
        border: 1px solid rgba(132, 156, 192, 0.2);
        background: rgba(255, 255, 255, 0.04);
        color: var(--text) !important;
        transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
      }
      .action-link:hover,
      .builder-action-link:hover {
        transform: translateY(-1px);
        border-color: rgba(143, 220, 255, 0.42);
        background: rgba(143, 220, 255, 0.08);
      }
      .builder-action-link.primary,
      .action-link.primary {
        border-color: rgba(255, 107, 61, 0.34);
        background: rgba(255, 107, 61, 0.12);
      }
      .builder-action-link.secondary,
      .action-link.secondary {
        border-color: rgba(25, 195, 165, 0.3);
        background: rgba(25, 195, 165, 0.1);
      }
      .builder-action-link.ghost,
      .action-link.ghost {
        border-color: rgba(132, 156, 192, 0.18);
        background: rgba(255, 255, 255, 0.03);
      }
      .ranked-table-wrap {
        margin-top: 0.9rem;
      }
      .risk-chip-row,
      .meta-chip-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
      }
      .risk-chip,
      .meta-chip {
        display: inline-flex;
        align-items: center;
        padding: 0.34rem 0.62rem;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 600;
      }
      .risk-chip {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(132, 156, 192, 0.16);
      }
      .risk-chip.high {
        color: #ffd7d5;
        border-color: rgba(255, 77, 90, 0.34);
        background: rgba(255, 77, 90, 0.12);
      }
      .risk-chip.med {
        color: #ffe2b0;
        border-color: rgba(243, 173, 61, 0.32);
        background: rgba(243, 173, 61, 0.12);
      }
      .risk-chip.low {
        color: #baffef;
        border-color: rgba(25, 195, 165, 0.28);
        background: rgba(25, 195, 165, 0.12);
      }
      .meta-chip {
        color: var(--muted);
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(132, 156, 192, 0.12);
      }
      .stop-shell {
        margin-top: 1rem;
      }
      .stop-image-shell {
        padding: 1rem;
        border-radius: 22px;
        background: linear-gradient(180deg, rgba(17, 28, 48, 0.98), rgba(10, 17, 31, 0.98));
        border: 1px solid rgba(132, 156, 192, 0.14);
      }
      .image-empty {
        min-height: 360px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: flex-start;
        gap: 0.75rem;
        padding: 1.25rem;
        border-radius: 20px;
        background:
          linear-gradient(135deg, rgba(255, 107, 61, 0.12), transparent 45%),
          rgba(9, 15, 27, 0.94);
        border: 1px dashed rgba(132, 156, 192, 0.22);
      }
      .image-empty h4 {
        margin: 0;
      }
      .image-empty p {
        margin: 0;
        color: var(--muted);
        line-height: 1.5;
      }
      .intelligence-header {
        padding: 0.95rem 1rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(132, 156, 192, 0.12);
        margin-bottom: 0.9rem;
      }
      .intelligence-title {
        margin: 0;
        font-size: 1.5rem;
      }
      .intelligence-sub {
        margin-top: 0.3rem;
        color: var(--muted);
      }
      .score-shell {
        display: grid;
        grid-template-columns: 132px 1fr;
        gap: 1rem;
        align-items: center;
        padding: 1rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(132, 156, 192, 0.12);
      }
      .score-ring {
        width: 120px;
        height: 120px;
        border-radius: 50%;
        display: grid;
        place-items: center;
        background: conic-gradient(var(--ring-color, var(--med)) calc(var(--score) * 1%), rgba(255,255,255,0.08) 0);
      }
      .score-ring::after {
        content: "";
        width: 88px;
        height: 88px;
        border-radius: 50%;
        background: #0b1220;
        border: 1px solid rgba(132, 156, 192, 0.12);
      }
      .score-ring-value {
        position: relative;
        margin-top: -88px;
        text-align: center;
        z-index: 2;
      }
      .score-ring-value strong {
        display: block;
        font-size: 1.8rem;
        line-height: 1;
      }
      .score-ring-value span {
        color: var(--muted);
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      .severity-meter {
        margin-top: 0.85rem;
      }
      .severity-track {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 0.35rem;
      }
      .severity-segment {
        height: 10px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.08);
      }
      .severity-segment.on.low { background: var(--low); }
      .severity-segment.on.med { background: var(--med); }
      .severity-segment.on.high { background: var(--high); }
      .severity-segment.on.critical { background: var(--critical); }
      .severity-label {
        margin-top: 0.55rem;
        color: var(--muted);
        font-size: 0.86rem;
      }
      .planner-card,
      .detail-note,
      .detail-subpanel {
        padding: 0.95rem 1rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(132, 156, 192, 0.12);
      }
      .detail-note {
        border-left: 3px solid rgba(255, 107, 61, 0.8);
      }
      .stTabs [data-baseweb="tab-list"] {
        gap: 0.4rem;
        background: rgba(255, 255, 255, 0.03);
        padding: 0.35rem;
        border-radius: 16px;
        border: 1px solid rgba(132, 156, 192, 0.12);
      }
      .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 12px;
        color: var(--muted);
        padding: 0.55rem 0.9rem;
      }
      .stTabs [aria-selected="true"] {
        background: rgba(255, 107, 61, 0.14) !important;
        color: #fff4ee !important;
      }
      .stDataFrame {
        background: rgba(11, 18, 32, 0.88);
        border: 1px solid rgba(132, 156, 192, 0.12);
        border-radius: 18px;
        overflow: hidden;
      }
      .rider-shell {
        padding: 1.1rem;
        border-radius: 24px;
        background:
          linear-gradient(135deg, rgba(25, 195, 165, 0.08), transparent 28%),
          linear-gradient(180deg, rgba(17, 28, 48, 0.96), rgba(10, 17, 31, 0.98));
        border: 1px solid rgba(132, 156, 192, 0.16);
        box-shadow: var(--shadow);
      }
      .rider-mini-card {
        padding: 0.9rem 1rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(132, 156, 192, 0.12);
        min-height: 100%;
      }
      .rider-mini-value {
        margin-top: 0.3rem;
        font-size: 1.3rem;
        font-weight: 700;
      }
      .rider-mini-text {
        margin-top: 0.35rem;
        color: var(--muted);
        line-height: 1.5;
      }
      .relief-card {
        padding: 0.95rem 1rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(132, 156, 192, 0.14);
        margin-bottom: 0.7rem;
      }
      .relief-name {
        font-size: 1rem;
        font-weight: 700;
      }
      .relief-meta {
        margin-top: 0.3rem;
        color: var(--muted);
        line-height: 1.45;
      }
      .builder-note {
        margin-top: 0.5rem;
        color: var(--muted);
        line-height: 1.55;
      }
      .copilot-response-card {
        padding: 1rem 1.05rem;
        border-radius: 18px;
        background: linear-gradient(135deg, rgba(25, 195, 165, 0.1), rgba(255, 255, 255, 0.03));
        border: 1px solid rgba(25, 195, 165, 0.18);
      }
      .copilot-headline {
        font-size: 1.15rem;
        font-weight: 700;
        line-height: 1.45;
      }
      .copilot-summary {
        margin-top: 0.45rem;
        color: var(--muted);
        line-height: 1.6;
      }
      .footer-note {
        color: var(--muted);
        font-size: 0.9rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


API_URL = settings.api_url.rstrip("/")
COMMUNITY_UPLOAD_SOURCE = "community_upload"
ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def api_get(path: str, params: dict | None = None) -> dict:
    response = requests.get(f"{API_URL}{path}", params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def api_post(path: str, params: dict | None = None) -> dict:
    response = requests.post(f"{API_URL}{path}", params=params, timeout=180)
    response.raise_for_status()
    return response.json()


def manifest_path() -> Path:
    return IMAGES_DIR / "manifest.csv"


def load_local_manifest() -> pd.DataFrame:
    path = manifest_path()
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "stop_id",
                "file_name",
                "source_url",
                "contributor_name",
                "contributor_note",
                "uploaded_at",
            ]
        )
    return pd.read_csv(path, dtype=str).fillna("")


def local_image_record(stop_id: str) -> dict | None:
    image_path = _find_image_path(str(stop_id), IMAGES_DIR)
    if image_path is None or not image_path.exists():
        return None

    manifest = load_local_manifest()
    metadata: dict[str, str] = {}
    if not manifest.empty and {"stop_id", "file_name"}.issubset(manifest.columns):
        matches = manifest.loc[
            (manifest["stop_id"] == str(stop_id)) & (manifest["file_name"] == image_path.name)
        ]
        if not matches.empty:
            metadata = matches.iloc[0].to_dict()

    return {
        "image_path": str(image_path),
        "image_provider": "Community upload" if metadata.get("source_url") == COMMUNITY_UPLOAD_SOURCE else "Local file",
        "image_capture_date": metadata.get("uploaded_at") or None,
        "image_author": metadata.get("contributor_name") or None,
        "image_attribution_url": metadata.get("source_url") if metadata.get("source_url") not in {"", COMMUNITY_UPLOAD_SOURCE} else None,
        "contributor_note": metadata.get("contributor_note") or None,
    }


def latest_community_upload_for_stop(stop_id: str) -> dict | None:
    manifest = load_local_manifest()
    if manifest.empty or "stop_id" not in manifest.columns:
        return None
    subset = manifest.loc[
        (manifest["stop_id"] == str(stop_id)) & (manifest["source_url"] == COMMUNITY_UPLOAD_SOURCE)
    ].copy()
    if subset.empty:
        return None
    subset["uploaded_at_ts"] = pd.to_datetime(subset["uploaded_at"], utc=True, errors="coerce")
    subset = subset.sort_values("uploaded_at_ts", ascending=False)
    record = subset.iloc[0].to_dict()
    record["uploaded_at_ts"] = subset.iloc[0]["uploaded_at_ts"]
    return record


def shelter_override_state(stop: dict, local_record: dict | None) -> dict:
    official_shelter = stop.get("has_shelter")
    verified_photo = bool(local_record and local_record.get("image_provider") == "Community upload")
    canopy_visible = bool(stop.get("shelter_image_estimate")) if verified_photo and pd.notna(stop.get("shelter_image_estimate")) else False
    conflict = official_shelter is False and canopy_visible
    return {
        "official_shelter": official_shelter,
        "verified_photo": verified_photo,
        "canopy_visible": canopy_visible,
        "conflict": conflict,
        "selected_stop_override": bool(conflict),
        "selected_stop_shelter_present": True if conflict else official_shelter,
    }


def image_source_profile(provider: str | None) -> dict[str, str]:
    provider = str(provider or "").strip()
    if provider == "Community upload":
        return {
            "label": "Verified waiting-point photo",
            "status": "Highest confidence",
            "description": "Community-submitted photo captured specifically for this waiting area.",
        }
    if provider == "Local file":
        return {
            "label": "Local evidence photo",
            "status": "Manual local evidence",
            "description": "Local waiting-area image supplied outside the public imagery workflow.",
        }
    if provider == "Mapillary":
        return {
            "label": "Nearby street context image",
            "status": "Lower-confidence context",
            "description": "Crowdsourced street-level image captured near the waiting point, not guaranteed to frame the exact waiting zone.",
        }
    return {
        "label": "No verified waiting-point photo",
        "status": "No image evidence",
        "description": "This waiting point currently has no verified waiting-area photo in the app.",
    }


def save_community_upload(stop: dict, uploaded_file, contributor_name: str, contributor_note: str) -> tuple[bool, str]:
    file_suffix = Path(uploaded_file.name or "").suffix.lower()
    if file_suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        return False, "Upload a JPG, PNG, or WEBP image."

    latest_upload = latest_community_upload_for_stop(str(stop["stop_id"]))
    if latest_upload is not None:
        uploaded_at_ts = latest_upload.get("uploaded_at_ts")
        if pd.notna(uploaded_at_ts):
            next_allowed_at = uploaded_at_ts + pd.Timedelta(hours=24)
            now_utc = pd.Timestamp.utcnow()
            if now_utc < next_allowed_at:
                return False, (
                    f"A community photo was already added for this waiting point on {format_timestamp(str(latest_upload.get('uploaded_at')))}. "
                    f"You can add another photo after {format_timestamp(next_allowed_at.isoformat())}."
                )

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    uploaded_at = pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    file_name = f"community_{stop['stop_id']}_{uploaded_at.replace(':', '').replace('-', '')}{file_suffix}"
    destination = IMAGES_DIR / file_name
    destination.write_bytes(uploaded_file.getbuffer())

    manifest = load_local_manifest()
    if not manifest.empty and "stop_id" in manifest.columns:
        manifest = manifest.loc[manifest["stop_id"] != str(stop["stop_id"])].copy()

    new_row = pd.DataFrame(
        [
            {
                "stop_id": str(stop["stop_id"]),
                "file_name": file_name,
                "source_url": COMMUNITY_UPLOAD_SOURCE,
                "contributor_name": contributor_name.strip(),
                "contributor_note": contributor_note.strip(),
                "uploaded_at": uploaded_at,
            }
        ]
    )
    manifest = pd.concat([manifest, new_row], ignore_index=True)
    manifest.to_csv(manifest_path(), index=False)
    return True, file_name


def datetime_now():
    return pd.Timestamp.now(tz="America/New_York").to_pydatetime()


def format_timestamp(value: str | None) -> str:
    if not value:
        return "n/a"
    try:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        return timestamp.tz_convert(datetime_now().tzinfo).strftime("%b %d, %Y %I:%M %p %Z")
    except Exception:
        return str(value)


def weather_snapshot_is_stale(weather: dict | None, *, max_age_minutes: int = 60) -> bool:
    if not weather:
        return True
    refreshed_at = weather.get("refreshed_at") or weather.get("updated_at")
    if not refreshed_at:
        return True
    try:
        timestamp = pd.Timestamp(refreshed_at)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        now = pd.Timestamp.now(tz="America/New_York")
        local_timestamp = timestamp.tz_convert(now.tzinfo)
        if local_timestamp.date() != now.date():
            return True
        age_minutes = (now - local_timestamp).total_seconds() / 60.0
        return age_minutes > max_age_minutes
    except Exception:
        return True


def score_color(value: float) -> str:
    if value >= 85:
        return "#ff4d5a"
    if value >= 70:
        return "#ff6b3d"
    if value >= 45:
        return "#f3ad3d"
    return "#19c3a5"


def score_tone(value: float) -> str:
    if value >= 85:
        return "critical"
    if value >= 70:
        return "high"
    if value >= 45:
        return "med"
    return "low"


def severity_label(value: float) -> str:
    if value >= 85:
        return "Critical heat-response priority"
    if value >= 70:
        return "High intervention priority"
    if value >= 45:
        return "Elevated corridor concern"
    return "Lower immediate urgency"


def bool_label(value: object) -> str:
    if pd.isna(value):
        return "Unknown"
    return "Yes" if bool(value) else "No"


def proxy_band(value: object) -> str:
    if pd.isna(value):
        return "Unknown"
    numeric = float(value)
    if numeric >= 0.67:
        return "High"
    if numeric >= 0.34:
        return "Medium"
    return "Low"


def tree_inventory_band(tree_count: object) -> str:
    if pd.isna(tree_count):
        return "Unknown"
    count = float(tree_count)
    if count >= 8:
        return "High"
    if count >= 3:
        return "Medium"
    return "Low"


def evidence_tone(tier: str) -> str:
    normalized = str(tier or "").lower()
    if normalized in {"verified", "live", "official"}:
        return "low"
    if normalized in {"estimated", "proxy-based", "proxy"}:
        return "med"
    return "high"


def pretty_driver_label(label: str) -> str:
    return label.replace("scheduled ", "").title()


def top_driver_labels(stop: dict, limit: int = 4) -> list[str]:
    breakdown = stop.get("score_breakdown") or {}
    if breakdown:
        ordered = sorted(breakdown.values(), key=lambda item: item.get("score", 0), reverse=True)
        return [item["label"] for item in ordered if item.get("score", 0) > 0][:limit]
    raw = stop.get("top_contributors", "")
    return [item.strip() for item in raw.split(",") if item.strip()][:limit]


def field_review_display_context(stop: dict, shelter_state: dict) -> dict:
    labels = top_driver_labels(stop)
    recommendation = str(stop.get("recommended_intervention", "No recommendation available."))
    action_summary = str(stop.get("recommended_action_summary", recommendation))
    planner_note = str(stop.get("planner_note", "No planner note available."))
    planner_source = str(stop.get("planner_note_source", "Deterministic fallback"))

    if not shelter_state.get("selected_stop_override"):
        return {
            "driver_labels": labels,
            "recommended_intervention": recommendation,
            "recommended_action_summary": action_summary,
            "planner_note": planner_note,
            "planner_note_source": planner_source,
        }

    display_labels = [label for label in labels if label != "no shelter"]
    adjusted_row = dict(stop)
    adjusted_row["shelter_present_effective"] = True
    adjusted_row["no_shelter_value"] = 0.0
    recommendation = recommend_intervention(adjusted_row)
    action_summary = recommend_action_summary(adjusted_row)

    remaining = summarize_contributors(display_labels[:3]) if display_labels else "remaining corridor heat exposure factors"
    intervention_phrase = recommendation.rstrip(".")
    if intervention_phrase:
        intervention_phrase = intervention_phrase[0].lower() + intervention_phrase[1:]
    planner_note = (
        "Field review of a verified community photo indicates an overhead canopy at this waiting point, "
        "so shelter absence is not treated as an active on-site deficiency for this selected-site view. "
        f"The highest remaining priorities are {remaining}. "
        f"The most practical near-term intervention is to {intervention_phrase}."
    )
    return {
        "driver_labels": display_labels,
        "recommended_intervention": recommendation,
        "recommended_action_summary": action_summary,
        "planner_note": planner_note,
        "planner_note_source": f"{planner_source} + verified-photo field review",
    }


def _normalize_score_series(values: pd.Series) -> pd.Series:
    series = pd.to_numeric(values, errors="coerce")
    if not series.notna().any():
        return pd.Series([0.0] * len(series), index=series.index, dtype=float)
    lower = float(series.min())
    upper = float(series.max())
    if upper == lower:
        return pd.Series([50.0 if pd.notna(value) else 0.0 for value in series], index=series.index, dtype=float)
    return (((series - lower) / (upper - lower)).clip(0, 1) * 100).round(2)


def field_review_score_context(stop: dict, shelter_state: dict, corridor_stops: pd.DataFrame | None) -> dict:
    official_raw = float(stop.get("priority_score") or 0.0)
    official_relative = float(stop.get("normalized_priority_score") or 0.0)
    official_breakdown = stop.get("score_breakdown") or {}

    context = {
        "official_raw": official_raw,
        "official_relative": official_relative,
        "official_breakdown": official_breakdown,
        "adjusted_raw": official_raw,
        "adjusted_relative": official_relative,
        "adjusted_breakdown": official_breakdown,
        "override_active": False,
    }

    if not shelter_state.get("selected_stop_override") or not official_breakdown:
        return context

    adjusted_breakdown = json.loads(json.dumps(official_breakdown))
    if "no_shelter" in adjusted_breakdown:
        adjusted_breakdown["no_shelter"]["value"] = 0.0
        adjusted_breakdown["no_shelter"]["score"] = 0.0

    adjusted_raw = float(stop.get("display_priority_score")) if stop.get("display_has_field_review_override") and stop.get("display_priority_score") is not None else round(
        sum(float(item.get("score", 0) or 0) for item in adjusted_breakdown.values()), 2
    )
    adjusted_relative = float(stop.get("display_relative_risk")) if stop.get("display_has_field_review_override") and stop.get("display_relative_risk") is not None else adjusted_raw
    if corridor_stops is not None and not corridor_stops.empty and "priority_score" in corridor_stops.columns:
        if not (stop.get("display_has_field_review_override") and stop.get("display_relative_risk") is not None):
            score_series = pd.to_numeric(corridor_stops["priority_score"], errors="coerce").copy()
            matching_index = corridor_stops.index[corridor_stops["stop_id"].astype(str) == str(stop.get("stop_id"))]
            if len(matching_index) > 0:
                score_series.loc[matching_index[0]] = adjusted_raw
                normalized = _normalize_score_series(score_series)
                adjusted_relative = float(normalized.loc[matching_index[0]])

    context.update(
        {
            "adjusted_raw": adjusted_raw,
            "adjusted_relative": adjusted_relative,
            "adjusted_breakdown": adjusted_breakdown,
            "override_active": True,
        }
    )
    return context


def enrich_stop_with_local_visual_evidence(stop: dict) -> tuple[dict, dict | None]:
    enriched = dict(stop)
    local_record = local_image_record(str(stop.get("stop_id")))
    if local_record:
        image_path = Path(local_record["image_path"])
        if image_path.exists():
            live_vision = analyze_image(image_path)
            for key, value in live_vision.items():
                if key != "image_path":
                    enriched[key] = value
    return enriched, local_record


def prepare_display_stops(stops: pd.DataFrame) -> pd.DataFrame:
    if stops.empty:
        return stops.copy()

    prepared_rows: list[dict] = []
    base_df = stops.copy()
    for _, row in base_df.iterrows():
        stop = row.to_dict()
        if isinstance(stop.get("score_breakdown_json"), str) and stop.get("score_breakdown_json"):
            try:
                stop["score_breakdown"] = json.loads(stop["score_breakdown_json"])
            except json.JSONDecodeError:
                stop["score_breakdown"] = {}
        enriched_stop, local_record = enrich_stop_with_local_visual_evidence(stop)
        shelter_state = shelter_override_state(enriched_stop, local_record)
        display_context = field_review_display_context(enriched_stop, shelter_state)
        score_context = field_review_score_context(enriched_stop, shelter_state, base_df)

        enriched_stop["display_priority_score"] = (
            float(score_context["adjusted_raw"]) if score_context["override_active"] else float(enriched_stop.get("priority_score") or 0.0)
        )
        enriched_stop["display_relative_risk"] = (
            float(score_context["adjusted_relative"]) if score_context["override_active"] else float(enriched_stop.get("normalized_priority_score") or 0.0)
        )
        enriched_stop["display_top_contributors"] = ", ".join(display_context["driver_labels"]) if display_context["driver_labels"] else ""
        enriched_stop["display_recommended_intervention"] = display_context["recommended_intervention"]
        enriched_stop["display_recommended_action_summary"] = display_context["recommended_action_summary"]
        enriched_stop["display_planner_note"] = display_context["planner_note"]
        enriched_stop["display_has_field_review_override"] = bool(score_context["override_active"])
        prepared_rows.append(enriched_stop)

    display_df = pd.DataFrame(prepared_rows)
    if display_df.empty:
        return display_df

    display_df["display_priority_score"] = pd.to_numeric(display_df["display_priority_score"], errors="coerce").fillna(0.0)
    display_df["display_relative_risk"] = _normalize_score_series(display_df["display_priority_score"])
    if "avg_headway_minutes" in display_df:
        display_df["avg_headway_minutes"] = pd.to_numeric(display_df["avg_headway_minutes"], errors="coerce")
        display_df = display_df.sort_values(["display_priority_score", "avg_headway_minutes"], ascending=[False, False], na_position="last")
    else:
        display_df = display_df.sort_values(["display_priority_score"], ascending=[False], na_position="last")
    return display_df.reset_index(drop=True)


def render_driver_chips(stop: dict, labels: list[str] | None = None) -> None:
    labels = labels or top_driver_labels(stop)
    if not labels:
        return
    chips = []
    for label in labels:
        tone = score_tone(float(stop.get("display_priority_score", stop.get("priority_score", 0)) or 0))
        chips.append(
            f"<span class='risk-chip {tone}'>{html.escape(pretty_driver_label(label))}</span>"
        )
    st.markdown("<div class='risk-chip-row'>" + "".join(chips) + "</div>", unsafe_allow_html=True)


def weather_pills_html(weather: dict) -> str:
    if not weather:
        return ""
    parts = []
    if weather.get("metric_display") and weather.get("value_f") is not None:
        parts.append(
            f"<span class='weather-pill heat'>{html.escape(weather['metric_display'])}: {weather['value_f']:.1f} F</span>"
        )
    parts.append(f"<span class='weather-pill source'>Source: {html.escape(weather.get('source_label', 'NWS / weather.gov'))}</span>")
    if weather.get("updated_at"):
        parts.append(f"<span class='weather-pill time'>Updated: {html.escape(format_timestamp(weather['updated_at']))}</span>")
    if weather.get("refreshed_at"):
        parts.append(f"<span class='weather-pill time'>Fetched: {html.escape(format_timestamp(weather['refreshed_at']))}</span>")
    return "<div class='weather-pill-row'>" + "".join(parts) + "</div>"


def corridor_insight(stops: pd.DataFrame) -> str:
    if stops.empty:
        return "No scored stops are available for the selected corridor."
    contributors = (
        stops["top_contributors"]
        .fillna("")
        .str.split(",")
        .explode()
        .str.strip()
    )
    contributors = contributors[contributors != ""]
    if contributors.empty:
        return "Priority is distributed across multiple factors in the selected corridor."
    top_factors = [pretty_driver_label(value) for value in contributors.value_counts().head(3).index.tolist()]
    if len(top_factors) == 1:
        return f"Most corridor exposure risk is driven by {top_factors[0].lower()}."
    if len(top_factors) == 2:
        return f"Most corridor exposure risk is concentrated around {top_factors[0].lower()} and {top_factors[1].lower()}."
    return (
        f"Most corridor exposure risk is concentrated at stops with {top_factors[0].lower()}, "
        f"{top_factors[1].lower()}, and {top_factors[2].lower()}."
    )


def top_intervention(stops: pd.DataFrame) -> str:
    if stops.empty or "recommended_action_summary" not in stops:
        return "No action identified"
    value_counts = stops["recommended_action_summary"].fillna("").replace("", pd.NA).dropna().value_counts()
    if value_counts.empty:
        return "No action identified"
    return str(value_counts.index[0])


def _safe_float(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _safe_bool(value: object) -> bool | None:
    try:
        if pd.isna(value):
            return None
        return bool(value)
    except Exception:
        return None


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def stop_rating_label(value: float) -> str:
    if value >= 8.0:
        return "Comfortable"
    if value >= 6.5:
        return "Solid"
    if value >= 5.0:
        return "Watch heat"
    return "Exposed"


def stop_rating_color(value: float) -> str:
    if value >= 8.0:
        return "#19c3a5"
    if value >= 6.5:
        return "#4dd2b3"
    if value >= 5.0:
        return "#f3ad3d"
    return "#ff6b3d"


def stop_rating_summary_html(rating: float, *, title: str = "Rider comfort rating") -> str:
    return f"""
    <div class="stop-rating-hero" style="--rating-color:{stop_rating_color(rating)};">
      <div class="stop-rating-header">
        <div class="stop-rating-title">{html.escape(title)}</div>
        <span class="stop-rating-band">{html.escape(stop_rating_label(rating))}</span>
      </div>
      <div class="stop-rating-value-row">
        <span class="stop-rating-value">{rating:.1f}</span>
        <span class="stop-rating-scale">/10</span>
      </div>
      <div class="stop-rating-note">
        Higher means cooler, safer, and more comfortable waiting conditions. This rider-facing score blends
        shelter, seating, tree cover, wait burden, heat burden, and overall HeatStop risk.
      </div>
    </div>
    """


def stop_rating_out_of_10(stop_or_risk: object, relative_risk: object | None = None) -> float:
    row: dict[str, object] = {}
    if isinstance(stop_or_risk, dict):
        row = dict(stop_or_risk)
    elif hasattr(stop_or_risk, "to_dict"):
        row = dict(stop_or_risk.to_dict())

    fallback_risk = None if row else stop_or_risk
    relative = _safe_float(
        relative_risk
        if relative_risk is not None
        else row.get("display_relative_risk", row.get("normalized_priority_score", fallback_risk))
    )
    if relative is None:
        relative = 50.0

    shelter_present = _safe_bool(row.get("shelter_present_effective", row.get("has_shelter")))
    if bool(row.get("display_has_field_review_override")):
        shelter_present = True
    no_shelter_penalty = 1.4 if shelter_present is False else 0.0

    seating_present = _safe_bool(row.get("bench_present_effective", row.get("has_nearby_seating")))
    no_seating_penalty = 0.75 if seating_present is False else 0.0

    low_tree_cover = _safe_float(row.get("low_tree_cover_value"))
    if low_tree_cover is None:
        combined_tree_cover = _safe_float(row.get("combined_tree_cover_score"))
        if combined_tree_cover is not None:
            low_tree_cover = 1.0 - _clamp(combined_tree_cover, 0.0, 1.0)
    tree_penalty = _clamp(low_tree_cover or 0.0, 0.0, 1.0) * 1.15

    wait_burden = _safe_float(row.get("wait_burden_value"))
    if wait_burden is None:
        avg_headway = _safe_float(row.get("avg_headway_minutes"))
        if avg_headway is not None:
            wait_burden = _clamp((avg_headway - 5.0) / 20.0, 0.0, 1.0)
    wait_penalty = _clamp(wait_burden or 0.0, 0.0, 1.0) * 0.9

    heat_burden = _safe_float(row.get("heat_burden_value", row.get("heat_burden_score")))
    heat_penalty = _clamp(heat_burden or 0.0, 0.0, 1.0) * 0.95

    open_sky = _safe_float(row.get("open_sky_ratio"))
    open_sky_penalty = 0.0
    if open_sky is not None and open_sky > 0.7:
        open_sky_penalty = _clamp((open_sky - 0.7) / 0.3, 0.0, 1.0) * 0.45

    overall_risk_penalty = _clamp(relative / 100.0, 0.0, 1.0) * 0.75

    rating = 9.3 - (
        no_shelter_penalty
        + no_seating_penalty
        + tree_penalty
        + wait_penalty
        + heat_penalty
        + open_sky_penalty
        + overall_risk_penalty
    )
    return round(_clamp(rating, 2.5, 9.6), 1)


def google_maps_search_url(lat: object, lon: object) -> str | None:
    safe_lat = _safe_float(lat)
    safe_lon = _safe_float(lon)
    if safe_lat is None or safe_lon is None:
        return None
    query = urlencode({"api": 1, "query": f"{safe_lat},{safe_lon}"})
    return f"https://www.google.com/maps/search/?{query}"


def google_maps_directions_url(lat: object, lon: object, travelmode: str = "driving") -> str | None:
    safe_lat = _safe_float(lat)
    safe_lon = _safe_float(lon)
    if safe_lat is None or safe_lon is None:
        return None
    query = urlencode({"api": 1, "destination": f"{safe_lat},{safe_lon}", "travelmode": travelmode})
    return f"https://www.google.com/maps/dir/?{query}"


def google_maps_street_view_url(lat: object, lon: object) -> str | None:
    safe_lat = _safe_float(lat)
    safe_lon = _safe_float(lon)
    if safe_lat is None or safe_lon is None:
        return None
    query = urlencode({"api": 1, "map_action": "pano", "viewpoint": f"{safe_lat},{safe_lon}"})
    return f"https://www.google.com/maps/@?{query}"


def maps_action_links_html(
    lat: object,
    lon: object,
    *,
    include_street_view: bool = False,
    include_walk: bool = False,
    class_name: str = "action-link",
) -> str:
    links: list[str] = []
    search_url = google_maps_search_url(lat, lon)
    if search_url:
        links.append(
            f"<a class='{class_name}' href='{html.escape(search_url)}' target='_blank' rel='noopener noreferrer'>Open in Google Maps</a>"
        )
    drive_url = google_maps_directions_url(lat, lon, travelmode="driving")
    if drive_url:
        links.append(
            f"<a class='{class_name} primary' href='{html.escape(drive_url)}' target='_blank' rel='noopener noreferrer'>Navigate crew</a>"
        )
    if include_walk:
        walk_url = google_maps_directions_url(lat, lon, travelmode="walking")
        if walk_url:
            links.append(
                f"<a class='{class_name} secondary' href='{html.escape(walk_url)}' target='_blank' rel='noopener noreferrer'>Walking route</a>"
            )
    if include_street_view:
        street_url = google_maps_street_view_url(lat, lon)
        if street_url:
            links.append(
                f"<a class='{class_name} ghost' href='{html.escape(street_url)}' target='_blank' rel='noopener noreferrer'>Street-level view</a>"
            )
    if not links:
        return ""
    row_class = "builder-action-row" if "builder" in class_name else "action-links"
    return f"<div class='{row_class}'>{''.join(links)}</div>"


def kpi_card_html(label: str, value: str, subtitle: str, accent: str, icon: str) -> str:
    return f"""
    <div class="kpi-card" style="--accent:{accent};">
      <div class="kpi-icon">{html.escape(icon)} {html.escape(label)}</div>
      <div class="kpi-value">{html.escape(value)}</div>
      <div class="kpi-subtitle">{html.escape(subtitle)}</div>
    </div>
    """


def use_case_card_html(title: str, subtitle: str, accent: str) -> str:
    return f"""
    <div class="scope-card">
      <div class="eyebrow" style="background:{accent}; border-color:transparent; color:#fff;">Platform fit</div>
      <div class="scope-card-title">{html.escape(title)}</div>
      <div class="scope-card-text">{html.escape(subtitle)}</div>
    </div>
    """


def render_map(stops: pd.DataFrame, selected_stop_id: str | None = None) -> None:
    if stops.empty:
        st.info("No processed stops are available yet.")
        return
    center = [stops["stop_lat"].astype(float).mean(), stops["stop_lon"].astype(float).mean()]
    map_height = 620
    figure = folium.Figure(width="100%", height=map_height)
    fmap = folium.Map(location=center, zoom_start=13, tiles="CartoDB dark_matter")
    figure.add_child(fmap)

    for _, row in stops.iterrows():
        selected = str(row["stop_id"]) == str(selected_stop_id)
        priority = float(row.get("display_relative_risk", row["normalized_priority_score"]))
        marker_color = score_color(priority)
        radius = 10 if selected else 7
        folium.CircleMarker(
            location=[float(row["stop_lat"]), float(row["stop_lon"])],
            radius=radius,
            color="#f8fbff" if selected else marker_color,
            weight=3 if selected else 1.2,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.95,
            popup=folium.Popup(
                (
                    f"<b>{html.escape(str(row['stop_name']))}</b><br/>"
                    f"Relative risk: {priority:.1f}<br/>"
                    f"Action: {html.escape(str(row.get('display_recommended_action_summary', row.get('recommended_action_summary', row.get('recommended_intervention', 'n/a')))))}"
                ),
                max_width=320,
            ),
        ).add_to(fmap)
        if selected:
            folium.Circle(
                location=[float(row["stop_lat"]), float(row["stop_lon"])],
                radius=85,
                color="#f8fbff",
                weight=1.5,
                fill=False,
                opacity=0.65,
            ).add_to(fmap)
    components_html(figure.render(), height=map_height + 8, scrolling=False)


def render_action_cards(stops: pd.DataFrame) -> None:
    top_rows = stops.head(5).copy()
    if top_rows.empty:
        st.info("No priority actions are available.")
        return
    for _, row in top_rows.iterrows():
        display_score = float(row.get("display_priority_score", row["priority_score"]))
        relative_risk = float(row.get("display_relative_risk", row.get("normalized_priority_score", display_score)) or 0)
        stop_rating = stop_rating_out_of_10(row, relative_risk=relative_risk)
        tone = score_tone(display_score)
        reason_text = str(row.get("display_top_contributors") or row.get("top_contributors") or "No major drivers listed")
        action_text = str(row.get("display_recommended_action_summary") or row.get("recommended_action_summary") or row.get("recommended_intervention") or "No action listed")
        rating_html = stop_rating_summary_html(stop_rating).strip()
        action_links_html = maps_action_links_html(
            row.get("stop_lat"),
            row.get("stop_lon"),
            include_street_view=True,
        ).strip()
        st.markdown(
            dedent(
                f"""
            <div class="action-card {tone}">
              <div class="action-topline">
                <div class="action-stop">{html.escape(str(row['stop_name']))}</div>
                <span class="score-badge" style="--badge:{score_color(display_score)};">
                  {display_score:.1f}
                </span>
              </div>
              <div class="action-reason">{html.escape(reason_text)}</div>
              {rating_html}
              <div class="action-summary">{html.escape(action_text)}</div>
              {action_links_html}
            </div>
            """
            ).strip(),
            unsafe_allow_html=True,
        )


def corridor_intelligence_cache_key(display_stops: pd.DataFrame, meta: dict) -> str:
    weather = meta.get("weather", {})
    manifest_mtime = manifest_path().stat().st_mtime if manifest_path().exists() else 0.0
    payload = {
        "corridor_id": meta.get("corridor_id"),
        "weather_updated_at": weather.get("updated_at"),
        "weather_refreshed_at": weather.get("refreshed_at"),
        "manifest_mtime": manifest_mtime,
        "score_sum": round(float(pd.to_numeric(display_stops.get("display_priority_score"), errors="coerce").fillna(0).sum()), 2),
        "override_count": int(pd.to_numeric(display_stops.get("display_has_field_review_override"), errors="coerce").fillna(0).astype(int).sum()),
    }
    return json.dumps(payload, sort_keys=True)


def _render_agent_list(items: list[str], empty_text: str) -> None:
    if not items:
        st.caption(empty_text)
        return
    for item in items:
        st.markdown(f"- {item}")


def _agent_card_html(title: str, severity: str | None, body_lines: list[str], bullet_items: list[str] | None = None) -> str:
    bullet_html = ""
    if bullet_items:
        bullet_html = "<div style='margin-top:0.75rem;'><ul style='margin:0; padding-left:1.1rem; line-height:1.65;'>" + "".join(
            f"<li>{html.escape(str(item))}</li>" for item in bullet_items if str(item).strip()
        ) + "</ul></div>"
    body_html = "".join(
        f"<div style='margin-top:0.55rem; line-height:1.6;'>{html.escape(str(line))}</div>"
        for line in body_lines if str(line).strip()
    )
    severity_html = ""
    if severity:
        severity_html = f"<div style='margin-top:0.4rem; font-size:1.05rem; font-weight:700;'>{html.escape(str(severity))}</div>"
    return f"""
    <div class="panel-card" style="padding:1rem 1rem 0.95rem 1rem; min-height:100%;">
      <div class="section-kicker">{html.escape(title)}</div>
      {severity_html}
      {body_html}
      {bullet_html}
    </div>
    """


def render_corridor_intelligence(intelligence: dict) -> None:
    evidence = intelligence.get("evidence", {})
    analyst = intelligence.get("analyst", {})
    vulnerability = intelligence.get("vulnerability", {})
    planning = intelligence.get("planning", {})

    st.markdown(
        """
        <div class="section-shell">
          <div class="section-head">
            <div>
              <div class="section-kicker">Agent layer</div>
              <div class="section-title">Waiting-Zone Intelligence</div>
            </div>
            <div class="section-text">
              Facts come from the existing score pipeline and facility joins. The current demo groups waiting points by bus corridor, and the agent layer interprets those facts into zone patterns, vulnerability overlaps, and planner actions.
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    badges = [
        f"<span class='weather-pill source'>Facts: {html.escape(str(intelligence.get('source_of_truth', 'Transparent scoring pipeline')))}</span>",
        f"<span class='weather-pill heat'>Reasoning: {html.escape(str(intelligence.get('reasoning_mode', 'Deterministic fallback')))}</span>",
        f"<span class='weather-pill time'>Unsheltered: {float(evidence.get('unsheltered_pct', 0)):.0f}%</span>",
        f"<span class='weather-pill time'>Top 5 burden share: {float(evidence.get('top5_burden_share_pct', 0)):.0f}%</span>",
        f"<span class='weather-pill time'>Priority segment: {html.escape(str(evidence.get('top_segment') or 'n/a'))}</span>",
    ]
    st.markdown("<div class='weather-pill-row'>" + "".join(badges) + "</div>", unsafe_allow_html=True)
    st.markdown("<div style='height:0.85rem'></div>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3, gap="large")
    with col1:
        st.markdown(
            _agent_card_html(
                "Corridor Analyst says",
                str(analyst.get("severity_label", "n/a")),
                [
                    str(analyst.get("corridor_summary", "No corridor summary available.")),
                    f"Top segment: {analyst.get('top_segment', 'n/a')}",
                    f"Signature insight: {analyst.get('signature_insight', 'n/a')}",
                ],
                [str(item) for item in analyst.get("dominant_drivers", [])],
            ),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            _agent_card_html(
                "Vulnerability Agent says",
                str(vulnerability.get("severity_label", "n/a")),
                [
                    str(vulnerability.get("summary", "No vulnerability summary available.")),
                    f"Segment focus: {vulnerability.get('vulnerable_segment_summary', 'n/a')}",
                ],
                [str(item) for item in vulnerability.get("critical_findings", [])],
            ),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            _agent_card_html(
                "Planning Agent recommends",
                None,
                [
                    f"Priority segment: {planning.get('priority_segment', 'n/a')}",
                    f"Intervention mix: {', '.join(str(item) for item in planning.get('intervention_mix', [])) or 'n/a'}",
                    str(planning.get("planner_memo", "No planner memo available.")),
                ],
                [str(item) for item in planning.get("top_actions", [])],
            ),
            unsafe_allow_html=True,
        )


def empty_rider_support_payload(stop: dict) -> dict:
    return {
        "stop": {
            "stop_id": str(stop.get("stop_id")),
            "stop_name": stop.get("stop_name"),
            "route_short_name": stop.get("route_short_name"),
            "direction_id": stop.get("direction_id"),
            "stop_lat": stop.get("stop_lat"),
            "stop_lon": stop.get("stop_lon"),
        },
        "arrivals": {
            "status": "unavailable",
            "message": "Real-time arrivals are unavailable right now.",
            "source_label": "MTA Bus Time / SIRI StopMonitoring",
            "source_url": "https://bustime.mta.info/wiki/Developers/SIRIStopMonitoring",
            "items": [],
            "relevant_items": [],
            "next_arrival": None,
            "fetched_at": None,
        },
        "nearby_relief": {
            "status": "unavailable",
            "message": "Nearby relief places are unavailable right now.",
            "source_label": "OpenStreetMap / Overpass API",
            "source_url": "https://overpass-api.de/",
            "items": [],
            "fetched_at": None,
        },
    }


def _arrival_summary(arrivals: dict) -> tuple[str, str]:
    next_arrival = arrivals.get("next_arrival") or {}
    eta = next_arrival.get("eta_minutes")
    route = next_arrival.get("route")
    destination = next_arrival.get("destination")
    if eta is None:
        return (
            "Live ETA unavailable",
            arrivals.get("message") or "Real-time arrival data is not available right now.",
        )
    headline = f"Next bus in {eta} min"
    detail = f"{route or 'Bus'} to {destination}" if destination else f"{route or 'Bus'} arrival expected soon"
    return headline, detail


def _relief_badges(place: dict) -> str:
    badges = [
        f"<span class='meta-chip'>{html.escape(place.get('category', 'Place'))}</span>",
        f"<span class='meta-chip'>{html.escape(str(place.get('distance_m', 'n/a')))} m away</span>",
        f"<span class='meta-chip'>{html.escape(str(place.get('walking_minutes', 'n/a')))} min walk</span>",
    ]
    return "<div class='meta-chip-row'>" + "".join(badges) + "</div>"


def _render_relief_places(places: list[dict]) -> None:
    if not places:
        st.info("No nearby relief places were found in the configured free/open categories for this waiting point.")
        return
    for place in places[:4]:
        action_links_html = maps_action_links_html(place.get("lat"), place.get("lon"), include_walk=True).strip()
        st.markdown(
            dedent(
                f"""
            <div class="relief-card">
              <div class="relief-name">{html.escape(str(place.get('name', 'Nearby place')))}</div>
              {_relief_badges(place)}
              <div class="relief-meta">{html.escape(str(place.get('usefulness', 'Useful nearby place while waiting.')))}</div>
              <div class="relief-meta">Source: {html.escape(str(place.get('provider', 'OpenStreetMap / Overpass API')))}</div>
              {action_links_html}
            </div>
            """
            ).strip(),
            unsafe_allow_html=True,
        )


def _render_lower_risk_stop(lower_risk_stop: dict | None) -> None:
    if not lower_risk_stop:
        st.info("No lower-exposure nearby stop on this corridor met the current walk-distance and risk-drop thresholds.")
        return
    shelter = bool_label(lower_risk_stop.get("has_shelter"))
    seating = bool_label(lower_risk_stop.get("has_nearby_seating"))
    action_links_html = maps_action_links_html(
        lower_risk_stop.get("stop_lat"),
        lower_risk_stop.get("stop_lon"),
        include_walk=True,
    ).strip()
    st.markdown(
        dedent(
            f"""
        <div class="relief-card">
          <div class="relief-name">{html.escape(str(lower_risk_stop.get('stop_name')))}</div>
          <div class="meta-chip-row">
            <span class="meta-chip">Risk: {html.escape(str(lower_risk_stop.get('relative_risk')))}</span>
            <span class="meta-chip">{html.escape(str(lower_risk_stop.get('distance_m')))} m away</span>
            <span class="meta-chip">{html.escape(str(lower_risk_stop.get('walking_minutes')))} min walk</span>
            <span class="meta-chip">Shelter: {html.escape(shelter)}</span>
            <span class="meta-chip">Seating: {html.escape(seating)}</span>
          </div>
          {action_links_html}
        </div>
        """
        ).strip(),
        unsafe_allow_html=True,
    )


def render_copilot_sections(sections: list[dict]) -> None:
    if not sections:
        st.info("No grounded copilot sections are available for this question.")
        return
    for section in sections:
        tier = str(section.get("tier", "Unavailable"))
        confidence = str(section.get("confidence", "n/a"))
        sources = [str(source) for source in section.get("sources", []) if str(source).strip()]
        sources_text = ", ".join(sources[:3]) if sources else "HeatStop evidence layer"
        st.markdown(
            f"""
            <div class="detail-subpanel" style="margin-top:0.75rem;">
              <div class="section-kicker">{html.escape(str(section.get('title', 'Signal')))}</div>
              <div class="risk-chip-row" style="margin-top:0.45rem;">
                <span class="risk-chip {evidence_tone(tier)}">{html.escape(tier)}</span>
                <span class="meta-chip">Confidence: {html.escape(confidence)}</span>
              </div>
              <div style="margin-top:0.6rem; line-height:1.58;">{html.escape(str(section.get('summary', 'No summary available.')))}</div>
              <div style="margin-top:0.65rem; color:var(--muted); font-size:0.9rem;">Source: {html.escape(sources_text)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_nearby_relief_copilot(
    stop: dict,
    corridor_stops: pd.DataFrame,
    rider_support: dict,
    support_key: str,
    corridor_intelligence: dict | None = None,
) -> None:
    arrivals = rider_support.get("arrivals", {})
    nearby_relief = rider_support.get("nearby_relief", {})
    copilot_state = st.session_state.rider_copilot_answers.get(support_key)
    if not copilot_state:
        copilot_state = answer_heatstop_copilot(None, stop, corridor_stops, rider_support, corridor_intelligence)
    guidance = copilot_state.get("guidance", {})
    arrival_headline, arrival_detail = _arrival_summary(arrivals)
    risk_score = float(stop.get("display_relative_risk", stop.get("normalized_priority_score", 0)) or 0)
    risk_driver = str(stop.get("display_top_contributors") or stop.get("top_contributors") or "HeatStop waiting-point evidence")
    last_response = copilot_state

    st.markdown(
        """
        <div class="section-shell">
          <div class="section-head">
            <div>
              <div class="section-kicker">Rider support</div>
              <div class="section-title">HeatStop Copilot</div>
            </div>
            <div class="section-text">
              Waiting-point and corridor assistant grounded in HeatStop risk, live arrivals, nearby relief places, and current corridor evidence. Every answer is labeled as verified, estimated, or unavailable.
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div class='rider-shell'>", unsafe_allow_html=True)
    top_left, top_mid, top_right = st.columns(3, gap="large")
    with top_left:
        st.markdown(
            f"""
            <div class="rider-mini-card">
              <div class="section-kicker">Selected waiting-point heat risk</div>
              <div class="rider-mini-value" style="color:{score_color(risk_score)};">{risk_score:.1f} · {html.escape(severity_label(risk_score))}</div>
              <div class="rider-mini-text">{html.escape(risk_driver)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with top_mid:
        st.markdown(
            f"""
            <div class="rider-mini-card">
              <div class="section-kicker">Next bus arrival</div>
              <div class="rider-mini-value">{html.escape(arrival_headline)}</div>
              <div class="rider-mini-text">{html.escape(arrival_detail)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if arrivals.get("source_label"):
            st.caption(
                f"Source: {arrivals.get('source_label')} · Fetched {format_timestamp(arrivals.get('fetched_at'))}"
            )
    with top_right:
        relief_count = len(nearby_relief.get("items") or [])
        st.markdown(
            f"""
            <div class="rider-mini-card">
              <div class="section-kicker">Safer nearby waiting places</div>
              <div class="rider-mini-value">{relief_count}</div>
              <div class="rider-mini-text">Grounded heat-relief places from {html.escape(str(nearby_relief.get('source_label', 'OpenStreetMap / Overpass API')))}.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if arrivals.get("status") in {"error", "unavailable"}:
        st.warning(arrivals.get("message") or "Real-time arrivals are unavailable right now.")
    if nearby_relief.get("status") in {"error", "unavailable"}:
        st.warning(nearby_relief.get("message") or "Nearby relief places are unavailable right now.")

    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="copilot-response-card">
          <div class="section-kicker">Heat-aware waiting guidance</div>
          <div class="copilot-headline">{html.escape(str(guidance.get('headline', 'No guidance available right now.')))}</div>
          <div class="copilot-summary">{html.escape(str(guidance.get('summary', '')))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    guide_left, guide_right = st.columns([1.1, 0.9], gap="large")
    with guide_left:
        st.markdown("<div class='section-kicker' style='margin-top:1rem;'>Safer nearby places to wait</div>", unsafe_allow_html=True)
        _render_relief_places(guidance.get("relief_places") or [])
    with guide_right:
        st.markdown("<div class='section-kicker' style='margin-top:1rem;'>Lower-exposure nearby stop option</div>", unsafe_allow_html=True)
        _render_lower_risk_stop(guidance.get("lower_risk_stop"))

    st.markdown("<div class='section-kicker' style='margin-top:1rem;'>Copilot answer</div>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="detail-subpanel">
          <div class="section-kicker">Latest rider question</div>
          <div style="margin-top:0.3rem; color:var(--muted); line-height:1.5;">
            {html.escape(last_response.get('question', 'Should I stay here or wait somewhere cooler?'))}
          </div>
          <div style="height:0.7rem;"></div>
          <div class="section-kicker">Answer</div>
          <div style="font-weight:700;">{html.escape(last_response.get('answer', guidance.get('summary', '')))}</div>
          <div style="margin-top:0.55rem; color:var(--muted); line-height:1.55;">
            {html.escape(last_response.get('follow_up_tip', (guidance.get('steps') or [''])[0]))}
          </div>
          <div class="risk-chip-row" style="margin-top:0.7rem;">
            <span class="risk-chip {evidence_tone(str(last_response.get('primary_tier', 'Unavailable')))}">{html.escape(str(last_response.get('primary_tier', 'Unavailable')))}</span>
            <span class="meta-chip">Confidence: {html.escape(str(last_response.get('primary_confidence', 'n/a')))}</span>
          </div>
          <div style="margin-top:0.75rem; color:var(--muted); font-size:0.9rem;">
            Source: {html.escape(str(last_response.get('source', 'Deterministic capability router')))}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_copilot_sections(last_response.get("sections", []))

    related_signals = last_response.get("related_signals") or []
    if related_signals:
        chips = "".join(
            f"<span class='meta-chip'>{html.escape(str(item.get('label')))} · {html.escape(str(item.get('tier')))}</span>"
            for item in related_signals
        )
        st.markdown(
            f"""
            <div class="detail-subpanel" style="margin-top:0.75rem;">
              <div class="section-kicker">Related signals available</div>
              <div class="meta-chip-row" style="margin-top:0.55rem;">{chips}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    examples = last_response.get("examples") or QUESTION_EXAMPLES
    example_text = " · ".join(examples[:5])
    st.caption(f"Example questions: {example_text}")

    with st.form(f"rider_copilot_form_{support_key}"):
        question = st.text_input(
            "Ask about this waiting point or corridor",
            value=last_response.get("question", ""),
            placeholder="Example: Why is this waiting point high priority? Is the bus packed? What evidence is missing here?",
        )
        asked = st.form_submit_button("Ask the copilot")
        if asked:
            st.session_state.rider_copilot_answers[support_key] = answer_heatstop_copilot(
                question,
                stop,
                corridor_stops,
                rider_support,
                corridor_intelligence,
            )
            st.rerun()

    if guidance.get("steps"):
        st.markdown("<div class='section-kicker' style='margin-top:1rem;'>Suggested rider steps</div>", unsafe_allow_html=True)
        for step in guidance["steps"]:
            st.markdown(f"- {step}")
    st.markdown("</div>", unsafe_allow_html=True)


def score_ring_html(score: float) -> str:
    return score_panel_html(score, "Relative waiting-zone risk")


def score_panel_html(score: float, label: str, subtitle: str | None = None) -> str:
    tone = score_tone(score)
    tone_color = score_color(score)
    active_segments = 1
    if score >= 85:
        active_segments = 4
    elif score >= 70:
        active_segments = 3
    elif score >= 45:
        active_segments = 2
    segments = []
    segment_tones = ["low", "med", "high", "critical"]
    for index, segment_tone in enumerate(segment_tones):
        active_class = "on" if index < active_segments else ""
        segments.append(f"<div class='severity-segment {active_class} {segment_tone}'></div>")
    return f"""
    <div class="score-shell">
      <div>
        <div class="score-ring" style="--score:{max(0, min(score, 100))}; --ring-color:{tone_color};"></div>
        <div class="score-ring-value">
          <strong>{score:.1f}</strong>
          <span>risk</span>
        </div>
      </div>
      <div>
        <div class="section-kicker">{html.escape(label)}</div>
        <div class="severity-meter">
          <div class="severity-track">{''.join(segments)}</div>
          <div class="severity-label">{html.escape(severity_label(score))}</div>
        </div>
        {f"<div class='section-text' style='margin-top:0.55rem;'>{html.escape(subtitle)}</div>" if subtitle else ""}
      </div>
    </div>
    """


def image_metadata_chips(stop: dict, local_record: dict | None) -> str:
    image_provider = local_record.get("image_provider") if local_record else stop.get("display_image_provider") or stop.get("image_provider")
    image_capture_date = local_record.get("image_capture_date") if local_record else stop.get("display_image_capture_date") or stop.get("image_capture_date")
    image_author = local_record.get("image_author") if local_record else stop.get("display_image_author") or stop.get("image_author")
    image_distance_m = stop.get("display_image_distance_m")
    if image_distance_m is None:
        image_distance_m = stop.get("image_distance_m")
    profile = image_source_profile(image_provider)

    chips: list[str] = []
    chips.append(f"<span class='meta-chip'>{html.escape(profile['label'])}</span>")
    chips.append(f"<span class='meta-chip'>{html.escape(profile['status'])}</span>")
    if image_capture_date:
        label = "Uploaded" if image_provider == "Community upload" else "Captured"
        chips.append(f"<span class='meta-chip'>{label}: {html.escape(str(image_capture_date))}</span>")
    if image_author:
        role = "Contributor" if image_provider == "Community upload" else "Creator"
        chips.append(f"<span class='meta-chip'>{role}: {html.escape(str(image_author))}</span>")
    if image_distance_m is not None and image_provider != "Community upload":
        chips.append(f"<span class='meta-chip'>Distance: {html.escape(str(image_distance_m))} m</span>")
    return "<div class='meta-chip-row'>" + "".join(chips) + "</div>" if chips else ""


def render_upload_form(stop: dict) -> None:
    if not settings.enable_community_uploads:
        st.info("Community uploads are disabled for this deployment.")
        return
    latest_upload = latest_community_upload_for_stop(str(stop["stop_id"]))
    st.markdown(
        """
        <div class="detail-subpanel">
          <div class="section-kicker">Community update</div>
          <div class="section-title" style="font-size:1.15rem; margin-top:0.25rem;">Help update this waiting point</div>
          <div class="section-text" style="margin-top:0.35rem;">
            Contribute current site evidence with a real photo from the curb, shelter area, or passenger waiting zone.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        "Community uploads are stored on local filesystem for this demo and may not persist in hosted deployments without persistent storage."
    )
    if latest_upload is not None and pd.notna(latest_upload.get("uploaded_at_ts")):
        next_allowed_at = latest_upload["uploaded_at_ts"] + pd.Timedelta(hours=24)
        st.caption(
            "Community uploads are limited to one new photo per waiting point every 24 hours. "
            f"Last upload: {format_timestamp(str(latest_upload.get('uploaded_at')))}."
        )
        if pd.Timestamp.utcnow() < next_allowed_at:
            st.info(f"Next upload window opens at {format_timestamp(next_allowed_at.isoformat())}.")
    with st.form(f"community_upload_form_{stop['stop_id']}"):
        contributor_name = st.text_input("Your name or handle", key=f"uploader_name_{stop['stop_id']}")
        contributor_note = st.text_input(
            "Quick note about the photo",
            key=f"uploader_note_{stop['stop_id']}",
            placeholder="Example: facing north from the curb near the shelter pole",
        )
        uploaded_file = st.file_uploader(
            "Upload a real waiting-point photo",
            type=["jpg", "jpeg", "png", "webp"],
            key=f"uploader_file_{stop['stop_id']}",
            help="Only upload a real photo of this waiting area. Do not upload generated or unrelated images.",
        )
        submitted = st.form_submit_button("Contribute current site evidence")
        if submitted:
            if uploaded_file is None:
                st.warning("Choose an image before submitting.")
            else:
                ok, message = save_community_upload(stop, uploaded_file, contributor_name, contributor_note)
                if ok:
                    st.session_state["community_upload_message"] = (
                        f"Community photo saved for {stop['stop_name']}. The image will now appear for this waiting point."
                    )
                    st.rerun()
                st.warning(message)


def render_stop_intelligence(stop: dict, corridor_stops: pd.DataFrame | None = None) -> None:
    st.markdown(
        """
        <div class="section-shell">
          <div class="section-head">
            <div>
              <div class="section-kicker">Selected waiting point</div>
              <div class="section-title">Site Intelligence</div>
            </div>
            <div class="section-text">Trace why this outdoor waiting location matters, what the evidence says, and what action should happen next.</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, right = st.columns([1.05, 1], gap="large")
    local_record = local_image_record(str(stop["stop_id"]))
    live_image_path: Path | None = None

    with left:
        st.markdown("<div class='stop-image-shell'>", unsafe_allow_html=True)
        image_path = stop.get("image_path")
        image_url = stop.get("display_image_url") or stop.get("image_url")
        image_provider = stop.get("display_image_provider") or stop.get("image_provider")
        image_source = None
        has_image = False

        if local_record and Path(local_record["image_path"]).exists():
            image_source = local_record["image_path"]
            image_provider = local_record.get("image_provider") or image_provider
            live_image_path = Path(local_record["image_path"])
        elif image_provider == "Local file" and image_path and Path(str(image_path)).exists():
            image_source = str(image_path)
            live_image_path = Path(str(image_path))
        elif isinstance(image_url, str) and image_url:
            resolved_url = f"{API_URL}{image_url}" if image_url.startswith("/") else image_url
            try:
                response = requests.get(resolved_url, timeout=30)
                response.raise_for_status()
                image_source = response.content
            except requests.RequestException:
                image_source = None
        elif image_path and Path(str(image_path)).exists():
            image_source = str(image_path)
            live_image_path = Path(str(image_path))

        if live_image_path is not None and live_image_path.exists():
            live_vision = analyze_image(live_image_path)
            for key, value in live_vision.items():
                if key != "image_path":
                    stop[key] = value

        shelter_state = shelter_override_state(stop, local_record)
        display_context = field_review_display_context(stop, shelter_state)
        score_context = field_review_score_context(stop, shelter_state, corridor_stops)

        metadata_html = image_metadata_chips(stop, local_record)
        profile = image_source_profile(image_provider)
        if image_source is not None:
            has_image = True
            if metadata_html:
                st.markdown(metadata_html, unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="detail-subpanel" style="margin-bottom:0.9rem;">
                  <div class="section-kicker">Image evidence status</div>
                  <div style="margin-top:0.32rem; font-weight:700;">{html.escape(profile['label'])}</div>
                  <div style="margin-top:0.35rem; color:var(--muted); line-height:1.55;">{html.escape(profile['description'])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.image(image_source, use_container_width=True)
            if local_record and local_record.get("contributor_note"):
                st.caption(f"Community note: {local_record['contributor_note']}")
            if shelter_state["conflict"]:
                st.warning(
                    "Field evidence conflicts with official shelter inventory. "
                    "A verified community photo shows overhead canopy at this waiting point, but the official shelter dataset does not match it. "
                    "The app keeps official data as primary for corridor ranking and surfaces the photo-based override here for the selected site."
                )
            image_attribution_url = (
                local_record.get("image_attribution_url")
                if local_record
                else stop.get("display_image_attribution_url") or stop.get("image_attribution_url")
            )
            if image_attribution_url:
                st.markdown(f"[Open source image]({image_attribution_url})")
        else:
            st.markdown(
                """
                <div class="image-empty">
                  <div class="eyebrow">Evidence gap</div>
                  <h4>No verified waiting-point photo is available yet</h4>
                  <p>
                    This waiting point is still scored from real transit, amenity, tree, and weather data. Add a current photo to improve
                    the evidence base for image-derived conditions.
                  </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:0.9rem'></div>", unsafe_allow_html=True)
            render_upload_form(stop)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown(
            f"""
            <div class="intelligence-header">
              <div class="section-kicker">Waiting-point profile</div>
              <div class="intelligence-title">{html.escape(str(stop['stop_name']))}</div>
              <div class="intelligence-sub">
                Stop ID {html.escape(str(stop['stop_id']))} | Route {html.escape(str(stop['route_short_name']))} | Direction {html.escape(str(stop['direction_id']))}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        tabs = st.tabs(["Overview", "Evidence", "Planner Note", "Community Update"])

        with tabs[0]:
            primary_stop_rating = stop_rating_out_of_10(
                stop,
                relative_risk=float(score_context["adjusted_relative"]) if score_context["override_active"] else float(stop["normalized_priority_score"]),
            )
            if score_context["override_active"]:
                score_left, score_right = st.columns(2, gap="large")
                with score_left:
                    st.markdown(
                        score_panel_html(
                            float(score_context["adjusted_relative"]),
                            "Field-reviewed waiting-point risk",
                            f"Primary selected-site view using verified canopy evidence. Adjusted weighted score: {float(score_context['adjusted_raw']):.1f}.",
                        ),
                        unsafe_allow_html=True,
                    )
                with score_right:
                    st.markdown(
                        score_panel_html(
                            float(score_context["official_relative"]),
                            "Official corridor risk",
                            f"Reference ranking from the current corridor dataset. Official weighted score: {float(score_context['official_raw']):.1f}.",
                        ),
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(score_ring_html(float(stop["normalized_priority_score"])), unsafe_allow_html=True)
            st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
            rating_html = stop_rating_summary_html(primary_stop_rating).strip()
            st.markdown(
                dedent(
                    f"""
                <div class="detail-subpanel">
                  {rating_html}
                </div>
                """
                ).strip(),
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
            st.markdown("<div class='section-kicker'>Primary drivers</div>", unsafe_allow_html=True)
            render_driver_chips(stop, display_context["driver_labels"])
            if shelter_state["selected_stop_override"]:
                st.markdown(
                    """
                    <div class="detail-subpanel" style="margin-top:0.75rem;">
                      <div class="section-kicker">Selected-site field override</div>
                      <div style="margin-top:0.35rem; line-height:1.55;">
                        Verified community photo indicates overhead canopy at this waiting point. This override is shown for field review only and does not alter the corridor ranking.
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            st.markdown("<div style='height:0.7rem'></div>", unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="detail-note">
                  <div class="section-kicker">Action recommendation</div>
                  <div style="margin-top:0.35rem; font-size:1.05rem; line-height:1.5;">{html.escape(display_context['recommended_intervention'])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:0.7rem'></div>", unsafe_allow_html=True)
            builder_links_html = maps_action_links_html(
                stop.get("stop_lat"),
                stop.get("stop_lon"),
                include_street_view=True,
                class_name="builder-action-link",
            ).strip()
            st.markdown(
                dedent(
                    f"""
                <div class="detail-subpanel">
                  <div class="section-kicker">Builder actions</div>
                  <div style="margin-top:0.35rem; font-weight:700;">Move from triage into field inspection or upgrade execution.</div>
                  <div class="builder-note">
                    HeatStop decides which stop needs attention first. Google Maps helps crews reach the site, inspect the curb, and verify the upgrade area.
                  </div>
                  {builder_links_html}
                </div>
                """
                ).strip(),
                unsafe_allow_html=True,
            )

        with tabs[1]:
            visual_provider = local_record.get("image_provider") if local_record else stop.get("display_image_provider") or stop.get("image_provider")
            profile = image_source_profile(visual_provider)
            has_visual_evidence = bool(visual_provider)
            evidence_rows = pd.DataFrame(
                [
                    {"signal": "Official shelter inventory nearby", "value": bool_label(stop.get("has_shelter")), "confidence": "Primary dataset-backed"},
                    {
                        "signal": "Overhead canopy visible in photo",
                        "value": bool_label(stop.get("shelter_image_estimate")) if has_visual_evidence else "Unknown",
                        "confidence": "Verified stop photo" if visual_provider == "Community upload" else ("Lower-confidence context image" if has_visual_evidence else "No image evidence"),
                    },
                    {
                        "signal": "Selected-stop shelter interpretation",
                        "value": bool_label(shelter_state["selected_stop_shelter_present"]),
                        "confidence": "Verified photo override for UI only" if shelter_state["selected_stop_override"] else "Official inventory-backed",
                    },
                    {"signal": "Nearby seating inventory", "value": bool_label(stop.get("has_nearby_seating")), "confidence": "Primary dataset-backed"},
                    {"signal": "Nearby tree inventory", "value": tree_inventory_band(stop.get("nearby_tree_count")), "confidence": "Spatial dataset-backed"},
                    {
                        "signal": "Visible tree / shade in photo",
                        "value": proxy_band(stop.get("visible_tree_ratio")) if has_visual_evidence else "Unknown",
                        "confidence": "Verified stop photo" if visual_provider == "Community upload" else ("Lower-confidence context image" if has_visual_evidence else "No image evidence"),
                    },
                    {
                        "signal": "Open sky exposure in photo",
                        "value": proxy_band(stop.get("open_sky_ratio")) if has_visual_evidence else "Unknown",
                        "confidence": "Verified stop photo" if visual_provider == "Community upload" else ("Lower-confidence context image" if has_visual_evidence else "No image evidence"),
                    },
                ]
            )
            st.markdown("<div class='section-kicker'>Evidence snapshot</div>", unsafe_allow_html=True)
            st.dataframe(evidence_rows, use_container_width=True, hide_index=True)
            if visual_provider:
                st.markdown(
                    f"""
                    <div class="detail-subpanel" style="margin-top:0.9rem;">
                      <div class="section-kicker">Visual evidence confidence</div>
                      <div style="margin-top:0.32rem; font-weight:700;">{html.escape(profile['label'])}</div>
                      <div style="margin-top:0.35rem; color:var(--muted); line-height:1.55;">
                        {html.escape(profile['description'])}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            if stop.get("vision_model_name") or stop.get("vision_model_status"):
                model_rows = pd.DataFrame(
                    [
                        {"signal": "Vision mode", "value": stop.get("vision_method"), "status": stop.get("vision_model_status")},
                        {"signal": "Pretrained detector", "value": stop.get("vision_model_name") or "Disabled (heuristic-only mode)", "status": stop.get("vision_model_status")},
                        {"signal": "Shelter model detection", "value": bool_label(stop.get("shelter_model_detected")), "status": stop.get("shelter_model_confidence")},
                        {"signal": "Bench model detection", "value": bool_label(stop.get("bench_model_detected")), "status": stop.get("bench_model_confidence")},
                        {"signal": "Detection summary", "value": stop.get("model_detection_summary"), "status": ""},
                    ]
                )
                st.markdown("<div class='section-kicker' style='margin-top:1rem;'>Vision processing status</div>", unsafe_allow_html=True)
                st.dataframe(model_rows, use_container_width=True, hide_index=True)

            feature_rows = pd.DataFrame(
                [
                    {"feature": "Avg scheduled headway (min)", "value": stop.get("avg_headway_minutes")},
                    {"feature": "Heat burden factor (0-1 internal)", "value": stop.get("heat_burden_score")},
                    {"feature": "Nearby tree count", "value": stop.get("nearby_tree_count")},
                    {
                        "feature": "Visible tree ratio (image proxy)",
                        "value": stop.get("visible_tree_ratio"),
                        "confidence": "Verified stop photo" if visual_provider == "Community upload" else "Lower-confidence context",
                    },
                    {
                        "feature": "Open sky ratio (image proxy)",
                        "value": stop.get("open_sky_ratio"),
                        "confidence": "Verified stop photo" if visual_provider == "Community upload" else "Lower-confidence context",
                    },
                ]
            )
            st.markdown("<div class='section-kicker' style='margin-top:1rem;'>Supporting metrics</div>", unsafe_allow_html=True)
            st.dataframe(feature_rows, use_container_width=True, hide_index=True)

            official_breakdown = score_context["official_breakdown"] or {}
            adjusted_breakdown = score_context["adjusted_breakdown"] or {}
            if official_breakdown:
                st.markdown("<div class='section-kicker' style='margin-top:1rem;'>Score decomposition</div>", unsafe_allow_html=True)
                if score_context["override_active"]:
                    bd_left, bd_right = st.columns(2, gap="large")
                    with bd_left:
                        adjusted_df = pd.DataFrame(
                            [
                                {
                                    "factor": pretty_driver_label(item["label"]),
                                    "raw value": item["value"],
                                    "weight": item["weight"],
                                    "score points": item["score"],
                                }
                                for item in adjusted_breakdown.values()
                            ]
                        ).sort_values("score points", ascending=False)
                        st.caption("Primary field-reviewed stop view")
                        st.dataframe(adjusted_df, use_container_width=True, hide_index=True)
                    with bd_right:
                        official_df = pd.DataFrame(
                            [
                                {
                                    "factor": pretty_driver_label(item["label"]),
                                    "raw value": item["value"],
                                    "weight": item["weight"],
                                    "score points": item["score"],
                                }
                                for item in official_breakdown.values()
                            ]
                        ).sort_values("score points", ascending=False)
                        st.caption("Official corridor scoring reference")
                        st.dataframe(official_df, use_container_width=True, hide_index=True)
                else:
                    breakdown_df = pd.DataFrame(
                        [
                            {
                                "factor": pretty_driver_label(item["label"]),
                                "raw value": item["value"],
                                "weight": item["weight"],
                                "score points": item["score"],
                            }
                            for item in official_breakdown.values()
                        ]
                    ).sort_values("score points", ascending=False)
                    st.dataframe(breakdown_df, use_container_width=True, hide_index=True)

        with tabs[2]:
            st.markdown(
                f"""
                <div class="planner-card">
                  <div class="section-kicker">Planner note</div>
                  <div style="margin-top:0.45rem; line-height:1.65;">{html.escape(display_context['planner_note'])}</div>
                  <div style="margin-top:0.85rem; color:var(--muted);">
                    Source: {html.escape(display_context['planner_note_source'])} |
                    Urgency: {html.escape(str(stop.get('planner_note_urgency', 'n/a')))}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="detail-subpanel">
                  <div class="section-kicker">Recommended action</div>
                  <div style="margin-top:0.35rem; line-height:1.6;">{html.escape(display_context['recommended_action_summary'])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with tabs[3]:
            if local_record and local_record.get("image_provider") == "Community upload":
                st.markdown(
                    """
                    <div class="detail-subpanel">
                      <div class="section-kicker">Community-submitted evidence</div>
                      <div style="margin-top:0.35rem; line-height:1.55;">
                        A local contributor has already supplied current visual evidence for this waiting point.
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if local_record.get("contributor_note"):
                    st.caption(f"Community note: {local_record['contributor_note']}")
            elif has_image:
                render_upload_form(stop)
            else:
                st.markdown(
                    """
                    <div class="detail-subpanel">
                      <div class="section-kicker">Community update</div>
                      <div style="margin-top:0.35rem; line-height:1.55;">
                        The contribution form is shown directly in the evidence-gap panel on the left so users can add a photo immediately.
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def main() -> None:
    if "live_corridor_payloads" not in st.session_state:
        st.session_state.live_corridor_payloads = {}
    if "weather_refresh_errors" not in st.session_state:
        st.session_state.weather_refresh_errors = {}
    if "auto_refreshed_corridors" not in st.session_state:
        st.session_state.auto_refreshed_corridors = set()
    if "corridor_intelligence_cache" not in st.session_state:
        st.session_state.corridor_intelligence_cache = {}
    if "rider_support_payloads" not in st.session_state:
        st.session_state.rider_support_payloads = {}
    if "rider_copilot_answers" not in st.session_state:
        st.session_state.rider_copilot_answers = {}
    if "community_upload_message" in st.session_state:
        st.success(st.session_state.pop("community_upload_message"))

    health = api_get("/health")
    empty_meta = api_get("/meta")
    corridors_payload = api_get("/corridors")
    corridor_items = corridors_payload.get("items", [])
    corridor_lookup = {item["corridor_id"]: item for item in corridor_items}
    default_corridor_id = health.get("default_corridor_id") or (corridor_items[0]["corridor_id"] if corridor_items else None)

    if not health.get("has_processed_data"):
        st.warning(empty_meta.get("message", "Processed waiting-point data not found."))
        st.code("python scripts/build_demo_data.py --route M15 --direction 0 --stop-limit 20")
        st.stop()

    if default_corridor_id and "selected_corridor_id" not in st.session_state:
        st.session_state.selected_corridor_id = default_corridor_id

    st.markdown(
        """
        <div class="command-shell">
          <div class="eyebrow">Outdoor waiting-space resilience platform</div>
          <div class="hero-title">HeatStop AI</div>
          <div class="hero-subtitle">
            Resilience copilot for exposed outdoor waiting locations. Current demo: NYC bus corridors. Rank exposure risk,
            trace the evidence, and surface defensible near-term interventions for bus stops today, with a structure that
            can expand to shuttle stops, pickup zones, hospital transport points, and other public waiting spaces later.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="section-shell">
          <div class="section-head">
            <div>
              <div class="section-kicker">Platform scope</div>
              <div class="section-title">Who Can Use This?</div>
            </div>
            <div class="section-text">
              HeatStop AI is framed as a general platform for exposed outdoor waiting locations. The current live implementation is intentionally focused on NYC bus corridors for demo clarity.
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    scope_a, scope_b, scope_c, scope_d, scope_e = st.columns(5, gap="large")
    with scope_a:
        st.markdown(use_case_card_html("Cities & transit agencies", "Triage exposed curbside waiting points and route corridors for shade, seating, and resilience upgrades.", "rgba(255,107,61,0.88)"), unsafe_allow_html=True)
    with scope_b:
        st.markdown(use_case_card_html("Campuses & shuttle systems", "Apply the same waiting-point model to campus shuttle loops, transfer nodes, and event loading areas.", "rgba(25,195,165,0.88)"), unsafe_allow_html=True)
    with scope_c:
        st.markdown(use_case_card_html("Hospitals & patient transport", "Prioritize outdoor pickup points where heat exposure, wait burden, and vulnerability overlap matter most.", "rgba(243,173,61,0.88)"), unsafe_allow_html=True)
    with scope_d:
        st.markdown(use_case_card_html("Schools & pickup zones", "Generalize the resilience workflow to school dismissal waiting areas and parent pickup points.", "rgba(111,143,255,0.88)"), unsafe_allow_html=True)
    with scope_e:
        st.markdown(use_case_card_html("Venues & event operations", "Extend the same site-risk logic to temporary queue bands, rideshare staging, and transfer waiting zones.", "rgba(190,120,255,0.88)"), unsafe_allow_html=True)

    selected_corridor_id = default_corridor_id
    control_left, control_mid, control_right = st.columns([1.25, 0.42, 1.55], gap="large")
    with control_left:
        st.markdown("<div class='control-label'>Active corridor</div>", unsafe_allow_html=True)
        if corridor_items:
            selected_corridor_id = st.selectbox(
                "Corridor",
                options=[item["corridor_id"] for item in corridor_items],
                index=next((idx for idx, item in enumerate(corridor_items) if item["corridor_id"] == default_corridor_id), 0),
                format_func=lambda corridor_id: corridor_lookup[corridor_id]["label"],
                label_visibility="collapsed",
                key="selected_corridor_id",
            )

    params = {"corridor_id": selected_corridor_id} if selected_corridor_id else None
    active_payload = st.session_state.live_corridor_payloads.get(selected_corridor_id)
    if active_payload is None:
        stops_payload = api_get("/stops", params=params)
        active_payload = {
            "corridor_id": selected_corridor_id,
            "items": stops_payload.get("items", []),
            "meta": stops_payload.get("meta", {}),
            "weather": stops_payload.get("meta", {}).get("weather", {}),
        }
    weather = active_payload.get("weather") or active_payload.get("meta", {}).get("weather", {})
    auto_refresh_key = selected_corridor_id or "__default__"
    if auto_refresh_key not in st.session_state.auto_refreshed_corridors and weather_snapshot_is_stale(weather):
        with st.spinner("Refreshing stale corridor weather snapshot..."):
            try:
                refreshed_payload = api_post("/weather/refresh", params=params)
                st.session_state.live_corridor_payloads[selected_corridor_id] = refreshed_payload
                st.session_state.weather_refresh_errors[selected_corridor_id] = None
                active_payload = refreshed_payload
            except requests.RequestException as exc:
                st.session_state.weather_refresh_errors[selected_corridor_id] = (
                    f"Automatic weather refresh failed. Showing the last saved corridor snapshot. Details: {exc}"
                )
            finally:
                st.session_state.auto_refreshed_corridors.add(auto_refresh_key)

    refresh_error = st.session_state.weather_refresh_errors.get(selected_corridor_id)

    with control_mid:
        st.markdown("<div class='control-label'>Live weather</div>", unsafe_allow_html=True)
        if st.button("Refresh weather", use_container_width=True):
            with st.spinner("Updating corridor heat snapshot and rescoring stops..."):
                try:
                    refreshed_payload = api_post("/weather/refresh", params=params)
                    st.session_state.live_corridor_payloads[selected_corridor_id] = refreshed_payload
                    st.session_state.weather_refresh_errors[selected_corridor_id] = None
                    refresh_error = None
                    active_payload = refreshed_payload
                except requests.RequestException as exc:
                    st.session_state.weather_refresh_errors[selected_corridor_id] = (
                        f"Weather refresh failed. Showing the last successful corridor state. Details: {exc}"
                    )
                    refresh_error = st.session_state.weather_refresh_errors[selected_corridor_id]

    meta = active_payload.get("meta", {})
    weather = active_payload.get("weather") or meta.get("weather", {})
    stops = pd.DataFrame(active_payload.get("items", []))
    if stops.empty:
        st.warning("No waiting points are available for the selected corridor.")
        st.stop()
    display_stops = prepare_display_stops(stops)

    with control_right:
        st.markdown("<div class='control-label'>Operational snapshot</div>", unsafe_allow_html=True)
        st.markdown(weather_pills_html(weather), unsafe_allow_html=True)
        insight_stops = display_stops.assign(
            top_contributors=display_stops["display_top_contributors"].where(
                display_stops["display_top_contributors"].astype(str).str.strip() != "",
                display_stops["top_contributors"],
            )
        )
        st.markdown(
            f"""
            <div class="insight-card">
              <div class="insight-label">Current waiting-zone insight</div>
              <div class="insight-text">{html.escape(corridor_insight(insight_stops))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if refresh_error:
        st.warning(refresh_error)

    corridor_label = corridor_lookup.get(selected_corridor_id, {}).get("label") or (
        f"{meta.get('city_name')} {meta.get('route_short_name')} direction {meta.get('direction_id')}"
    )
    heat_value = weather.get("value_f")
    critical_count = int((display_stops["display_priority_score"].astype(float) >= 75).sum()) if "display_priority_score" in display_stops else 0
    top_action_stops = display_stops.assign(
        recommended_action_summary=display_stops["display_recommended_action_summary"].where(
            display_stops["display_recommended_action_summary"].astype(str).str.strip() != "",
            display_stops["recommended_action_summary"],
        )
    )
    top_action = top_intervention(top_action_stops)
    top_stop_name = str(display_stops.iloc[0]["stop_name"]) if not display_stops.empty else "n/a"

    st.markdown("<div class='kpi-grid'></div>", unsafe_allow_html=True)
    kpi_a, kpi_b, kpi_c, kpi_d = st.columns(4, gap="large")
    with kpi_a:
        st.markdown(
            kpi_card_html(
                "Current active-zone heat snapshot",
                f"{heat_value:.1f} F" if heat_value is not None else "n/a",
                weather.get("summary") or "Live corridor weather snapshot from NWS.",
                "#ff6b3d",
                "heat",
            ),
            unsafe_allow_html=True,
        )
    with kpi_b:
        st.markdown(
            kpi_card_html(
                "Waiting points scored",
                str(len(stops)),
                f"Active corridor: {corridor_label}",
                "#19c3a5",
                "scope",
            ),
            unsafe_allow_html=True,
        )
    with kpi_c:
        st.markdown(
            kpi_card_html(
                "Critical and high-risk waiting points",
                str(critical_count),
                "Locations demanding the strongest near-term response.",
                "#ff4d5a",
                "alert",
            ),
            unsafe_allow_html=True,
        )
    with kpi_d:
        st.markdown(
            kpi_card_html(
                "Top intervention today",
                top_action,
                f"Leading action for {top_stop_name}.",
                "#f3ad3d",
                "action",
            ),
            unsafe_allow_html=True,
        )

    intelligence_key = corridor_intelligence_cache_key(display_stops, meta)
    if intelligence_key not in st.session_state.corridor_intelligence_cache:
        with st.spinner("Running corridor intelligence agents..."):
            st.session_state.corridor_intelligence_cache[intelligence_key] = generate_waiting_zone_intelligence(display_stops, meta)
    corridor_intelligence = st.session_state.corridor_intelligence_cache[intelligence_key]
    render_corridor_intelligence(corridor_intelligence)

    current_stop_key = f"inspect_stop_{selected_corridor_id or 'default'}"
    if current_stop_key not in st.session_state or st.session_state[current_stop_key] not in display_stops["stop_id"].tolist():
        st.session_state[current_stop_key] = display_stops["stop_id"].iloc[0]

    selected_stop_id = st.selectbox(
        "Inspect a waiting point",
        options=display_stops["stop_id"].tolist(),
        key=current_stop_key,
        format_func=lambda stop_id: f"{display_stops.loc[display_stops['stop_id'] == stop_id, 'stop_name'].iloc[0]} ({stop_id})",
    )

    left, right = st.columns([1.45, 1], gap="large")
    with left:
        st.markdown(
            """
            <div class="section-shell">
              <div class="section-head">
                <div>
                  <div class="section-kicker">Spatial command view</div>
                  <div class="section-title">Risk Landscape</div>
                </div>
                <div class="section-text">
                  Scan the active waiting zone to see where exposure concentrates by segment and where the selected waiting point sits inside the wider heat-response pattern.
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div class='map-shell'>", unsafe_allow_html=True)
        render_map(display_stops, selected_stop_id=selected_stop_id)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown(
            """
            <div class="section-shell">
              <div class="section-head">
                <div>
                  <div class="section-kicker">Decision queue</div>
                  <div class="section-title">Top Actions Today</div>
                </div>
                <div class="section-text">
                  Highest-risk waiting points surfaced as a concise response list for planners and operations staff.
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
        render_action_cards(display_stops)
        st.markdown("<div class='ranked-table-wrap'>", unsafe_allow_html=True)
        ranked_table = display_stops.assign(stop_rating_10=display_stops.apply(stop_rating_out_of_10, axis=1))
        st.dataframe(
            ranked_table.loc[:, ["stop_name", "display_priority_score", "stop_rating_10", "display_top_contributors", "display_recommended_action_summary"]].rename(
                columns={
                    "stop_name": "stop",
                    "display_priority_score": "risk",
                    "stop_rating_10": "comfort /10",
                    "display_top_contributors": "key risk reason",
                    "display_recommended_action_summary": "recommended intervention",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("</div></div>", unsafe_allow_html=True)

    selected_stop = display_stops.loc[display_stops["stop_id"] == selected_stop_id].iloc[0].to_dict()
    if isinstance(selected_stop.get("score_breakdown_json"), str):
        selected_stop["score_breakdown"] = json.loads(selected_stop["score_breakdown_json"])

    render_stop_intelligence(selected_stop, stops)

    support_key = f"{selected_corridor_id}:{selected_stop_id}"
    rider_params = {"corridor_id": selected_corridor_id} if selected_corridor_id else None
    if support_key not in st.session_state.rider_support_payloads:
        with st.spinner("Fetching live arrivals and nearby relief places..."):
            try:
                st.session_state.rider_support_payloads[support_key] = api_get(
                    f"/stops/{selected_stop_id}/rider-support",
                    params=rider_params,
                )
            except requests.RequestException:
                st.session_state.rider_support_payloads[support_key] = empty_rider_support_payload(selected_stop)

    refresh_left, refresh_right = st.columns([1, 0.28], gap="large")
    with refresh_right:
        if st.button("Refresh rider guidance", key=f"refresh_rider_support_{support_key}", use_container_width=True):
            with st.spinner("Refreshing arrivals and nearby relief places..."):
                try:
                    st.session_state.rider_support_payloads[support_key] = api_get(
                        f"/stops/{selected_stop_id}/rider-support",
                        params=rider_params,
                    )
                except requests.RequestException:
                    st.session_state.rider_support_payloads[support_key] = empty_rider_support_payload(selected_stop)
                existing_question = (st.session_state.rider_copilot_answers.get(support_key) or {}).get("question")
                st.session_state.rider_copilot_answers[support_key] = answer_heatstop_copilot(
                    existing_question,
                    selected_stop,
                    display_stops,
                    st.session_state.rider_support_payloads[support_key],
                    corridor_intelligence,
                )
    rider_support_payload = st.session_state.rider_support_payloads.get(support_key, empty_rider_support_payload(selected_stop))
    render_nearby_relief_copilot(selected_stop, display_stops, rider_support_payload, support_key, corridor_intelligence)

    st.caption("HeatStop AI keeps the scoring engine unchanged and only reshapes how evidence, urgency, and action are surfaced.")


if __name__ == "__main__":
    main()
