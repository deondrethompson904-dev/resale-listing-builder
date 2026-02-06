# -*- coding: utf-8 -*-
import os
import re
import json
import uuid
import base64
import pathlib
import datetime as dt
from typing import Dict, Any, Optional, Tuple, List

import streamlit as st
import streamlit.components.v1 as components


# =====================================================
# Resale Listing Builder (v1.5.1)
# - Emoji-safe UI (no raw emoji chars in UI strings)
# - Smarter title rules + labeled variants
# - Live preview while typing (no counters)
# - Reset buttons
# - Modern visual polish (cards, badges, spacing, mobile)
# =====================================================


# =========================
# File storage (Streamlit Cloud-friendly)
# =========================
BASE_DIR = pathlib.Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
DATA_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)

CONFIG_PATH = DATA_DIR / "config.json"
STATS_PATH = DATA_DIR / "stats.json"
WAITLIST_CSV = DATA_DIR / "waitlist.csv"
LOGO_OVERRIDE_PATH = DATA_DIR / "logo_override.png"
EVENTS_PATH = DATA_DIR / "events.jsonl"

DEFAULT_CONFIG = {
    "app_name": "Resale Listing Builder",
    "tagline": "List faster. Price smarter. Profit confidently.",
    "accent_color": "#22C55E",
    "logo_size": 56,
    "show_how_it_works_tab": True,
}

DEFAULT_STATS = {
    "created_at": None,
    "updated_at": None,
    "sessions": 0,
    "tiktok_sessions": 0,
    "profit_checks": 0,
    "listings_generated": 0,
    "emails_captured": 0,
    "save_pro_clicks": 0,
    "sessions_by_source": {
        "tiktok": 0,
        "pinterest": 0,
        "instagram": 0,
        "facebook": 0,
        "direct": 0,
        "other": 0,
    },
}

APP_VERSION = "v1.5.1"  # emoji-safe UI + polish


# =========================
# Widget keys (stable reset support)
# =========================
# Listing Builder keys
LB_PLATFORM = "lb_platform"
LB_BRAND = "lb_brand"
LB_ITEM = "lb_item"
LB_MODEL = "lb_model"
LB_CONDITION = "lb_condition"
LB_CATEGORY = "lb_category"
LB_QTY = "lb_qty"
LB_FEATURES = "lb_features"
LB_DEFECTS = "lb_defects"
LB_USE_COND_TMPL = "lb_use_condition_template"
LB_INCLUDE_PARTS_NOTE = "lb_include_parts_note"
LB_SELLER_CITY = "lb_seller_city"
LB_PICKUP = "lb_pickup_line"
LB_SHIPPING = "lb_shipping_line"
LB_HANDLING = "lb_handling_time"
LB_RETURNS = "lb_returns_line"
LB_TITLE_PICK = "lb_title_pick"

# Flip Checker keys
FC_PRESET = "fc_preset"
FC_SALE_PRICE = "fc_sale_price"
FC_COGS = "fc_cogs"
FC_PACKAGING = "fc_packaging_cost"
FC_SHIP_METHOD = "fc_shipping_method"
FC_WEIGHT = "fc_weight"
FC_MANUAL_SHIP = "fc_manual_shipping"
FC_SHIP_COST = "fc_shipping_cost"
FC_PLATFORM_FEE = "fc_platform_fee_pct"
FC_PROCESSING_PCT = "fc_processing_pct"
FC_PROCESSING_FIXED = "fc_processing_fixed"


# =========================
# Helpers: JSON + counters
# =========================
def _read_json(path: pathlib.Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default)


def _write_json(path: pathlib.Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_config() -> Dict[str, Any]:
    cfg = _read_json(CONFIG_PATH, DEFAULT_CONFIG)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    cfg2 = dict(cfg)
    for k, v in DEFAULT_CONFIG.items():
        cfg2.setdefault(k, v)
    _write_json(CONFIG_PATH, cfg2)


def load_stats() -> Dict[str, Any]:
    stats = _read_json(STATS_PATH, DEFAULT_STATS)

    for k, v in DEFAULT_STATS.items():
        if k not in stats:
            stats[k] = v

    if not isinstance(stats.get("sessions_by_source"), dict):
        stats["sessions_by_source"] = dict(DEFAULT_STATS["sessions_by_source"])

    for sk, sv in DEFAULT_STATS["sessions_by_source"].items():
        stats["sessions_by_source"].setdefault(sk, sv)

    if stats.get("created_at") is None:
        stats["created_at"] = dt.datetime.utcnow().isoformat()

    return stats


def save_stats(stats: Dict[str, Any]) -> None:
    stats["updated_at"] = dt.datetime.utcnow().isoformat()
    _write_json(STATS_PATH, stats)


def bump_stat(key: str, n: int = 1) -> None:
    stats = load_stats()
    stats[key] = int(stats.get(key, 0)) + n
    save_stats(stats)


# =========================
# Event logging (lightweight)
# =========================
def log_event(event: str, props: Optional[Dict[str, Any]] = None) -> None:
    try:
        payload = {
            "ts_utc": dt.datetime.utcnow().isoformat(),
            "event": event,
            "session_id": st.session_state.get("session_id", ""),
            "source": st.session_state.get("traffic_source", ""),
            "props": props or {},
        }
        with EVENTS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


# =========================
# Helpers: waitlist
# =========================
def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    email = normalize_email(email)
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def append_waitlist(email: str, source: str = "", note: str = "") -> Tuple[bool, str]:
    email = normalize_email(email)
    if not is_valid_email(email):
        return False, "That does not look like a valid email."

    new_file = not WAITLIST_CSV.exists()
    if new_file:
        WAITLIST_CSV.write_text("timestamp_utc,email,source,note\n", encoding="utf-8")

    existing = WAITLIST_CSV.read_text(encoding="utf-8", errors="ignore").splitlines()[1:]
    for line in existing:
        parts = line.split(",")
        if len(parts) >= 2 and normalize_email(parts[1]) == email:
            return False, "You are already on the list."

    ts = dt.datetime.utcnow().isoformat()
    safe_source = (source or "").replace(",", " ").strip()
    safe_note = (note or "").replace(",", " ").replace("\n", " ").strip()
    with WAITLIST_CSV.open("a", encoding="utf-8") as f:
        f.write(f"{ts},{email},{safe_source},{safe_note}\n")

    bump_stat("emails_captured", 1)
    log_event("waitlist_joined", {"note": safe_note})
    return True, "Added. You are on the waitlist."


# =========================
# Helpers: query tracking (src + UTMs)
# =========================
def _qp_get(qp: Any, key: str) -> str:
    try:
        val = qp.get(key, "")
        if isinstance(val, list):
            val = val[0] if val else ""
        return (val or "").strip()
    except Exception:
        return ""


def get_query_context() -> Dict[str, str]:
    try:
        qp = st.query_params
    except Exception:
        qp = {}

    src = _qp_get(qp, "src").lower()

    utm_source = _qp_get(qp, "utm_source").lower()
    utm_medium = _qp_get(qp, "utm_medium").lower()
    utm_campaign = _qp_get(qp, "utm_campaign").lower()
    utm_content = _qp_get(qp, "utm_content").lower()

    raw = src or utm_source or ""
    traffic_source = raw if raw else "direct"

    if traffic_source in ("tt", "tik", "tiktokapp"):
        traffic_source = "tiktok"

    return {
        "src": src,
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
        "utm_content": utm_content,
        "traffic_source": traffic_source,
    }


def is_tiktok_context(ctx: Dict[str, str]) -> bool:
    return (ctx.get("src") == "tiktok") or (ctx.get("utm_source") == "tiktok") or (ctx.get("traffic_source") == "tiktok")


def source_bucket(traffic_source: str) -> str:
    s = (traffic_source or "").strip().lower()
    if s == "tiktok":
        return "tiktok"
    if s == "pinterest":
        return "pinterest"
    if s in ("ig", "instagram"):
        return "instagram"
    if s in ("fb", "facebook"):
        return "facebook"
    if s in ("direct", ""):
        return "direct"
    return "other"


# =========================
# Helpers: logo
# =========================
def read_file_bytes(path: pathlib.Path) -> Optional[bytes]:
    try:
        if path.exists():
            return path.read_bytes()
    except Exception:
        return None
    return None


def get_logo_source() -> Tuple[Optional[str], Optional[bytes], Optional[str]]:
    logo_url = (os.getenv("LOGO_URL", "") or "").strip()
    if logo_url:
        return logo_url, None, None

    override = read_file_bytes(LOGO_OVERRIDE_PATH)
    if override:
        return None, override, "image/png"

    png = read_file_bytes(ASSETS_DIR / "logo.png")
    if png:
        return None, png, "image/png"

    svg = read_file_bytes(ASSETS_DIR / "logo.svg")
    if svg:
        return None, svg, "image/svg+xml"

    return None, None, None


# =========================
# UI helpers
# =========================
def money(x: float) -> str:
    return f"${x:,.2f}"


def toast(msg: str) -> None:
    try:
        if hasattr(st, "toast"):
            st.toast(msg)
        else:
            st.success(msg)
    except Exception:
        st.success(msg)


def _clipboard_js(text: str) -> str:
    safe = json.dumps(text)
    return f"""
      <script>
        (function() {{
          try {{
            navigator.clipboard.writeText({safe});
          }} catch (e) {{}}
        }})();
      </script>
    """


def copy_btn(label: str, text: str, key: str, flash_key: str = "") -> None:
    """One-tap copy with confidence feedback + optional card flash.
    - Button label briefly becomes "Copied"
    - Inline confirmation appears (helps on mobile)
    - flash_key triggers a brief highlight on the matching card
    """
    now = dt.datetime.utcnow().timestamp()
    state_key = f"_copied_at_{key}"
    last = float(st.session_state.get(state_key, 0.0) or 0.0)
    is_recent = (now - last) < 1.6

    shown_label = "Copied" if is_recent else label

    if st.button(shown_label, key=key, use_container_width=True):
        components.html(_clipboard_js(text), height=0)
        ts = dt.datetime.utcnow().timestamp()
        st.session_state[state_key] = ts
        if flash_key:
            st.session_state["_flash_card"] = {"k": flash_key, "t": ts}
        toast("Copied â")

    if is_recent:
        st.caption("Copied to clipboard.")




def card(title: str, body_fn, flash_key: str = "") -> None:
    """Card wrapper with optional brief highlight after copy."""
    flash = st.session_state.get("_flash_card") or {}
    do_flash = False
    try:
        if flash_key and flash.get("k") == flash_key:
            now = dt.datetime.utcnow().timestamp()
            do_flash = (now - float(flash.get("t", 0.0) or 0.0)) < 1.8
    except Exception:
        do_flash = False

    extra = " tf-flash" if do_flash else ""
    st.markdown(f'<div class="tf-card{extra}"><div class="tf-card-title">{title}</div>', unsafe_allow_html=True)
    body_fn()
    st.markdown("</div>", unsafe_allow_html=True)




# =========================
# Styling (dark theme + modern typography + polish)
# =========================
def inject_css(accent: str) -> None:
    st.markdown(
        f"""
        <style>
          :root {{
            --accent: {accent};
            --bg: #0B0F14;
            --sidebar: #070A0F;
            --sidebar2: #0A111A;
            --card: rgba(255,255,255,0.04);
            --card2: rgba(255,255,255,0.06);
            --border: rgba(255,255,255,0.14);
            --border2: rgba(255,255,255,0.20);
            --text: #F3F4F6;
            --muted: #B6BAC4;
            --radius: 16px;
            --radiusSm: 12px;

            --h1: 1.55rem;
            --h2: 1.28rem;
            --h3: 1.12rem;
            --body: 1.00rem;
            --small: 0.92rem;
            --xs: 0.86rem;
          }}

          html, body, [class*="css"] {{
            font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji";
            color: var(--text) !important;
          }}

          html, body {{
            font-size: 16px !important;
            line-height: 1.45 !important;
            letter-spacing: 0.1px;
          }}

          h1 {{ font-size: var(--h1) !important; font-weight: 900 !important; letter-spacing: -0.2px; }}
          h2 {{ font-size: var(--h2) !important; font-weight: 850 !important; }}
          h3 {{ font-size: var(--h3) !important; font-weight: 800 !important; }}
          p, li {{ font-size: var(--body) !important; }}

          .stApp {{
            background:
              radial-gradient(1200px 600px at 18% 0%, rgba(34,197,94,0.10), transparent 55%),
              radial-gradient(900px 500px at 85% 10%, rgba(59,130,246,0.10), transparent 55%),
              var(--bg);
          }}

          section.main > div.block-container {{
            padding-top: 1.0rem;
            padding-bottom: 2.4rem;
            max-width: 1200px;
          }}

          [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, var(--sidebar), var(--sidebar2)) !important;
            border-right: 1px solid var(--border2) !important;
            opacity: 1 !important;
          }}
          [data-testid="stSidebar"] * {{
            color: var(--text) !important;
          }}
          [data-testid="stSidebar"] .stCaption,
          [data-testid="stSidebar"] p {{
            color: var(--muted) !important;
          }}

          [data-testid="stMarkdownContainer"] * {{ color: var(--text) !important; }}
          [data-testid="stCaptionContainer"] * {{ color: var(--muted) !important; }}

          label, .stMarkdown label {{
            font-weight: 760 !important;
            font-size: var(--small) !important;
            color: var(--text) !important;
          }}

          /* Inputs */
          .stTextInput > div > div > input,
          .stNumberInput > div > div > input,
          .stTextArea textarea {{
            background: rgba(255,255,255,0.04) !important;
            border: 1px solid var(--border) !important;
            border-radius: var(--radiusSm) !important;
            color: var(--text) !important;
            box-shadow: 0 10px 26px rgba(0,0,0,0.22);
          }}
          .stSelectbox > div > div {{
            background: rgba(255,255,255,0.04) !important;
            border-radius: var(--radiusSm) !important;
            border: 1px solid var(--border) !important;
            color: var(--text) !important;
          }}

          /* Buttons */
          div.stButton > button {{
            border-radius: 14px !important;
            border: 1px solid var(--border2) !important;
            background: rgba(255,255,255,0.06) !important;
            color: var(--text) !important;
            padding: 0.72rem 0.95rem !important;
            font-weight: 700 !important;
          }}
          div.stButton > button:hover {{
            border-color: rgba(255,255,255,0.26) !important;
            background: rgba(255,255,255,0.08) !important;
            transform: translateY(-1px);
          }}
          div.stButton > button[kind="primary"] {{
            background: linear-gradient(180deg, rgba(34,197,94,0.95), rgba(34,197,94,0.80)) !important;
            border: 1px solid rgba(34,197,94,0.55) !important;
            color: #07110A !important;
          }}

          /* Tabs */
          .stTabs [data-baseweb="tab-list"] {{
            gap: 10px;
            padding: 8px;
            background: rgba(255,255,255,0.03);
            border: 1px solid var(--border);
            border-radius: var(--radius);
          }}
          .stTabs [data-baseweb="tab"] {{
            height: 44px;
            border-radius: 12px;
            padding-left: 14px;
            padding-right: 14px;
            color: var(--muted) !important;
            font-weight: 780 !important;
          }}
          .stTabs [aria-selected="true"] {{
            background: rgba(255,255,255,0.08) !important;
            color: var(--text) !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
          }}

          /* Cards */
          .tf-card {{
            background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.03));
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 14px 14px;
            margin: 10px 0;
          }}

          /* Flash highlight (after copy) */
          .tf-card.tf-flash {{
            border-color: rgba(34,197,94,0.70) !important;
            box-shadow: 0 0 0 2px rgba(34,197,94,0.18) !important;
          }}

          .tf-card-title {{
            font-weight: 900;
            font-size: 1.02rem;
            margin-bottom: 10px;
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:10px;
          }}
          .tf-subtle {{ color: var(--muted); font-size: var(--xs); font-weight: 650; }}

          .tf-badge {{
            display:inline-flex;
            align-items:center;
            gap: 8px;
            padding: 6px 10px;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.14);
            background: rgba(255,255,255,0.05);
            color: var(--muted);
            font-size: 0.85rem;
            white-space: nowrap;
          }}
          .tf-badge-dot {{
            width: 8px; height: 8px; border-radius: 999px;
            background: var(--accent);
            box-shadow: 0 0 0 3px rgba(34,197,94,0.18);
          }}

          /* Header bar */
          .tf-headerbar {{
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 12px 14px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 14px;
          }}
          .tf-header-left {{
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 0;
          }}
          .tf-header-logo {{
            width: 54px;
            height: 54px;
            border-radius: 14px;
            overflow: hidden;
            flex: 0 0 auto;
            display: grid;
            place-items: center;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.10);
          }}
          .tf-header-logo img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
          }}
          .tf-header-title {{ min-width: 0; }}
          .tf-header-title .name {{
            font-weight: 950;
            font-size: 1.25rem;
            line-height: 1.15;
            margin: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }}
          .tf-header-title .tagline {{
            margin-top: 2px;
            color: var(--muted) !important;
            font-size: 0.95rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }}
          .tf-header-right {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            justify-content: flex-end;
          }}

          /* Mobile polish */
          @media (max-width: 640px) {{
            html, body {{ font-size: 16.8px !important; }}
            .tf-headerbar {{ padding: 10px 12px; }}
            .tf-header-logo {{ width: 46px; height: 46px; border-radius: 12px; }}
            .tf-header-title .name {{ font-size: 1.12rem; }}
            .tf-header-right {{ display: none; }}
            div.stButton > button {{ padding: 0.80rem 0.95rem !important; }}
          }}

          @media (max-width: 768px) {{
            section.main > div.block-container {{
              padding-top: 0.8rem;
              padding-left: 0.8rem;
              padding-right: 0.8rem;
            }}
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header_native(cfg: Dict[str, Any]) -> None:
    logo_url, logo_bytes, mime = get_logo_source()

    app_name = cfg.get("app_name", "Resale Listing Builder")
    tagline = cfg.get("tagline", "")
    initials = "".join([w[:1] for w in app_name.split()[:2]]).upper() or "RL"

    img_src = ""
    if logo_url:
        img_src = logo_url
    elif logo_bytes and mime:
        b64 = base64.b64encode(logo_bytes).decode("utf-8")
        img_src = f"data:{mime};base64,{b64}"

    left_logo_html = (
        f"<img src='{img_src}' alt='logo' />"
        if img_src
        else f"<div style='font-weight:950;color:var(--text);'>{initials}</div>"
    )

    st.markdown(
        f"""
        <div class="tf-headerbar">
          <div class="tf-header-left">
            <div class="tf-header-logo">{left_logo_html}</div>
            <div class="tf-header-title">
              <div class="name">{app_name}</div>
              <div class="tagline">{tagline}</div>
            </div>
          </div>
          <div class="tf-header-right">
            <span class="tf-badge"><span class="tf-badge-dot"></span>Offline-friendly</span>
            <span class="tf-badge"><span class="tf-badge-dot"></span>No login</span>
            <span class="tf-badge"><span class="tf-badge-dot"></span>{APP_VERSION}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()


# =========================
# Core logic
# =========================
def calc_profit(
    sale_price: float,
    cogs: float,
    ebay_fee_pct: float,
    processing_pct: float,
    processing_fixed: float,
    shipping_cost: float,
    packaging_cost: float,
) -> Dict[str, float]:
    ebay_fee = sale_price * (ebay_fee_pct / 100.0)
    processing_fee = sale_price * (processing_pct / 100.0) + processing_fixed
    total_fees = ebay_fee + processing_fee
    total_cost = cogs + shipping_cost + packaging_cost + total_fees
    profit = sale_price - total_cost
    margin = (profit / sale_price * 100.0) if sale_price > 0 else 0.0
    return {
        "ebay_fee": ebay_fee,
        "processing_fee": processing_fee,
        "total_fees": total_fees,
        "total_cost": total_cost,
        "profit": profit,
        "margin_pct": margin,
    }


def shipping_estimate(method: str, weight_lb: float) -> float:
    w = max(0.0, float(weight_lb))
    if method == "Ground (est.)":
        return 6.50 + 1.10 * w
    if method == "Priority (est.)":
        return 9.50 + 1.50 * w
    if method == "Local pickup":
        return 0.0
    return 7.50 + 1.20 * w


def flip_score(profit: float, margin_pct: float, sale_price: float) -> float:
    score = 5.0
    if profit >= 25:
        score += 2.0
    if profit >= 50:
        score += 3.0
    if margin_pct >= 40:
        score += 2.0
    if margin_pct >= 60:
        score += 3.0
    if profit < 10:
        score -= 3.0
    if margin_pct < 20:
        score -= 3.0
    if sale_price > 200 and profit < 20:
        score -= 2.0
    return max(1.0, min(10.0, round(score, 1)))


def flip_badge(score: float) -> str:
    if score <= 3:
        return "â Bad Flip"
    if score <= 6:
        return "â ï¸ Risky"
    if score <= 8:
        return "â Good Flip"
    return "ð¥ Great Flip"


# =========================
# Listing helpers (templates, titles, platforms)
# =========================
CONDITION_TEMPLATES = {
    "New": "Brand new, unused. Ships fast.",
    "Open box": "Open box item. Tested/inspected. Ships fast.",
    "Used - Like New": "Lightly used. Clean and fully functional. Ships fast.",
    "Used - Good": "Normal wear from use. Fully functional unless noted. Ships fast.",
    "Used - Fair": "Noticeable wear. Fully functional unless noted. Please review photos/notes.",
    "Used - Poor": "Heavy wear. May have issues. Please read notes carefully.",
    "For parts/repair": "For parts/repair. Sold as-is. No returns.",
}

PHOTO_CHECKLISTS = {
    "Electronics": [
        "Front & back",
        "Screen close-up (if applicable)",
        "Model/part number label",
        "Ports & buttons",
        "Power-on photo (if possible)",
        "Accessories included",
        "Any defects close-up",
    ],
    "Shoes/Clothing": [
        "Front, sides, back",
        "Size tag/label",
        "Soles/bottoms",
        "Stitching/inside",
        "Brand/logo close-up",
        "Any stains/tears close-up",
    ],
    "Tools": [
        "Full tool front/back",
        "Model/serial plate",
        "Battery/charger (if included)",
        "Bit/attachments (if included)",
        "Power-on/operation (if possible)",
        "Any cracks/damage close-up",
    ],
    "Home/Kitchen": [
        "Front/back",
        "Underside/markings",
        "Measurements (if relevant)",
        "Set pieces (if bundle)",
        "Any chips/cracks close-up",
    ],
    "Toys/Games": [
        "Front/back of box",
        "Contents laid out",
        "Piece/part count note (if known)",
        "Close-ups of wear/tears",
    ],
    "Other": [
        "Front/back",
        "Brand/model label",
        "Any included accessories",
        "Any defects close-up",
    ],
}

# ---- Title rules ----
FLUFF_WORDS = {
    "great",
    "amazing",
    "awesome",
    "nice",
    "wow",
    "look",
    "fast",
    "shipping",
    "must",
    "see",
    "hot",
}


def _clean_token(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _strip_fluff(text: str) -> str:
    words = re.split(r"(\W+)", text)
    out = []
    for w in words:
        if re.match(r"^\w+$", w):
            if w.lower() in FLUFF_WORDS:
                continue
        out.append(w)
    return _clean_token("".join(out))


def _short_featureize(s: str) -> str:
    s = _clean_token(s)
    s = re.sub(r"\b(\d{1,2})\s*(inches|inch)\b", r'\1"', s, flags=re.IGNORECASE)
    return s


def _keywords_from_features(features_lines: str, max_k: int = 2) -> List[str]:
    lines = [ln.strip() for ln in (features_lines or "").splitlines() if ln.strip()]
    keep: List[str] = []
    for ln in lines[:12]:
        ln = _short_featureize(_strip_fluff(ln))
        if 2 <= len(ln) <= 26:
            keep.append(ln)
        if len(keep) >= max_k:
            break
    return keep


def _fit_to_limit(parts: List[str], limit: int) -> str:
    parts = [_clean_token(p) for p in parts if _clean_token(p)]
    if not parts:
        return ""
    title = _clean_token(" ".join(parts))
    title = _strip_fluff(title)

    if len(title) <= limit:
        return title

    trimmed = parts[:]
    while trimmed and len(_clean_token(" ".join(trimmed))) > limit:
        trimmed.pop()

    title2 = _clean_token(" ".join(trimmed))
    if len(title2) <= limit:
        return title2

    return title2[:limit].rstrip()


def build_title_variants(
    platform: str,
    brand: str,
    item: str,
    model: str,
    condition: str,
    features_lines: str,
    max_variants: int = 6,
) -> List[Tuple[str, str]]:
    platform_l = (platform or "").strip().lower()
    ebay_limit = 80 if platform_l == "ebay" else 90
    short_limit = 60
    super_short_limit = 45

    b = _strip_fluff(_clean_token(brand))
    it = _strip_fluff(_clean_token(item))
    m = _strip_fluff(_clean_token(model))
    cond = _clean_token(condition)

    kws = _keywords_from_features(features_lines, max_k=2)

    candidates: List[Tuple[str, List[str]]] = []
    candidates.append(("eBay-fit", [b, it, m] + kws))
    if kws:
        candidates.append(("feature-first", [b, it, m, kws[0]]))
    candidates.append(("short", [b, it, m]))
    candidates.append(("super short", [b, it]))

    if cond and cond != "For parts/repair":
        candidates.append(("condition", [b, it, m, cond]))
    elif cond == "For parts/repair":
        candidates.append(("parts/repair", [b, it, m, "For Parts/Repair"]))

    seen = set()
    out: List[Tuple[str, str]] = []

    for label, parts in candidates:
        limit = ebay_limit
        if label == "short":
            limit = short_limit
        if label == "super short":
            limit = super_short_limit

        t = _fit_to_limit(parts, limit)
        t = _clean_token(t)
        if not t:
            continue

        key = t.lower()
        if key in seen:
            continue
        seen.add(key)

        out.append((label, t))
        if len(out) >= max_variants:
            break

    if not out:
        out = [("eBay-fit", _fit_to_limit([b, it, m], ebay_limit) or "Item for sale")]

    return out


def platform_description(
    platform: str,
    title: str,
    condition: str,
    category: str,
    qty: int,
    features: List[str],
    defects: List[str],
    seller_city: str,
    pickup_line: str,
    shipping_line: str,
    handling_time: str,
    returns_line: str,
    parts_repair_note: str,
) -> str:
    platform = (platform or "").strip().lower()

    feat_bul = "\n".join([f"- {x}" for x in features]) if features else ""
    def_bul = "\n".join([f"- {x}" for x in defects]) if defects else ""

    if platform == "ebay":
        key_features_block = ""
        if feat_bul:
            key_features_block = "### Key features\n" + feat_bul + "\n\n"

        notes_block = ""
        if def_bul:
            notes_block = "### Notes / defects\n" + def_bul + "\n\n"

        parts_block = (parts_repair_note + "\n") if parts_repair_note else ""

        return (
            f"## {title}\n\n"
            f"{key_features_block}"
            f"{notes_block}"
            f"**Condition:** {condition}\n"
            f"**Quantity:** {qty}\n"
            f"**Category:** {category or 'â'}\n\n"
            f"**Location:** {seller_city or 'â'}\n"
            f"**Pickup:** {pickup_line or 'â'}\n"
            f"**Shipping:** {shipping_line or 'â'}\n"
            f"**Handling time:** {handling_time or 'â'}\n"
            f"**Returns:** {returns_line or 'â'}\n\n"
            f"{parts_block}"
        ).strip()


    if platform in ("facebook marketplace", "facebook"):
        lines = []
        lines.append(title)
        lines.append("")
        lines.append(f"Condition: {condition}")
        lines.append(f"Qty: {qty}")
        if category:
            lines.append(f"Category: {category}")
        lines.append("")
        if features:
            lines.append("Features:")
            lines.extend([f"ÂÂ¢ {x}" for x in features])
            lines.append("")
        if defects:
            lines.append("Notes/defects:")
            lines.extend([f"ÂÂ¢ {x}" for x in defects])
            lines.append("")
        lines.append(f"Pickup: {pickup_line or '-'}")
        lines.append(f"Shipping: {shipping_line or '-'}")
        lines.append(f"Location: {seller_city or '-'}")
        lines.append(f"Returns: {returns_line or '-'}")
        if parts_repair_note:
            lines.append("")
            lines.append(parts_repair_note.replace("**", ""))
        return "\n".join(lines).strip()

    if platform == "mercari":
        lines = []
        lines.append(title)
        lines.append("")
        if features:
            lines.append("Details:")
            lines.extend([f"- {x}" for x in features])
            lines.append("")
        if defects:
            lines.append("Condition notes:")
            lines.extend([f"- {x}" for x in defects])
            lines.append("")
        lines.append(f"Condition: {condition}")
        if parts_repair_note:
            lines.append(parts_repair_note.replace("**", ""))
        return "\n".join(lines).strip()

    if platform == "offerup":
        lines = []
        lines.append(title)
        lines.append("")
        lines.append(f"Condition: {condition}")
        if features:
            lines.append("")
            lines.append("Highlights:")
            lines.extend([f"ÂÂ¢ {x}" for x in features])
        if defects:
            lines.append("")
            lines.append("Notes:")
            lines.extend([f"ÂÂ¢ {x}" for x in defects])
        lines.append("")
        lines.append(f"Pickup: {pickup_line or '-'}")
        lines.append(f"Location: {seller_city or '-'}")
        if parts_repair_note:
            lines.append("")
            lines.append(parts_repair_note.replace("**", ""))
        return "\n".join(lines).strip()

    return f"{title}\n\nCondition: {condition}\n\n{feat_bul}\n\n{def_bul}".strip()


def build_listing_payload(
    platform: str,
    brand: str,
    item: str,
    model: str,
    condition: str,
    category: str,
    qty: int,
    features_lines: str,
    defects_lines: str,
    seller_city: str,
    pickup_line: str,
    shipping_line: str,
    handling_time: str,
    returns_line: str,
    include_parts_repair_note: bool,
    use_condition_template: bool,
) -> Dict[str, Any]:
    features = [ln.strip() for ln in (features_lines or "").splitlines() if ln.strip()]
    defects = [ln.strip() for ln in (defects_lines or "").splitlines() if ln.strip()]

    if use_condition_template and condition in CONDITION_TEMPLATES:
        tmpl = CONDITION_TEMPLATES[condition]
        if tmpl and tmpl not in defects:
            defects = defects + [tmpl]

    title_variants = build_title_variants(
        platform=platform,
        brand=brand,
        item=item,
        model=model,
        condition=condition,
        features_lines=features_lines,
        max_variants=6,
    )
    chosen_title = title_variants[0][1] if title_variants else "Item for sale"

    parts_repair_note = ""
    if include_parts_repair_note and condition == "For parts/repair":
        parts_repair_note = (
            "**Parts/repair note:** Sold as-is for parts/repair. "
            "May have issues not listed. Please ask questions before purchase."
        )

    desc = platform_description(
        platform=platform,
        title=chosen_title,
        condition=condition,
        category=category,
        qty=qty,
        features=features,
        defects=defects,
        seller_city=seller_city,
        pickup_line=pickup_line,
        shipping_line=shipping_line,
        handling_time=handling_time,
        returns_line=returns_line,
        parts_repair_note=parts_repair_note,
    )

    return {
        "platform": platform,
        "title": chosen_title,
        "title_variants": title_variants,
        "desc": desc,
        "features": features,
        "defects": defects,
        "parts_repair_note": parts_repair_note,
    }


# =========================
# Reset helpers
# =========================
def _reset_keys(keys: List[str]) -> None:
    for k in keys:
        st.session_state.pop(k, None)


def reset_listing_builder() -> None:
    _reset_keys(
        [
            LB_PLATFORM,
            LB_BRAND,
            LB_ITEM,
            LB_MODEL,
            LB_CONDITION,
            LB_CATEGORY,
            LB_QTY,
            LB_FEATURES,
            LB_DEFECTS,
            LB_USE_COND_TMPL,
            LB_INCLUDE_PARTS_NOTE,
            LB_SELLER_CITY,
            LB_PICKUP,
            LB_SHIPPING,
            LB_HANDLING,
            LB_RETURNS,
            LB_TITLE_PICK,
        ]
    )
    st.session_state.pop("last_listing", None)
    st.session_state.pop("live_listing", None)


def reset_flip_checker() -> None:
    _reset_keys(
        [
            FC_PRESET,
            FC_SALE_PRICE,
            FC_COGS,
            FC_PACKAGING,
            FC_SHIP_METHOD,
            FC_WEIGHT,
            FC_MANUAL_SHIP,
            FC_SHIP_COST,
            FC_PLATFORM_FEE,
            FC_PROCESSING_PCT,
            FC_PROCESSING_FIXED,
        ]
    )
    st.session_state.pop("last_profit", None)


# =========================
# Live preview helper (no counters)
# =========================
def maybe_build_live_preview() -> None:
    platform = st.session_state.get(LB_PLATFORM, "eBay")
    brand = st.session_state.get(LB_BRAND, "")
    item = st.session_state.get(LB_ITEM, "")
    model = st.session_state.get(LB_MODEL, "")
    condition = st.session_state.get(LB_CONDITION, "Used - Good")
    category = st.session_state.get(LB_CATEGORY, "")
    qty = int(st.session_state.get(LB_QTY, 1) or 1)
    features_lines = st.session_state.get(LB_FEATURES, "")
    defects_lines = st.session_state.get(LB_DEFECTS, "")

    seller_city = st.session_state.get(LB_SELLER_CITY, "Jacksonville, FL")
    pickup_line = st.session_state.get(LB_PICKUP, "Porch pickup / meetup")
    shipping_line = st.session_state.get(LB_SHIPPING, "Ships within the US")
    handling_time = st.session_state.get(LB_HANDLING, "Same or next business day")
    returns_line = st.session_state.get(LB_RETURNS, "No returns (ask questions before buying)")

    use_condition_template = bool(st.session_state.get(LB_USE_COND_TMPL, True))
    include_parts_repair_note = bool(st.session_state.get(LB_INCLUDE_PARTS_NOTE, True))

    enough = bool(_clean_token(item)) or bool(_clean_token(brand))
    if not enough:
        st.session_state.pop("live_listing", None)
        return

    payload = build_listing_payload(
        platform=platform,
        brand=brand,
        item=item,
        model=model,
        condition=condition,
        category=category,
        qty=qty,
        features_lines=features_lines,
        defects_lines=defects_lines,
        seller_city=seller_city,
        pickup_line=pickup_line,
        shipping_line=shipping_line,
        handling_time=handling_time,
        returns_line=returns_line,
        include_parts_repair_note=include_parts_repair_note,
        use_condition_template=use_condition_template,
    )

    st.session_state["live_listing"] = payload


# =========================
# App boot
# =========================
st.set_page_config(
    page_title="Resale Listing Builder",
    page_icon="ð§¾",
    layout="wide",
    initial_sidebar_state="expanded",
)

cfg = load_config()
inject_css(cfg.get("accent_color", DEFAULT_CONFIG["accent_color"]))

# ---- Session + traffic context (one-time per session)
if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())

ctx = get_query_context()
st.session_state["traffic_ctx"] = ctx
st.session_state["traffic_source"] = ctx.get("traffic_source", "direct")

if "session_bumped" not in st.session_state:
    bump_stat("sessions", 1)

    stats = load_stats()
    bucket = source_bucket(st.session_state["traffic_source"])
    stats["sessions_by_source"][bucket] = int(stats["sessions_by_source"].get(bucket, 0)) + 1

    if is_tiktok_context(ctx):
        stats["tiktok_sessions"] = int(stats.get("tiktok_sessions", 0)) + 1

    save_stats(stats)
    log_event("session_started", {"ctx": ctx})
    st.session_state["session_bumped"] = True

# UI preferences
if "compact_mode" not in st.session_state:
    st.session_state["compact_mode"] = True


# =========================
# Sidebar
# =========================
ADMIN_PIN = os.getenv("ADMIN_PIN", "").strip()
is_owner = False

with st.sidebar:
    st.markdown("### Control Panel")

    st.toggle("Compact mode (better on phones)", key="compact_mode")
    st.caption("Compact mode collapses sections and reduces scrolling.")

    with st.expander("Owner Mode", expanded=False):
        st.caption("Tip: set ADMIN_PIN env var to hide admin tools from customers.")
        pin_input = st.text_input("Enter PIN", type="password", placeholder="Owner PIN")
        if ADMIN_PIN and pin_input and pin_input == ADMIN_PIN:
            is_owner = True
            st.success("Owner mode enabled")

    st.markdown("---")

    if is_owner:
        st.markdown("### Settings (Owner)")
        cfg["app_name"] = st.text_input("App name", value=cfg.get("app_name", DEFAULT_CONFIG["app_name"]))
        cfg["tagline"] = st.text_input("Tagline", value=cfg.get("tagline", DEFAULT_CONFIG["tagline"]))
        cfg["accent_color"] = st.color_picker("Accent color", value=cfg.get("accent_color", DEFAULT_CONFIG["accent_color"]))
        cfg["logo_size"] = st.slider("Logo size", 40, 120, value=int(cfg.get("logo_size", 56)), step=2)
        cfg["show_how_it_works_tab"] = st.toggle("Show How it works tab", value=bool(cfg.get("show_how_it_works_tab", True)))

        uploaded = st.file_uploader("Upload logo (PNG)", type=["png"], help="Owner-only. Overrides other logo sources.")
        if uploaded is not None:
            try:
                LOGO_OVERRIDE_PATH.write_bytes(uploaded.read())
                st.success("Logo uploaded (saved to data/logo_override.png)")
            except Exception as e:
                st.error(f"Could not save logo: {e}")

        colA, colB = st.columns(2)
        with colA:
            if st.button("Save settings", use_container_width=True):
                save_config(cfg)
                st.success("Saved. Refreshing...")
                st.rerun()
        with colB:
            if st.button("Reset defaults", use_container_width=True):
                save_config(DEFAULT_CONFIG)
                st.warning("Reset. Refreshing...")
                st.rerun()

        st.markdown("---")
        st.markdown("### Owner Dashboard")

        stats = load_stats()

        st.write(f"Sessions: {stats.get('sessions', 0)}")
        st.write(f"TikTok sessions: {stats.get('tiktok_sessions', 0)}")
        st.write(f"Profit checks: {stats.get('profit_checks', 0)}")
        st.write(f"Listings generated: {stats.get('listings_generated', 0)}")
        st.write(f"Emails captured: {stats.get('emails_captured', 0)}")

        st.markdown("#### Sessions by source")
        sbs = stats.get("sessions_by_source", {})
        cols = st.columns(3)
        cols[0].metric("TikTok", int(sbs.get("tiktok", 0)))
        cols[1].metric("Direct", int(sbs.get("direct", 0)))
        cols[2].metric("Other", int(sbs.get("other", 0)))

        st.download_button(
            "Download stats.json",
            data=json.dumps(stats, indent=2).encode("utf-8"),
            file_name="stats.json",
            mime="application/json",
            use_container_width=True,
        )

        if EVENTS_PATH.exists():
            st.download_button(
                "Download events.jsonl",
                data=EVENTS_PATH.read_bytes(),
                file_name="events.jsonl",
                mime="application/x-ndjson",
                use_container_width=True,
            )

        if WAITLIST_CSV.exists():
            st.download_button(
                "Download waitlist.csv",
                data=WAITLIST_CSV.read_bytes(),
                file_name="waitlist.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.caption("No waitlist yet.")

    else:
        st.caption("Free tool. No login. Built for fast flips.")
        st.markdown("Tracking tip (use this in TikTok bio):")
        st.code(
            "https://YOUR_APP_URL/?utm_source=tiktok&utm_medium=social&utm_campaign=organic",
            language=None,
        )

        st.markdown("---")
        st.markdown("#### Get updates")
        st.caption("Want Bulk Mode + Saved Checks? Join the waitlist (optional).")
        email_side = st.text_input("Email", key="email_sidebar", placeholder="you@example.com")
        if st.button("Join waitlist", use_container_width=True):
            ok, msg = append_waitlist(email_side, source=st.session_state.get("traffic_source", "unknown"), note="sidebar")
            (st.success(msg) if ok else st.warning(msg))


# =========================
# Header
# =========================
render_header_native(cfg)
st.caption("Listings, profit, and flip score. Smarter titles and live preview.")


# =========================
# Tabs
# =========================
tabs = ["ð§¾ Listing Builder", "â Flip Checker", "ð Coming Soon"]
if cfg.get("show_how_it_works_tab", True):
    tabs.append("â¹ï¸ How it works")

tab_objs = st.tabs(tabs)


# =========================
# Tab 1: Listing Builder
# =========================
with tab_objs[0]:
    compact = bool(st.session_state.get("compact_mode", True))

    left, right = st.columns([1.05, 0.95], gap="large")

    with left:
        st.markdown("### Build your listing")
        st.caption("Type your info and watch the output update live. Click Generate when you are ready to count it.")

        with st.expander("0) Platform", expanded=not compact):
            st.selectbox("Platform", ["eBay", "Facebook Marketplace", "Mercari", "OfferUp"], key=LB_PLATFORM)

        with st.expander("1) Item info", expanded=not compact):
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Brand", placeholder="Apple, DeWalt, Nike, etc.", key=LB_BRAND)
                st.text_input("Item", placeholder="MacBook Pro, Drill, Sneakers, etc.", key=LB_ITEM)
                st.text_input("Model / Part # (optional)", placeholder="A1990, DCD791, etc.", key=LB_MODEL)
            with col2:
                st.selectbox(
                    "Condition",
                    ["New", "Open box", "Used - Like New", "Used - Good", "Used - Fair", "Used - Poor", "For parts/repair"],
                    key=LB_CONDITION,
                )
                st.text_input("Category (optional)", placeholder="Electronics, Tools, Shoes, Home, etc.", key=LB_CATEGORY)
                st.number_input("Quantity", min_value=1, max_value=100, value=1, step=1, key=LB_QTY)

        with st.expander("2) Features & notes", expanded=not compact):
            colA, colB = st.columns([0.55, 0.45])
            with colA:
                # Make the Key Features box bigger on mobile
                features_h = 200 if compact else 160
                defects_h = 130 if compact else 120

                st.text_area(
                    "Key features (one per line)",
                    height=features_h,
                    placeholder="Example:\n16GB RAM\n512GB SSD\nIncludes charger",
                    key=LB_FEATURES,
                )
                st.text_area(
                    "Notes / defects (one per line)",
                    height=defects_h,
                    placeholder="Example:\nSmall scratch on lid\nBattery service recommended\nNo original box",
                    key=LB_DEFECTS,
                )
            with colB:
                st.markdown("#### Quality helpers")
                st.toggle("Auto-add condition template text", value=True, key=LB_USE_COND_TMPL)
                st.toggle("Extra protection text for parts/repair", value=True, key=LB_INCLUDE_PARTS_NOTE)

                st.markdown("#### Photo checklist")
                cat_lower = (st.session_state.get(LB_CATEGORY, "") or "").lower()
                if any(k in cat_lower for k in ["electronic", "laptop", "phone", "camera", "tablet", "console"]):
                    bucket = "Electronics"
                elif any(k in cat_lower for k in ["shoe", "sneaker", "shirt", "hoodie", "pants", "jacket"]):
                    bucket = "Shoes/Clothing"
                elif any(k in cat_lower for k in ["tool", "drill", "dewalt", "milwaukee", "saw"]):
                    bucket = "Tools"
                elif any(k in cat_lower for k in ["kitchen", "home", "decor", "plate", "mug", "bowl"]):
                    bucket = "Home/Kitchen"
                elif any(k in cat_lower for k in ["toy", "game", "puzzle", "lego"]):
                    bucket = "Toys/Games"
                else:
                    bucket = "Other"

                st.markdown(f'<span class="tf-badge"><span class="tf-badge-dot"></span>{bucket}</span>', unsafe_allow_html=True)
                for it in PHOTO_CHECKLISTS[bucket]:
                    st.write(f"- {it}")

        with st.expander("3) Seller profile (auto-added)", expanded=not compact):
            colA, colB = st.columns(2)
            with colA:
                st.text_input("City/Area", value="Jacksonville, FL", key=LB_SELLER_CITY)
                st.text_input("Pickup line", value="Porch pickup / meetup", key=LB_PICKUP)
                st.text_input("Shipping line", value="Ships within the US", key=LB_SHIPPING)
            with colB:
                st.text_input("Handling time", value="Same or next business day", key=LB_HANDLING)
                st.text_input("Returns policy line", value="No returns (ask questions before buying)", key=LB_RETURNS)

        # Live preview build (no counters)
        maybe_build_live_preview()

        st.markdown("---")
        cbtn1, cbtn2 = st.columns([0.45, 0.55])
        with cbtn1:
            if st.button("Reset", use_container_width=True, key="lb_reset_btn"):
                reset_listing_builder()
                st.rerun()
        with cbtn2:
            generate = st.button("Generate listing text", type="primary", use_container_width=True, key="lb_generate_btn")

        if generate:
            payload = st.session_state.get("live_listing")
            if not payload:
                maybe_build_live_preview()
                payload = st.session_state.get("live_listing")

            if payload:
                bump_stat("listings_generated", 1)
                log_event(
                    "listing_generated",
                    {
                        "platform": payload.get("platform"),
                        "category": st.session_state.get(LB_CATEGORY, ""),
                        "condition": st.session_state.get(LB_CONDITION, ""),
                    },
                )
                st.session_state["last_listing"] = payload
                toast("Generated (counted)")
            else:
                st.warning("Add at least an Item (and optionally Brand/Model) to generate.")

    with right:
        st.markdown("### Output")
        st.caption("Live preview updates as you type. Generate counts it and pins it as last output.")

        payload = st.session_state.get("last_listing") or st.session_state.get("live_listing")

        if not payload:
            st.info("Start typing an item on the left to see a live preview.")
        else:
            variants = payload.get("title_variants") or [("eBay-fit", payload.get("title", "Item for sale"))]
            display = [f"{lab} - {t}" for (lab, t) in variants]

            default_index = 0
            prev_choice = st.session_state.get(LB_TITLE_PICK)
            if prev_choice in display:
                default_index = display.index(prev_choice)

            picked = st.selectbox(
                "Choose a title (optimizer)",
                options=display,
                index=default_index,
                key=LB_TITLE_PICK,
                help="Labeled variants: eBay-fit, short, super short, etc.",
            )

            idx = display.index(picked)
            chosen_title = variants[idx][1]

            platform_out = payload.get("platform", "eBay")
            condition = st.session_state.get(LB_CONDITION, "Used - Good")
            category = st.session_state.get(LB_CATEGORY, "")
            qty = int(st.session_state.get(LB_QTY, 1) or 1)
            seller_city = st.session_state.get(LB_SELLER_CITY, "Jacksonville, FL")
            pickup_line = st.session_state.get(LB_PICKUP, "Porch pickup / meetup")
            shipping_line = st.session_state.get(LB_SHIPPING, "Ships within the US")
            handling_time = st.session_state.get(LB_HANDLING, "Same or next business day")
            returns_line = st.session_state.get(LB_RETURNS, "No returns (ask questions before buying)")

            desc = platform_description(
                platform=platform_out,
                title=chosen_title,
                condition=condition,
                category=category,
                qty=qty,
                features=payload.get("features", []),
                defects=payload.get("defects", []),
                seller_city=seller_city,
                pickup_line=pickup_line,
                shipping_line=shipping_line,
                handling_time=handling_time,
                returns_line=returns_line,
                parts_repair_note=payload.get("parts_repair_note", ""),
            )

            title_len = len(chosen_title)
            title_fit = "Fits eBay (<= 80)" if title_len <= 80 else "Over 80 chars"

            def _title_card():
                st.markdown(
                    f"<div class='tf-subtle'>Length: <b>{title_len}</b> &nbsp; ÂÂ¢ &nbsp; {title_fit}</div>",
                    unsafe_allow_html=True,
                )
                st.text_area("title_out", value=chosen_title, height=80, label_visibility="collapsed")
                c1, c2 = st.columns([0.55, 0.45])
                with c1:
                    copy_btn("Copy title", chosen_title, key="copy_title_btn", flash_key="copy_title_btn")
                with c2:
                    st.download_button(
                        "Download title (.txt)",
                        data=(chosen_title + "\n").encode("utf-8"),
                        file_name="title.txt",
                        mime="text/plain",
                        use_container_width=True,
                    )

            def _desc_card():
                st.text_area(
                    "desc_out",
                    value=desc,
                    height=300 if compact else 260,
                    label_visibility="collapsed",
                )
                c1, c2 = st.columns([0.55, 0.45])
                with c1:
                    copy_btn("Copy description", desc, key="copy_desc_btn", flash_key="copy_desc_btn")
                with c2:
                    st.download_button(
                        "Download description (.txt)",
                        data=desc.encode("utf-8"),
                        file_name=f"{platform_out.replace(' ','_').lower()}_description.txt",
                        mime="text/plain",
                        use_container_width=True,
                    )

            card("Title", _title_card, flash_key="copy_title_btn")
            card(f"Description ({platform_out})", _desc_card, flash_key="copy_desc_btn")

            st.markdown("---")
            all_text = f"TITLE:\n{chosen_title}\n\nDESCRIPTION ({platform_out}):\n{desc}\n"
            copy_btn("Copy ALL (title + description)", all_text, key="copy_all_listing_btn", flash_key="copy_desc_btn")

    st.markdown("---")
    st.markdown("### Get updates (optional)")
    st.caption("Want Bulk Mode / Saved Checks? Join the waitlist. No spam.")
    colw1, colw2 = st.columns([0.6, 0.4])
    with colw1:
        email_main = st.text_input("Email address", key="email_main", placeholder="you@example.com")
    with colw2:
        if st.button("Join waitlist", key="join_waitlist_main", use_container_width=True):
            ok, msg = append_waitlist(email_main, source=st.session_state.get("traffic_source", "unknown"), note="main_footer")
            (st.success(msg) if ok else st.warning(msg))


# =========================
# Tab 2: Flip Checker
# =========================
with tab_objs[1]:
    compact = bool(st.session_state.get("compact_mode", True))

    st.markdown("### Flip Checker")
    st.caption("Grouped inputs + quick presets + clear all-in summary.")

    st.markdown("#### Quick presets")
    preset = st.selectbox(
        "Preset",
        [
            "eBay (typical)",
            "Facebook Marketplace (no platform fee)",
            "Local pickup (no shipping)",
            "Custom",
        ],
        key=FC_PRESET,
    )

    if preset == "Facebook Marketplace (no platform fee)":
        preset_platform_fee = 0.0
        preset_processing_pct = 2.9
        preset_processing_fixed = 0.30
        preset_ship_method = "Local pickup"
    elif preset == "Local pickup (no shipping)":
        preset_platform_fee = 13.25
        preset_processing_pct = 2.9
        preset_processing_fixed = 0.30
        preset_ship_method = "Local pickup"
    else:
        preset_platform_fee = 13.25
        preset_processing_pct = 2.9
        preset_processing_fixed = 0.30
        preset_ship_method = "Ground (est.)"

    with st.expander("1) Sale + cost", expanded=not compact):
        c1, c2, c3 = st.columns(3)
        with c1:
            sale_price = st.number_input("Target sale price ($)", min_value=0.0, value=79.99, step=1.0, key=FC_SALE_PRICE)
        with c2:
            cogs = st.number_input("Your cost (COGS) ($)", min_value=0.0, value=25.00, step=1.0, key=FC_COGS)
        with c3:
            packaging_cost = st.number_input("Packaging cost ($)", min_value=0.0, value=1.50, step=0.25, key=FC_PACKAGING)

    with st.expander("2) Shipping", expanded=not compact):
        c1, c2, c3 = st.columns(3)
        with c1:
            shipping_method = st.selectbox(
                "Shipping method",
                ["Ground (est.)", "Priority (est.)", "Local pickup"],
                index=["Ground (est.)", "Priority (est.)", "Local pickup"].index(preset_ship_method),
                key=FC_SHIP_METHOD,
            )
        with c2:
            weight = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25, key=FC_WEIGHT)
        with c3:
            manual_shipping = st.toggle("Manually enter shipping cost", value=False, key=FC_MANUAL_SHIP)

        if manual_shipping:
            shipping_cost = st.number_input("Shipping cost ($)", min_value=0.0, value=8.00, step=0.5, key=FC_SHIP_COST)
        else:
            shipping_cost = shipping_estimate(shipping_method, weight)
            st.caption(f"Estimated shipping: {money(shipping_cost)}")

    with st.expander("3) Fees", expanded=not compact):
        c1, c2, c3 = st.columns(3)
        with c1:
            platform_fee_pct = st.number_input(
                "Platform fee %",
                min_value=0.0,
                max_value=30.0,
                value=float(preset_platform_fee) if preset != "Custom" else 13.25,
                step=0.25,
                key=FC_PLATFORM_FEE,
            )
        with c2:
            processing_pct = st.number_input(
                "Processing %",
                min_value=0.0,
                max_value=10.0,
                value=float(preset_processing_pct) if preset != "Custom" else 2.90,
                step=0.10,
                key=FC_PROCESSING_PCT,
            )
        with c3:
            processing_fixed = st.number_input(
                "Processing fixed ($)",
                min_value=0.0,
                max_value=2.0,
                value=float(preset_processing_fixed) if preset != "Custom" else 0.30,
                step=0.05,
                key=FC_PROCESSING_FIXED,
            )

    st.markdown("---")
    b1, b2 = st.columns([0.42, 0.58])
    with b1:
        if st.button("Reset", use_container_width=True, key="fc_reset_btn"):
            reset_flip_checker()
            st.rerun()
    with b2:
        calc_btn = st.button("Calculate profit", type="primary", use_container_width=True, key="fc_calc_btn")

    if calc_btn:
        bump_stat("profit_checks", 1)
        log_event("profit_checked", {"sale_price": sale_price, "cogs": cogs, "shipping_method": shipping_method, "preset": preset})

        result = calc_profit(
            sale_price=sale_price,
            cogs=cogs,
            ebay_fee_pct=platform_fee_pct,
            processing_pct=processing_pct,
            processing_fixed=processing_fixed,
            shipping_cost=shipping_cost,
            packaging_cost=packaging_cost,
        )

        score = flip_score(result["profit"], result["margin_pct"], sale_price)
        badge = flip_badge(score)

        st.session_state["last_profit"] = {
            **result,
            "score": score,
            "badge": badge,
            "shipping_cost": shipping_cost,
            "packaging_cost": packaging_cost,
            "cogs": cogs,
            "sale_price": sale_price,
        }

    result = st.session_state.get("last_profit")
    if not result:
        st.info("Click Calculate profit to get numbers + flip score.")
    else:
        profit = float(result["profit"])
        margin = float(result["margin_pct"])
        score = float(result["score"])
        badge = str(result["badge"])

        top = st.columns(4)
        top[0].metric("Profit", money(profit))
        top[1].metric("Margin", f"{margin:.1f}%")
        top[2].metric("Flip Score", f"{score} / 10")
        top[3].metric("Verdict", badge)
        # Colorful verdict pill
        cls = "tf-verdict-pill tf-verdict-good"
        if "Bad" in badge:
            cls = "tf-verdict-pill tf-verdict-bad"
        elif "Risky" in badge:
            cls = "tf-verdict-pill tf-verdict-risky"
        elif "Great" in badge:
            cls = "tf-verdict-pill tf-verdict-great"

        st.markdown(f"<span class='{cls}'>Verdict: {badge}</span>", unsafe_allow_html=True)


        card(
            "Summary",
            lambda: (
                st.write(f"All-in cost: {money(float(result['total_cost']))}"),
                st.write(f"Sale price: {money(float(result['sale_price']))}"),
                st.write(f"Profit: {money(profit)}  |  Margin: {margin:.1f}%  |  Score: {score}/10"),
            ),
        )

        if "Bad" in badge:
            st.error("Pass unless you can lower cost or raise sale price.")
        elif "Risky" in badge:
            st.warning("Tight margins. Negotiate, reduce shipping, or increase sale price.")
        elif "Good" in badge:
            st.success("â Solid deal for most resellers.")
        else:
            st.success("Strong profit/margin combo.")

        st.markdown("#### Breakdown")
        b1, b2 = st.columns(2)
        with b1:
            st.write(f"- Platform fee: {money(result['ebay_fee'])}")
            st.write(f"- Processing: {money(result['processing_fee'])}")
            st.write(f"- Shipping: {money(float(result['shipping_cost']))}")
            st.write(f"- Packaging: {money(float(result['packaging_cost']))}")
        with b2:
            st.write(f"- COGS: {money(float(result['cogs']))}")
            st.write(f"- Total fees: {money(result['total_fees'])}")
            st.write(f"- Total cost (all-in): {money(result['total_cost'])}")

        st.markdown("---")
        st.markdown("### Save profit check")
        st.button("Save this check (Pro)", disabled=True, use_container_width=True)
        st.caption("Planned: saved checks, history, notes, and exports. Not live yet.")


# =========================
# Tab 3: Coming Soon
# =========================
with tab_objs[2]:
    st.markdown("## Coming Soon")
    st.caption("Free stays free. Pro (later) is for speed + tracking. Nothing is locked right now.")

    st.markdown("### Planned Pro features (not live yet)")
    st.markdown(
        """
- Saved Profit Checks (history + notes per item)
- Bulk Mode (check 5-20 items at once)
- Inventory Tracker (buy price, sold price, net profit)
- CSV Exports (taxes + bookkeeping)
- Smarter Flip Score presets (time-to-sell vs max profit)
        """.strip()
    )

    st.markdown("---")
    st.markdown("### Join the waitlist")
    st.caption("Early users get first access. No spam.")
    colx, coly = st.columns([0.7, 0.3])
    with colx:
        email_cs = st.text_input("Email", key="email_comingsoon", placeholder="you@example.com")
        note_cs = st.text_input("What feature do you want most? (optional)", key="note_comingsoon", placeholder="Saved checks, bulk mode, exports...")
    with coly:
        if st.button("Join waitlist", key="join_waitlist_cs", use_container_width=True):
            ok, msg = append_waitlist(email_cs, source=st.session_state.get("traffic_source", "unknown"), note=note_cs)
            (st.success(msg) if ok else st.warning(msg))

    st.markdown("---")
    st.info("Tracking tip: use UTM links in bio, e.g. ?utm_source=tiktok&utm_medium=social&utm_campaign=organic")


# =========================
# Tab 4: How it works
# =========================
if cfg.get("show_how_it_works_tab", True):
    with tab_objs[3]:
        st.markdown("## How it works")
        st.markdown(
            """
### What this app does
- Drafts copy/paste listings for eBay, Facebook Marketplace, Mercari, and OfferUp
- Calculates profit after platform fee, processing fee, shipping, and packaging

### v1.5.1 update
- Emoji-safe UI (no broken characters on mobile)
- Smarter title rules and labeled title variants
- Live preview while typing (Generate still counts it for stats)

### Privacy
- No login required
- Waitlist is optional
- Tracking is anonymous counters + events (no personal identity stored)
            """.strip()
        )
