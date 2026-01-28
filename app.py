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
    "tiktok_sessions": 0,  # kept for compatibility
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
    """Append one JSON event per line to data/events.jsonl (safe + simple)."""
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
        return False, "That doesn’t look like a valid email."

    new_file = not WAITLIST_CSV.exists()
    if new_file:
        WAITLIST_CSV.write_text("timestamp_utc,email,source,note\n", encoding="utf-8")

    existing = WAITLIST_CSV.read_text(encoding="utf-8", errors="ignore").splitlines()[1:]
    for line in existing:
        parts = line.split(",")
        if len(parts) >= 2 and normalize_email(parts[1]) == email:
            return False, "You’re already on the list ✅"

    ts = dt.datetime.utcnow().isoformat()
    safe_source = (source or "").replace(",", " ").strip()
    safe_note = (note or "").replace(",", " ").replace("\n", " ").strip()
    with WAITLIST_CSV.open("a", encoding="utf-8") as f:
        f.write(f"{ts},{email},{safe_source},{safe_note}\n")

    bump_stat("emails_captured", 1)
    log_event("waitlist_joined", {"note": safe_note})
    return True, "You’re on the waitlist ✅"


# =========================
# Helpers: query tracking (src + UTMs)
# =========================
def _qp_get(qp: Any, key: str) -> str:
    """Compatible getter for Streamlit query params across versions."""
    try:
        val = qp.get(key, "")
        if isinstance(val, list):
            val = val[0] if val else ""
        return (val or "").strip()
    except Exception:
        return ""


def get_query_context() -> Dict[str, str]:
    """
    Supports:
      - legacy: ?src=tiktok
      - standard: ?utm_source=tiktok&utm_medium=social&utm_campaign=organic
    """
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

    # Normalize common sources
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


def get_logo_bytes_and_mime() -> Tuple[Optional[bytes], Optional[str]]:
    override = read_file_bytes(LOGO_OVERRIDE_PATH)
    if override:
        return override, "image/png"

    png = read_file_bytes(ASSETS_DIR / "logo.png")
    if png:
        return png, "image/png"

    svg = read_file_bytes(ASSETS_DIR / "logo.svg")
    if svg:
        return svg, "image/svg+xml"

    return None, None


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


def copy_btn(label: str, text: str, key: str) -> None:
    if st.button(label, key=key, use_container_width=True):
        components.html(_clipboard_js(text), height=0)
        toast("Copied ✅")


def card(title: str, body_fn) -> None:
    st.markdown(f'<div class="tf-card"><div class="tf-card-title">{title}</div>', unsafe_allow_html=True)
    body_fn()
    st.markdown("</div>", unsafe_allow_html=True)


# =========================
# Styling (dark theme + Android/iOS readable + visible control panel)
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
            --text: #F3F4F6;      /* solid text helps Android */
            --muted: #B6BAC4;
            --radius: 16px;
            --radiusSm: 12px;
          }}

          html, body, [class*="css"] {{
            font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji";
            color: var(--text) !important;
          }}

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

          /* Sidebar MUST be solid */
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

          /* Cross-device text enforcement */
          h1, h2, h3, h4, h5, h6, p, li, label, span {{
            color: var(--text) !important;
          }}
          [data-testid="stMarkdownContainer"] * {{
            color: var(--text) !important;
          }}
          [data-testid="stCaptionContainer"] * {{
            color: var(--muted) !important;
          }}

          /* Inputs */
          .stTextInput > div > div > input,
          .stNumberInput > div > div > input,
          .stTextArea textarea {{
            background: rgba(255,255,255,0.04) !important;
            border: 1px solid var(--border) !important;
            border-radius: var(--radiusSm) !important;
            color: var(--text) !important;
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
            padding: 0.70rem 0.95rem !important;
            font-weight: 650 !important;
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
          }}
          .stTabs [aria-selected="true"] {{
            background: rgba(255,255,255,0.08) !important;
            color: var(--text) !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
          }}

          /* Metrics */
          [data-testid="stMetric"] {{
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 14px 14px;
          }}
          [data-testid="stMetric"] * {{
            color: var(--text) !important;
          }}

          /* Expander */
          details {{
            background: rgba(255,255,255,0.03);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 8px 10px;
          }}

          /* Code blocks */
          pre {{
            background: rgba(255,255,255,0.04) !important;
            border: 1px solid var(--border) !important;
            border-radius: var(--radius) !important;
            box-shadow: none !important;
          }}
          pre, code {{
            color: var(--text) !important;
          }}

          /* Card helper */
          .tf-card {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 14px 14px;
            margin: 10px 0;
          }}
          .tf-card-title {{
            font-weight: 800;
            font-size: 1.05rem;
            margin-bottom: 10px;
          }}
          .tf-pill {{
            display:inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.14);
            color: var(--muted);
            font-size: 0.85rem;
          }}

          hr {{
            border-color: rgba(255,255,255,0.10) !important;
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
    logo_bytes, mime = get_logo_bytes_and_mime()
    size = int(cfg.get("logo_size", 56))

    c1, c2 = st.columns([0.72, 0.28], vertical_alignment="center")

    with c1:
        left = st.columns([0.12, 0.88], vertical_alignment="center")
        with left[0]:
            if logo_bytes:
                if mime == "image/svg+xml":
                    # Streamlit can display svg bytes as image
                    st.image(logo_bytes, width=size)
                else:
                    st.image(logo_bytes, width=size)
            else:
                st.markdown("### 🧾")
        with left[1]:
            st.markdown(f"## {cfg.get('app_name','Resale Listing Builder')}")
            st.caption(cfg.get("tagline", ""))

    with c2:
        st.caption("Offline-friendly • v1.3")
        st.caption("No login • Dark mode ✅")

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
        return "❌ Bad Flip"
    if score <= 6:
        return "⚠️ Risky"
    if score <= 8:
        return "✅ Good Flip"
    return "🔥 Great Flip"


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
    "For parts/repair": "For parts/repair — sold as-is. May be missing parts or have issues not listed. No returns.",
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


def _keywords_from_features(features_lines: str, max_k: int = 3) -> List[str]:
    lines = [ln.strip() for ln in (features_lines or "").splitlines() if ln.strip()]
    # Keep short keyword-ish lines
    keep: List[str] = []
    for ln in lines[:10]:
        if len(ln) <= 28:
            keep.append(ln)
        if len(keep) >= max_k:
            break
    return keep


def build_title_variants(
    brand: str,
    item: str,
    model: str,
    condition: str,
    features_lines: str,
    max_variants: int = 6,
) -> List[str]:
    b = (brand or "").strip()
    it = (item or "").strip()
    m = (model or "").strip()
    cond = (condition or "").strip()
    kws = _keywords_from_features(features_lines)

    base_parts = [b, it, m]
    base = " ".join([p for p in base_parts if p]).strip() or "Item for sale"

    variants: List[str] = []
    variants.append(base)
    if m:
        variants.append(" ".join([it, b, m]).strip())
    if kws:
        variants.append(" ".join([b, it, m, kws[0]]).strip())
    if len(kws) >= 2:
        variants.append(" ".join([b, it, kws[0], kws[1]]).strip())
    if cond and cond != "For parts/repair":
        variants.append(" ".join([b, it, m, cond]).strip())
    if cond == "For parts/repair":
        variants.append(" ".join([b, it, m, "For Parts/Repair"]).strip())

    # Unique + trimmed
    uniq = []
    seen = set()
    for v in variants:
        v2 = re.sub(r"\s+", " ", v).strip()
        if v2 and v2.lower() not in seen:
            seen.add(v2.lower())
            uniq.append(v2)
        if len(uniq) >= max_variants:
            break
    return uniq


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

    # eBay: markdown-ish
    if platform == "ebay":
        return f"""
## {title}

{("### Key features\n" + feat_bul) if feat_bul else ""}

{("### Notes / defects\n" + def_bul) if def_bul else ""}

**Condition:** {condition}
**Quantity:** {qty}
**Category:** {category or "—"}

**Location:** {seller_city or "—"}
**Pickup:** {pickup_line or "—"}
**Shipping:** {shipping_line or "—"}
**Handling time:** {handling_time or "—"}
**Returns:** {returns_line or "—"}

{parts_repair_note}
""".strip()

    # FB: simple readable
    if platform == "facebook marketplace" or platform == "facebook":
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
            lines.extend([f"• {x}" for x in features])
            lines.append("")
        if defects:
            lines.append("Notes/defects:")
            lines.extend([f"• {x}" for x in defects])
            lines.append("")
        lines.append(f"Pickup: {pickup_line or '—'}")
        lines.append(f"Shipping: {shipping_line or '—'}")
        lines.append(f"Location: {seller_city or '—'}")
        lines.append(f"Returns: {returns_line or '—'}")
        if parts_repair_note:
            lines.append("")
            lines.append(parts_repair_note.replace("**", ""))  # remove markdown emphasis
        return "\n".join(lines).strip()

    # Mercari: short + skimmable
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

    # OfferUp: friendly + direct
    if platform == "offerup":
        lines = []
        lines.append(title)
        lines.append("")
        lines.append(f"Condition: {condition}")
        if features:
            lines.append("")
            lines.append("Highlights:")
            lines.extend([f"• {x}" for x in features])
        if defects:
            lines.append("")
            lines.append("Notes:")
            lines.extend([f"• {x}" for x in defects])
        lines.append("")
        lines.append(f"Pickup: {pickup_line or '—'}")
        lines.append(f"Location: {seller_city or '—'}")
        if parts_repair_note:
            lines.append("")
            lines.append(parts_repair_note.replace("**", ""))
        return "\n".join(lines).strip()

    # fallback (generic)
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

    # Condition template
    if use_condition_template and condition in CONDITION_TEMPLATES:
        tmpl = CONDITION_TEMPLATES[condition]
        # avoid duplicating if already included
        if tmpl and tmpl not in defects:
            defects = defects + [tmpl]

    title_variants = build_title_variants(brand, item, model, condition, features_lines, max_variants=6)
    chosen_title = title_variants[0] if title_variants else "Item for sale"

    parts_repair_note = ""
    if include_parts_repair_note and condition == "For parts/repair":
        parts_repair_note = (
            "**For parts/repair note:** Sold as-is for parts/repair. "
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
# App boot
# =========================
st.set_page_config(
    page_title="Resale Listing Builder",
    page_icon="🧾",
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
    st.caption("Compact mode collapses sections + reduces scrolling.")

    with st.expander("🔒 Owner Mode", expanded=False):
        st.caption("Tip: set `ADMIN_PIN` env var to hide admin tools from customers.")
        pin_input = st.text_input("Enter PIN", type="password", placeholder="Owner PIN")
        if ADMIN_PIN and pin_input and pin_input == ADMIN_PIN:
            is_owner = True
            st.success("Owner mode enabled ✅")

    st.markdown("---")

    if is_owner:
        st.markdown("### ⚙️ Settings (Owner)")
        cfg["app_name"] = st.text_input("App name", value=cfg.get("app_name", DEFAULT_CONFIG["app_name"]))
        cfg["tagline"] = st.text_input("Tagline", value=cfg.get("tagline", DEFAULT_CONFIG["tagline"]))
        cfg["accent_color"] = st.color_picker("Accent color", value=cfg.get("accent_color", DEFAULT_CONFIG["accent_color"]))
        cfg["logo_size"] = st.slider("Logo size", 40, 120, value=int(cfg.get("logo_size", 56)), step=2)
        cfg["show_how_it_works_tab"] = st.toggle("Show “How it works” tab", value=bool(cfg.get("show_how_it_works_tab", True)))

        uploaded = st.file_uploader("Upload logo (PNG)", type=["png"], help="Owner-only. Overrides other logo sources.")
        if uploaded is not None:
            try:
                LOGO_OVERRIDE_PATH.write_bytes(uploaded.read())
                st.success("Logo uploaded ✅ (saved to data/logo_override.png)")
            except Exception as e:
                st.error(f"Could not save logo: {e}")

        colA, colB = st.columns(2)
        with colA:
            if st.button("Save settings", use_container_width=True):
                save_config(cfg)
                st.success("Saved ✅ Refreshing…")
                st.rerun()
        with colB:
            if st.button("Reset defaults", use_container_width=True):
                save_config(DEFAULT_CONFIG)
                st.warning("Reset. Refreshing…")
                st.rerun()

        st.markdown("---")
        st.markdown("### 📊 Owner Dashboard")

        stats = load_stats()

        st.write(f"**Sessions:** {stats.get('sessions', 0)}")
        st.write(f"**TikTok sessions:** {stats.get('tiktok_sessions', 0)}  *(supports `?src=tiktok` + `?utm_source=tiktok`)*")
        st.write(f"**Profit checks:** {stats.get('profit_checks', 0)}")
        st.write(f"**Listings generated:** {stats.get('listings_generated', 0)}")
        st.write(f"**Emails captured:** {stats.get('emails_captured', 0)}")

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
            st.caption("No waitlist yet (waitlist.csv appears after first signup).")

    else:
        st.caption("Free tool. No login. Built for fast flips.")
        st.markdown("**Tracking tip (use this in TikTok bio):**")
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
st.caption("Listings + Profit + **Flip Score**. Dark mode by default. ✅")


# =========================
# Tabs
# =========================
tabs = ["🧾 Listing Builder", "✅ Flip Checker", "🚀 Coming Soon"]
if cfg.get("show_how_it_works_tab", True):
    tabs.append("ℹ️ How it works")

tab_objs = st.tabs(tabs)


# =========================
# Tab 1: Listing Builder
# =========================
with tab_objs[0]:
    compact = bool(st.session_state.get("compact_mode", True))

    left, right = st.columns([1.05, 0.95], gap="large")

    with left:
        st.markdown("### Build your listing")
        st.caption("Pick a platform, fill the basics, and generate clean copy/paste output.")

        with st.expander("0) Platform", expanded=not compact):
            platform = st.selectbox("Platform", ["eBay", "Facebook Marketplace", "Mercari", "OfferUp"])

        with st.expander("1) Item info", expanded=not compact):
            col1, col2 = st.columns(2)
            with col1:
                brand = st.text_input("Brand", placeholder="Apple, DeWalt, Nike, etc.")
                item = st.text_input("Item", placeholder="MacBook Pro, Drill, Sneakers, etc.")
                model = st.text_input("Model / Part # (optional)", placeholder="A1990, DCD791, etc.")
            with col2:
                condition = st.selectbox(
                    "Condition",
                    ["New", "Open box", "Used - Like New", "Used - Good", "Used - Fair", "Used - Poor", "For parts/repair"],
                )
                category = st.text_input("Category (optional)", placeholder="Electronics, Tools, Shoes, Home, etc.")
                qty = st.number_input("Quantity", min_value=1, max_value=100, value=1, step=1)

        with st.expander("2) Features & notes", expanded=not compact):
            colA, colB = st.columns([0.55, 0.45])
            with colA:
                features_lines = st.text_area(
                    "Key features (one per line)",
                    height=140 if not compact else 110,
                    placeholder="Example:\n16GB RAM\n512GB SSD\nIncludes charger",
                )
                defects_lines = st.text_area(
                    "Notes / defects (one per line)",
                    height=120 if not compact else 95,
                    placeholder="Example:\nSmall scratch on lid\nBattery service recommended\nNo original box",
                )
            with colB:
                st.markdown("#### Quality helpers")
                use_condition_template = st.toggle("Auto-add condition template text", value=True)
                include_parts_repair_note = st.toggle("Extra protection text for parts/repair", value=True)

                st.markdown("#### Photo checklist")
                # pick checklist bucket
                cat_lower = (category or "").lower()
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

                st.markdown(f'<span class="tf-pill">{bucket}</span>', unsafe_allow_html=True)
                for it in PHOTO_CHECKLISTS[bucket]:
                    st.write(f"- {it}")

        with st.expander("3) Seller profile (auto-added)", expanded=not compact):
            colA, colB = st.columns(2)
            with colA:
                seller_city = st.text_input("City/Area", value="Jacksonville, FL")
                pickup_line = st.text_input("Pickup line", value="Porch pickup / meetup")
                shipping_line = st.text_input("Shipping line", value="Ships within the US")
            with colB:
                handling_time = st.text_input("Handling time", value="Same or next business day")
                returns_line = st.text_input("Returns policy line", value="No returns (ask questions before buying)")

        st.markdown("---")
        generate = st.button("Generate listing text", type="primary", use_container_width=True)

        if generate:
            bump_stat("listings_generated", 1)
            log_event("listing_generated", {"platform": platform, "category": category, "condition": condition})

            payload = build_listing_payload(
                platform=platform,
                brand=brand,
                item=item,
                model=model,
                condition=condition,
                category=category,
                qty=int(qty),
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
            st.session_state["last_listing"] = payload

    with right:
        st.markdown("### Output")
        st.caption("Clean cards with one-tap copy (works great on phones).")

        payload = st.session_state.get("last_listing")
        if not payload:
            st.info("Fill out the item and click **Generate listing text**.")
        else:
            # Allow selecting the best title
            variants = payload.get("title_variants") or [payload.get("title", "Item for sale")]
            selected = st.selectbox(
                "Choose a title (optimizer)",
                options=variants,
                index=0,
                help="Pick the best keyword order. Aim for ≤ 80 characters for eBay.",
            )
            payload["title"] = selected
            # Rebuild description with selected title so all outputs match
            # (Keeps platform consistent + updates title inside description)
            # We'll use platform_description with existing parsed features/defects.
            platform = payload.get("platform", "eBay")
            desc = platform_description(
                platform=platform,
                title=payload["title"],
                condition=condition,
                category=category,
                qty=int(qty),
                features=payload.get("features", []),
                defects=payload.get("defects", []),
                seller_city=seller_city,
                pickup_line=pickup_line,
                shipping_line=shipping_line,
                handling_time=handling_time,
                returns_line=returns_line,
                parts_repair_note=payload.get("parts_repair_note", ""),
            )
            payload["desc"] = desc
            st.session_state["last_listing"] = payload

            title_len = len(payload["title"])
            title_fit = "✅ Fits eBay (≤80)" if title_len <= 80 else "⚠️ Over 80 chars"

            def _title_card():
                st.write(f"**Length:** {title_len} • {title_fit}")
                st.text_area("title_out", value=payload["title"], height=80, label_visibility="collapsed")
                c1, c2 = st.columns([0.55, 0.45])
                with c1:
                    copy_btn("Copy title", payload["title"], key="copy_title_btn")
                with c2:
                    st.download_button(
                        "Download title (.txt)",
                        data=(payload["title"] + "\n").encode("utf-8"),
                        file_name="title.txt",
                        mime="text/plain",
                        use_container_width=True,
                    )

            def _desc_card():
                st.text_area("desc_out", value=payload["desc"], height=260 if not compact else 210, label_visibility="collapsed")
                c1, c2 = st.columns([0.55, 0.45])
                with c1:
                    copy_btn("Copy description", payload["desc"], key="copy_desc_btn")
                with c2:
                    st.download_button(
                        "Download description (.txt)",
                        data=payload["desc"].encode("utf-8"),
                        file_name=f"{payload.get('platform','platform').replace(' ','_').lower()}_description.txt",
                        mime="text/plain",
                        use_container_width=True,
                    )

            card("Title", _title_card)
            card(f"Description ({payload.get('platform','eBay')})", _desc_card)

            st.markdown("---")
            all_text = f"TITLE:\n{payload['title']}\n\nDESCRIPTION ({payload.get('platform','eBay')}):\n{payload['desc']}\n"
            copy_btn("Copy ALL (title + description)", all_text, key="copy_all_listing_btn")

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
    st.caption("Cleaner flow: grouped inputs + quick presets + clear all-in summary.")

    st.markdown("#### Quick presets")
    preset = st.selectbox(
        "Preset",
        [
            "eBay (typical)",
            "Facebook Marketplace (no platform fee)",
            "Local pickup (no shipping)",
            "Custom",
        ],
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
            sale_price = st.number_input("Target sale price ($)", min_value=0.0, value=79.99, step=1.0)
        with c2:
            cogs = st.number_input("Your cost (COGS) ($)", min_value=0.0, value=25.00, step=1.0)
        with c3:
            packaging_cost = st.number_input("Packaging cost ($)", min_value=0.0, value=1.50, step=0.25)

    with st.expander("2) Shipping", expanded=not compact):
        c1, c2, c3 = st.columns(3)
        with c1:
            shipping_method = st.selectbox(
                "Shipping method",
                ["Ground (est.)", "Priority (est.)", "Local pickup"],
                index=["Ground (est.)", "Priority (est.)", "Local pickup"].index(preset_ship_method),
            )
        with c2:
            weight = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25)
        with c3:
            manual_shipping = st.toggle("Manually enter shipping cost", value=False)

        if manual_shipping:
            shipping_cost = st.number_input("Shipping cost ($)", min_value=0.0, value=8.00, step=0.5)
        else:
            shipping_cost = shipping_estimate(shipping_method, weight)
            st.caption(f"Estimated shipping: **{money(shipping_cost)}**")

    with st.expander("3) Fees", expanded=not compact):
        c1, c2, c3 = st.columns(3)
        with c1:
            platform_fee_pct = st.number_input(
                "Platform fee %",
                min_value=0.0,
                max_value=30.0,
                value=float(preset_platform_fee) if preset != "Custom" else 13.25,
                step=0.25,
            )
        with c2:
            processing_pct = st.number_input(
                "Processing %",
                min_value=0.0,
                max_value=10.0,
                value=float(preset_processing_pct) if preset != "Custom" else 2.90,
                step=0.10,
            )
        with c3:
            processing_fixed = st.number_input(
                "Processing fixed ($)",
                min_value=0.0,
                max_value=2.0,
                value=float(preset_processing_fixed) if preset != "Custom" else 0.30,
                step=0.05,
            )

    st.markdown("---")
    if st.button("Calculate profit", type="primary", use_container_width=True):
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
        st.info("Click **Calculate profit** to get numbers + Flip Score.")
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

        card(
            "Summary",
            lambda: (
                st.write(f"**All-in cost:** {money(float(result['total_cost']))}"),
                st.write(f"**Sale price:** {money(float(result['sale_price']))}"),
                st.write(f"**Profit:** {money(profit)}  •  **Margin:** {margin:.1f}%  •  **Score:** {score}/10"),
            ),
        )

        if "Bad" in badge:
            st.error("❌ I’d pass unless you can lower cost or raise sale price.")
        elif "Risky" in badge:
            st.warning("⚠️ Tight margins — negotiate, reduce shipping, or increase sale price.")
        elif "Good" in badge:
            st.success("✅ Solid deal for most resellers.")
        else:
            st.success("🔥 Great deal — strong profit/margin combo.")

        st.markdown("#### Breakdown")
        b1, b2 = st.columns(2)
        with b1:
            st.write(f"- Platform fee: **{money(result['ebay_fee'])}**")
            st.write(f"- Processing: **{money(result['processing_fee'])}**")
            st.write(f"- Shipping: **{money(float(result['shipping_cost']))}**")
            st.write(f"- Packaging: **{money(float(result['packaging_cost']))}**")
        with b2:
            st.write(f"- COGS: **{money(float(result['cogs']))}**")
            st.write(f"- Total fees: **{money(result['total_fees'])}**")
            st.write(f"- Total cost (all-in): **{money(result['total_cost'])}**")

        st.markdown("---")
        st.markdown("### 💾 Save profit check")
        st.button("Save this check (Pro)", disabled=True, use_container_width=True)
        st.caption("Planned: saved checks, history, notes, and exports. (Not live yet.)")


# =========================
# Tab 3: Coming Soon
# =========================
with tab_objs[2]:
    st.markdown("## 🚀 Coming Soon")
    st.caption("Free stays free. Pro (later) is for speed + tracking — nothing is locked right now.")

    st.markdown("### Planned Pro features (not live yet)")
    st.markdown(
        """
- 💾 **Saved Profit Checks** (history + notes per item)  
- ⚡ **Bulk Mode** (check 5–20 items at once)  
- 📦 **Inventory Tracker** (buy price, sold price, net profit)  
- 📁 **CSV Exports** (taxes + bookkeeping)  
- 🧠 **Smarter Flip Score** presets (time-to-sell vs max profit)  
        """.strip()
    )

    st.markdown("---")
    st.markdown("### Join the waitlist")
    st.caption("Early users get first access. No spam.")
    colx, coly = st.columns([0.7, 0.3])
    with colx:
        email_cs = st.text_input("Email", key="email_comingsoon", placeholder="you@example.com")
        note_cs = st.text_input("What feature do you want most? (optional)", key="note_comingsoon", placeholder="Saved checks, bulk mode, exports…")
    with coly:
        if st.button("Join waitlist", key="join_waitlist_cs", use_container_width=True):
            ok, msg = append_waitlist(email_cs, source=st.session_state.get("traffic_source", "unknown"), note=note_cs)
            (st.success(msg) if ok else st.warning(msg))

    st.markdown("---")
    st.info(
        "Tracking tip: use UTM links in bio, e.g. "
        "`...?utm_source=tiktok&utm_medium=social&utm_campaign=organic`"
    )


# =========================
# Tab 4: How it works
# =========================
if cfg.get("show_how_it_works_tab", True):
    with tab_objs[3]:
        st.markdown("## ℹ️ How it works")
        st.markdown(
            """
### What this app does
- Drafts copy/paste listings for **eBay**, **Facebook Marketplace**, **Mercari**, and **OfferUp**
- Calculates profit after:
  - platform fee %
  - processing fee %
  - shipping + packaging

### v1.3 update
- Cleaner UX: compact mode + output cards + copy buttons
- Title optimizer (variants + 80-char helper)
- Platform switch outputs
- Condition templates + photo checklist
- Android/iOS readability fixes + solid sidebar/control panel

### Privacy
- No login required
- Waitlist is optional
- Tracking is anonymous counters + events (no personal identity stored)
            """.strip()
        )
