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

APP_VERSION = "v1.3"


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
    return (
        (ctx.get("src") == "tiktok")
        or (ctx.get("utm_source") == "tiktok")
        or (ctx.get("traffic_source") == "tiktok")
    )


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
# Helpers: logo (CLEAN HEADER SUPPORT)
# =========================
def read_file_bytes(path: pathlib.Path) -> Optional[bytes]:
    try:
        if path.exists():
            return path.read_bytes()
    except Exception:
        return None
    return None


def get_logo_source() -> Tuple[Optional[str], Optional[bytes], Optional[str]]:
    """
    Priority:
      1) LOGO_URL env var (remote URL)
      2) data/logo_override.png
      3) assets/logo.png
      4) assets/logo.svg
      5) None (fallback badge)
    Returns: (logo_url, logo_bytes, mime)
    """
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


def copy_btn(label: str, text: str, key: str) -> None:
    if st.button(label, key=key, use_container_width=True):
        components.html(_clipboard_js(text), height=0)
        toast("Copied ✅")


def card(title: str, body_fn) -> None:
    st.markdown(f'<div class="tf-card"><div class="tf-card-title">{title}</div>', unsafe_allow_html=True)
    body_fn()
    st.markdown("</div>", unsafe_allow_html=True)


# =========================
# Styling (dark theme + readable + solid sidebar)
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
            --border: rgba(255,255,255,0.14);
            --border2: rgba(255,255,255,0.20);
            --text: #F3F4F6;
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

          /* Sidebar solid */
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
          .tf-header-title {{
            min-width: 0;
          }}
          .tf-header-title .name {{
            font-weight: 900;
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
          .tf-chip {{
            display:inline-flex;
            align-items:center;
            gap: 6px;
            padding: 6px 10px;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.14);
            background: rgba(255,255,255,0.05);
            color: var(--muted) !important;
            font-size: 0.85rem;
            white-space: nowrap;
          }}
          @media (max-width: 640px) {{
            .tf-header-right {{
              display: none;
            }}
            .tf-header-logo {{
              width: 46px;
              height: 46px;
              border-radius: 12px;
            }}
            .tf-header-title .name {{
              font-size: 1.12rem;
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
        else f"<div style='font-weight:900;color:var(--text);'>{initials}</div>"
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
            <span class="tf-chip">Offline-friendly</span>
            <span class="tf-chip">No login</span>
            <span class="tf-chip">{APP_VERSION}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

# =========================
# Core logic: profit + score
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


def flip_score(profit: float, margin_pct:

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
        log_event(
            "profit_checked",
            {"sale_price": sale_price, "cogs": cogs, "shipping_method": shipping_method, "preset": preset},
        )

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
        note_cs = st.text_input(
            "What feature do you want most? (optional)",
            key="note_comingsoon",
            placeholder="Saved checks, bulk mode, exports…",
        )
    with coly:
        if st.button("Join waitlist", key="join_waitlist_cs", use_container_width=True):
            ok, msg = append_waitlist(
                email_cs,
                source=st.session_state.get("traffic_source", "unknown"),
                note=note_cs,
            )
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
