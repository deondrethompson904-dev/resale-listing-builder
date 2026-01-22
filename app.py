import os
import re
import csv
import io
import base64
from dataclasses import dataclass
from typing import Optional, Tuple

import streamlit as st


# -----------------------------
# Utilities
# -----------------------------
def _clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


def _to_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _safe_strip(s: Optional[str]) -> str:
    return (s or "").strip()


def _looks_like_html(s: str) -> bool:
    # If user pastes <div> or <img> etc
    return "<" in s and ">" in s


def _extract_img_src_from_html(html: str) -> Optional[str]:
    # Extract src="..." from an img tag or any src attribute
    m = re.search(r'src\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _is_valid_image_ref(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if s.startswith("data:image/"):
        return True
    if s.startswith("http://") or s.startswith("https://"):
        return True
    return False


def _read_file_bytes(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None


def _guess_mime_from_filename(name: str) -> str:
    name = name.lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".jpg") or name.endswith(".jpeg"):
        return "image/jpeg"
    if name.endswith(".svg"):
        return "image/svg+xml"
    return "application/octet-stream"


def _to_data_uri(file_bytes: bytes, mime: str) -> str:
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def normalize_logo_input(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (logo_ref, warning_message)
    logo_ref can be:
      - https://... (image url)
      - data:image/... (data uri)
    """
    raw = _safe_strip(raw)
    if not raw:
        return None, None

    # If HTML pasted, try to extract src
    if _looks_like_html(raw):
        extracted = _extract_img_src_from_html(raw)
        if extracted and _is_valid_image_ref(extracted):
            return extracted, "Detected HTML pasted into Logo field. Extracted the image src automatically ✅"
        return None, "Logo field contained HTML but no valid image src was found. Ignored it to keep the header working."

    # If normal URL/data
    if _is_valid_image_ref(raw):
        return raw, None

    # Otherwise reject
    return None, "Logo URL must be a real image URL (https://...) or a data:image/... value. Ignored invalid input."


def load_default_repo_logo() -> Optional[str]:
    """
    Tries to load a logo file from repo (logo.png or logo.svg) into a data-uri
    so it always renders on Streamlit Cloud without relying on local paths.
    """
    candidates = [
        "assets/logo.png",
        "assets/logo.jpg",
        "assets/logo.jpeg",
        "assets/logo.svg",
        "logo.png",
        "logo.jpg",
        "logo.jpeg",
        "logo.svg",
    ]
    for p in candidates:
        b = _read_file_bytes(p)
        if b:
            mime = _guess_mime_from_filename(p)
            return _to_data_uri(b, mime)
    return None


# -----------------------------
# Data + Defaults
# -----------------------------
@dataclass
class OwnerDefaults:
    ebay_fee_pct: float = 13.25
    processing_pct: float = 2.90
    processing_fixed: float = 0.30
    packaging_cost: float = 1.50
    allow_user_edit_fees: bool = True


def init_state():
    st.session_state.setdefault("app_name", "Resale Listing Builder")
    st.session_state.setdefault("tagline", "List faster. Price smarter. Profit confidently.")
    st.session_state.setdefault("accent", "#7c3aed")

    st.session_state.setdefault("logo_url_raw", "")
    st.session_state.setdefault("logo_data_uri_upload", None)  # from uploaded file
    st.session_state.setdefault("repo_logo_data_uri", load_default_repo_logo())

    st.session_state.setdefault("your_name", "Deondre")
    st.session_state.setdefault("seller_city", "Jacksonville, FL")
    st.session_state.setdefault("pickup_line", "Porch pickup / meetup")
    st.session_state.setdefault("shipping_line", "Ships within the US")
    st.session_state.setdefault("handling_time", "Same or next business day")
    st.session_state.setdefault("returns_line", "No returns (ask questions before buying)")
    st.session_state.setdefault("auto_parts_repair_text", True)

    st.session_state.setdefault("owner_defaults", OwnerDefaults())

    st.session_state.setdefault("waitlist_emails", [])  # session-only for v1


def get_admin_pin() -> Optional[str]:
    # Streamlit Community Cloud supports env vars; also allow st.secrets if you choose
    pin = os.getenv("ADMIN_PIN")
    if not pin:
        try:
            pin = st.secrets.get("ADMIN_PIN", None)  # type: ignore
        except Exception:
            pin = None
    return pin


def is_owner_mode() -> bool:
    pin = get_admin_pin()
    # If no pin set, allow settings (dev mode)
    if not pin:
        return True

    # If pin set, require correct entry
    ok = st.session_state.get("owner_ok", False)
    return bool(ok)


def owner_gate_ui():
    pin = get_admin_pin()
    if not pin:
        st.sidebar.caption("🔓 Owner Mode is ON (no ADMIN_PIN set).")
        return

    st.sidebar.markdown("### 🔒 Owner Mode")
    st.sidebar.caption("Enter your ADMIN PIN to unlock Settings.")
    entered = st.sidebar.text_input("Admin PIN", type="password", key="pin_input")
    if st.sidebar.button("Unlock"):
        if entered == pin:
            st.session_state["owner_ok"] = True
            st.sidebar.success("Owner Mode unlocked ✅")
        else:
            st.session_state["owner_ok"] = False
            st.sidebar.error("Wrong PIN")


def resolve_logo_ref() -> Tuple[Optional[str], Optional[str]]:
    """
    Priority:
      1) Uploaded logo (data uri)
      2) LOGO_URL env var (if valid)
      3) Logo URL field (sanitized / extracted)
      4) Repo logo file (data uri)
      5) None
    Returns (logo_ref, warning)
    """
    # 1) uploaded
    if st.session_state.get("logo_data_uri_upload"):
        return st.session_state["logo_data_uri_upload"], None

    # 2) env LOGO_URL
    env_logo = _safe_strip(os.getenv("LOGO_URL", ""))
    if env_logo:
        logo_ref, warn = normalize_logo_input(env_logo)
        if logo_ref:
            return logo_ref, None

    # 3) Logo URL field
    raw = st.session_state.get("logo_url_raw", "")
    logo_ref, warn = normalize_logo_input(raw)
    if logo_ref:
        return logo_ref, warn

    # 4) repo logo
    repo_logo = st.session_state.get("repo_logo_data_uri")
    if repo_logo:
        return repo_logo, warn

    return None, warn


# -----------------------------
# UI: Theme + Header
# -----------------------------
def apply_style(accent_hex: str):
    accent_hex = accent_hex or "#7c3aed"
    st.markdown(
        f"""
        <style>
          .block-container {{
            padding-top: 2rem;
            padding-bottom: 2rem;
          }}
          .app-header {{
            display:flex;
            align-items:center;
            gap: 14px;
            padding: 12px 14px;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
            background: rgba(255,255,255,0.03);
          }}
          .app-title {{
            font-size: 1.35rem;
            font-weight: 800;
            line-height: 1.1;
            margin: 0;
          }}
          .app-tagline {{
            color: rgba(255,255,255,0.70);
            margin: 0;
            font-size: 0.95rem;
          }}
          .pill {{
            display:inline-flex;
            align-items:center;
            gap:8px;
            border:1px solid rgba(255,255,255,0.10);
            border-radius:999px;
            padding:6px 10px;
            background: rgba(255,255,255,0.03);
            font-size:0.9rem;
          }}
          .accent {{
            color: {accent_hex};
          }}
          .hr {{
            border: none;
            border-top: 1px solid rgba(255,255,255,0.08);
            margin: 16px 0 10px 0;
          }}
          .muted {{
            color: rgba(255,255,255,0.70);
          }}
          /* make primary buttons pop slightly */
          div.stButton > button[kind="primary"] {{
            border: 1px solid rgba(255,255,255,0.18);
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header():
    logo_ref, warn = resolve_logo_ref()
    app_name = st.session_state.get("app_name", "Resale Listing Builder")
    tagline = st.session_state.get("tagline", "List faster. Price smarter. Profit confidently.")

    if warn:
        # only show warning in owner mode (so customers don't see dev stuff)
        if is_owner_mode():
            st.info(warn)

    # Header layout
    cols = st.columns([0.18, 0.82])
    with cols[0]:
        if logo_ref:
            # st.image supports URL + data-uri
            st.image(logo_ref, width=72)
        else:
            st.markdown(
                f"""
                <div class="pill">
                  <span style="font-weight:800" class="accent">R</span>
                  <span class="muted">Resale</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    with cols[1]:
        st.markdown(
            f"""
            <div class="app-header">
              <div>
                <p class="app-title">{app_name}</p>
                <p class="app-tagline">{tagline}</p>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown('<hr class="hr" />', unsafe_allow_html=True)


# -----------------------------
# Business Logic
# -----------------------------
def estimate_shipping_cost(weight_lb: float, method: str) -> float:
    """
    Offline-friendly rough estimates.
    These are *estimates*, not carrier quotes.
    """
    w = max(0.0, weight_lb)
    method = (method or "").lower()

    # Flat-ish baseline + per-lb scaling
    if "local" in method or "pickup" in method:
        return 0.0
    if "priority" in method:
        return 7.50 + 1.25 * w
    if "ground" in method:
        return 6.00 + 0.95 * w
    if "first" in method:
        return 4.50 + 0.60 * w
    return 6.00 + 0.95 * w


def compute_profit(
    sale_price: float,
    cogs: float,
    ebay_fee_pct: float,
    processing_pct: float,
    processing_fixed: float,
    shipping_cost: float,
    packaging_cost: float,
) -> dict:
    sale = max(0.0, sale_price)
    cogs = max(0.0, cogs)

    ebay_fee = sale * (max(0.0, ebay_fee_pct) / 100.0)
    processing_fee = sale * (max(0.0, processing_pct) / 100.0) + max(0.0, processing_fixed)

    total_costs = cogs + ebay_fee + processing_fee + max(0.0, shipping_cost) + max(0.0, packaging_cost)
    profit = sale - total_costs
    margin = (profit / sale * 100.0) if sale > 0 else 0.0

    # breakeven sale price approximate:
    # sale - sale*(fee%+proc%) - fixed - othercosts = 0
    pct_total = (max(0.0, ebay_fee_pct) + max(0.0, processing_pct)) / 100.0
    fixed = max(0.0, processing_fixed) + max(0.0, shipping_cost) + max(0.0, packaging_cost) + cogs
    breakeven = fixed / max(1e-9, (1.0 - pct_total))

    return {
        "ebay_fee": ebay_fee,
        "processing_fee": processing_fee,
        "total_costs": total_costs,
        "profit": profit,
        "margin": margin,
        "breakeven": breakeven,
    }


def build_listing_text(
    brand: str,
    item: str,
    model: str,
    condition: str,
    category: str,
    qty: int,
    features_lines: str,
    notes_lines: str,
    includes_lines: str,
) -> dict:
    brand = _safe_strip(brand)
    item = _safe_strip(item)
    model = _safe_strip(model)
    condition = _safe_strip(condition)
    category = _safe_strip(category)

    qty = int(max(1, qty))

    # Seller profile
    your_name = _safe_strip(st.session_state.get("your_name"))
    seller_city = _safe_strip(st.session_state.get("seller_city"))
    pickup_line = _safe_strip(st.session_state.get("pickup_line"))
    shipping_line = _safe_strip(st.session_state.get("shipping_line"))
    handling_time = _safe_strip(st.session_state.get("handling_time"))
    returns_line = _safe_strip(st.session_state.get("returns_line"))
    auto_parts = bool(st.session_state.get("auto_parts_repair_text", True))

    features = [x.strip() for x in (features_lines or "").splitlines() if x.strip()]
    notes = [x.strip() for x in (notes_lines or "").splitlines() if x.strip()]
    includes = [x.strip() for x in (includes_lines or "").splitlines() if x.strip()]

    # Title logic
    title_parts = []
    if brand:
        title_parts.append(brand)
    if item:
        title_parts.append(item)
    if model:
        title_parts.append(model)
    if condition:
        title_parts.append(condition)

    title = " ".join(title_parts).strip()
    if not title:
        title = "Listing"

    # Description blocks
    bullets = ""
    if features:
        bullets += "\n".join([f"- {f}" for f in features])
    else:
        bullets += "- Clean condition\n- Ready to go"

    notes_block = ""
    if notes:
        notes_block = "\n".join([f"- {n}" for n in notes])

    includes_block = ""
    if includes:
        includes_block = "\n".join([f"- {i}" for i in includes])

    line_1 = f"**Item:** {brand} {item}".strip()
    line_2 = f"**Model/Part:** {model}" if model else ""
    line_3 = f"**Condition:** {condition}" if condition else ""
    line_4 = f"**Category:** {category}" if category else ""
    line_5 = f"**Quantity:** {qty}"

    seller_lines = []
    if seller_city:
        seller_lines.append(f"📍 {seller_city}")
    if pickup_line:
        seller_lines.append(f"🤝 {pickup_line}")
    if shipping_line:
        seller_lines.append(f"📦 {shipping_line}")
    if handling_time:
        seller_lines.append(f"⏱️ Handling: {handling_time}")
    if returns_line:
        seller_lines.append(f"↩️ Returns: {returns_line}")

    parts_repair = ""
    if auto_parts:
        parts_repair = (
            "\n\n**For parts/repair note:**\n"
            "- Sold as-is. Please review photos and ask questions before purchase.\n"
            "- No guarantees on compatibility or performance unless stated.\n"
        )

    # FB marketplace: simple, readable
    fb = f"""{title}

{line_1}
{line_2}
{line_3}
{line_4}
{line_5}

✅ Key details:
{bullets}
"""
    if includes_block:
        fb += f"\n📦 Included:\n{includes_block}\n"
    if notes_block:
        fb += f"\n📝 Notes:\n{notes_block}\n"

    if seller_lines:
        fb += "\n" + "\n".join(seller_lines)

    fb += parts_repair

    # eBay: slightly more structured
    ebay = f"""{title}

DETAILS
- Brand/Item: {brand} {item}
{"- Model/Part: " + model if model else ""}
{"- Condition: " + condition if condition else ""}
{"- Category: " + category if category else ""}
- Quantity: {qty}

KEY FEATURES
{bullets}
"""
    if includes_block:
        ebay += f"\nINCLUDED\n{includes_block}\n"
    if notes_block:
        ebay += f"\nNOTES\n{notes_block}\n"

    if seller_lines:
        ebay += "\nSHIPPING / PICKUP\n" + "\n".join(seller_lines)

    ebay += parts_repair

    if your_name:
        ebay += f"\n— {your_name}"

    return {"title": title, "fb": fb.strip(), "ebay": ebay.strip()}


# -----------------------------
# Pages
# -----------------------------
def page_listing_builder():
    st.subheader("🧾 Listing Builder")
    st.caption("Draft clean, copy/paste listings for eBay + Facebook Marketplace.")

    col1, col2, col3 = st.columns([1.15, 1.05, 1.10])

    with col1:
        st.markdown("#### 1) Item info")
        brand = st.text_input("Brand", placeholder="Apple, DeWalt, Nike, etc.", key="brand")
        item = st.text_input("Item", placeholder="MacBook Pro, Drill, Sneakers, etc.", key="item")
        model = st.text_input("Model / Part # (optional)", placeholder="A1990, DCD791, etc.", key="model")
        condition = st.selectbox(
            "Condition",
            ["New", "Open box", "Used - Like New", "Used - Good", "Used - Fair", "For parts/repair"],
            index=3,
            key="condition",
        )
        category = st.text_input("Category (optional)", placeholder="Electronics, Tools, Home, etc.", key="category")
        qty = st.number_input("Quantity", min_value=1, max_value=999, value=1, step=1, key="qty")

        st.markdown("#### 2) Features & notes")
        features = st.text_area("Key features (one per line)", height=120, key="features", placeholder="Example:\n16GB RAM\n512GB SSD\nIncludes charger")
        includes = st.text_area("What’s included (optional)", height=80, key="includes", placeholder="Example:\nCharger\nBox\nManual")
        notes = st.text_area("Flaws / notes (optional)", height=90, key="notes", placeholder="Example:\nMinor scuffs\nBattery holds charge")

    owner_defaults: OwnerDefaults = st.session_state["owner_defaults"]

    with col2:
        st.markdown("#### 3) Money math")
        cogs = st.number_input("Your cost (COGS) $", min_value=0.0, value=10.00, step=0.50, key="cogs")
        sale_price = st.number_input("Target sale price $", min_value=0.0, value=49.99, step=1.00, key="sale_price")
        weight = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25, key="weight")

        ship_method = st.selectbox(
            "Shipping method",
            ["Ground (est.)", "Priority (est.)", "First Class (est.)", "Local pickup"],
            index=0,
            key="ship_method",
        )
        shipping_cost = estimate_shipping_cost(weight, ship_method)

        packaging_cost = st.number_input(
            "Packaging cost ($)",
            min_value=0.0,
            value=float(owner_defaults.packaging_cost),
            step=0.25,
            key="pack_cost",
            disabled=not owner_defaults.allow_user_edit_fees and not is_owner_mode(),
        )

        # Fees section (lock for customers if owner chooses)
        st.markdown("##### Fees")
        fee_disabled = (not owner_defaults.allow_user_edit_fees) and (not is_owner_mode())

        ebay_fee_pct = st.number_input(
            "eBay fee %",
            min_value=0.0,
            max_value=40.0,
            value=float(owner_defaults.ebay_fee_pct),
            step=0.10,
            key="ebay_fee_pct",
            disabled=fee_disabled,
        )
        processing_pct = st.number_input(
            "Processing %",
            min_value=0.0,
            max_value=15.0,
            value=float(owner_defaults.processing_pct),
            step=0.10,
            key="processing_pct",
            disabled=fee_disabled,
        )
        processing_fixed = st.number_input(
            "Processing fixed ($)",
            min_value=0.0,
            max_value=5.0,
            value=float(owner_defaults.processing_fixed),
            step=0.05,
            key="processing_fixed",
            disabled=fee_disabled,
        )

        result = compute_profit(
            sale_price=sale_price,
            cogs=cogs,
            ebay_fee_pct=ebay_fee_pct,
            processing_pct=processing_pct,
            processing_fixed=processing_fixed,
            shipping_cost=shipping_cost,
            packaging_cost=packaging_cost,
        )

        st.markdown("##### Results")
        r1, r2, r3 = st.columns(3)
        r1.metric("Profit", f"${result['profit']:.2f}")
        r2.metric("Margin", f"{result['margin']:.1f}%")
        r3.metric("Breakeven", f"${result['breakeven']:.2f}")

        st.caption(
            f"Shipping estimate ({ship_method}): **${shipping_cost:.2f}**  •  Total costs: **${result['total_costs']:.2f}**"
        )

        # Quick tiers
        st.markdown("#### Quick pricing tiers")
        tiers = [
            ("Fast sale", max(result["breakeven"] + 5, sale_price * 0.85)),
            ("Market", max(result["breakeven"] + 10, sale_price)),
            ("Max profit", max(result["breakeven"] + 20, sale_price * 1.15)),
        ]
        for name, price in tiers:
            st.write(f"- **{name}:** ${price:.2f}")

    with col3:
        st.markdown("#### Output")
        listing = build_listing_text(
            brand=brand,
            item=item,
            model=model,
            condition=condition,
            category=category,
            qty=int(qty),
            features_lines=features,
            notes_lines=notes,
            includes_lines=includes,
        )

        st.markdown("##### Title")
        st.code(listing["title"], language=None)

        st.markdown("##### Facebook Marketplace description")
        st.code(listing["fb"], language=None)

        st.markdown("##### eBay description")
        st.code(listing["ebay"], language=None)

        st.markdown("—")
        st.caption("Tip: Paste the title + description into your listing, then attach photos. Always disclose flaws.")


def page_flip_checker():
    st.subheader("✅ Flip Checker")
    st.caption("A quick “should I buy this?” calculator for resellers.")

    owner_defaults: OwnerDefaults = st.session_state["owner_defaults"]
    fee_disabled = (not owner_defaults.allow_user_edit_fees) and (not is_owner_mode())

    c1, c2 = st.columns([1.05, 0.95])
    with c1:
        buy = st.number_input("Buy price ($)", min_value=0.0, value=20.0, step=1.0)
        expected_sale = st.number_input("Expected sale price ($)", min_value=0.0, value=75.0, step=1.0)
        weight = st.number_input("Estimated weight (lb)", min_value=0.0, value=2.0, step=0.25)
        ship_method = st.selectbox(
            "Shipping method",
            ["Ground (est.)", "Priority (est.)", "First Class (est.)", "Local pickup"],
            index=0,
        )
        shipping_cost = estimate_shipping_cost(weight, ship_method)
        packaging_cost = st.number_input(
            "Packaging cost ($)",
            min_value=0.0,
            value=float(owner_defaults.packaging_cost),
            step=0.25,
            disabled=fee_disabled,
        )

    with c2:
        st.markdown("##### Fees")
        ebay_fee_pct = st.number_input(
            "eBay fee %",
            min_value=0.0,
            max_value=40.0,
            value=float(owner_defaults.ebay_fee_pct),
            step=0.10,
            disabled=fee_disabled,
        )
        processing_pct = st.number_input(
            "Processing %",
            min_value=0.0,
            max_value=15.0,
            value=float(owner_defaults.processing_pct),
            step=0.10,
            disabled=fee_disabled,
        )
        processing_fixed = st.number_input(
            "Processing fixed ($)",
            min_value=0.0,
            max_value=5.0,
            value=float(owner_defaults.processing_fixed),
            step=0.05,
            disabled=fee_disabled,
        )

        min_profit = st.number_input("Minimum profit goal ($)", min_value=0.0, value=15.0, step=1.0)

        res = compute_profit(
            sale_price=expected_sale,
            cogs=buy,
            ebay_fee_pct=ebay_fee_pct,
            processing_pct=processing_pct,
            processing_fixed=processing_fixed,
            shipping_cost=shipping_cost,
            packaging_cost=packaging_cost,
        )

        st.markdown("##### Decision")
        good = res["profit"] >= min_profit
        if good:
            st.success(f"✅ Looks good — estimated profit **${res['profit']:.2f}**")
        else:
            st.warning(f"⚠️ Tight — estimated profit **${res['profit']:.2f}** (goal: ${min_profit:.2f})")

        st.metric("Profit", f"${res['profit']:.2f}")
        st.metric("Margin", f"{res['margin']:.1f}%")
        st.caption(f"Shipping est: **${shipping_cost:.2f}** • Breakeven: **${res['breakeven']:.2f}**")


def page_coming_soon():
    st.subheader("🚀 Coming Soon")
    st.caption("This is where we funnel customers + collect a waitlist for new features.")

    st.markdown(
        """
### What’s next
- **Saved profiles** (multiple seller profiles + presets)
- **Photo checklist** per category (electronics/tools/sneakers)
- **Bulk listing builder** (paste multiple items + generate outputs)
- **Pricing suggestions** based on “profit goal” + “time to sell”
- **Export to CSV / Notion** for inventory tracking
- **Buyer message templates** (FB Marketplace quick replies)
"""
    )

    st.markdown("### Join the waitlist")
    with st.form("waitlist"):
        email = st.text_input("Email (optional)", placeholder="you@example.com")
        note = st.text_input("What should we build next?", placeholder="Example: bulk listing, inventory tracker, etc.")
        submitted = st.form_submit_button("Join waitlist", type="primary")
        if submitted:
            email_s = _safe_strip(email)
            note_s = _safe_strip(note)
            if email_s or note_s:
                st.session_state["waitlist_emails"].append((email_s, note_s))
                st.success("Added ✅ (saved for this session)")
            else:
                st.warning("Type an email or a note first.")

    if st.session_state["waitlist_emails"]:
        st.markdown("### Export waitlist (CSV)")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["email", "note"])
        for e, n in st.session_state["waitlist_emails"]:
            writer.writerow([e, n])

        st.download_button(
            "Download CSV",
            data=output.getvalue().encode("utf-8"),
            file_name="waitlist.csv",
            mime="text/csv",
        )

    st.markdown("### Launch CTA (copy/paste)")
    app_url = st.secrets.get("APP_URL", "") if hasattr(st, "secrets") else ""  # optional
    st.code(
        "Free resale profit calculator (eBay + FB Marketplace)\n"
        "Check flips before you buy 👇\n"
        f"{app_url or '(paste your streamlit app link here)'}",
        language=None,
    )


def page_how_it_works():
    st.subheader("ℹ️ How it works")
    st.markdown(
        """
### What this app does
- Helps you draft **clean, copy/paste listings** for **eBay** and **Facebook Marketplace**
- Estimates your **profit** after:
  - eBay fee %
  - processing %
  - processing fixed fee
  - shipping estimate (based on weight + method)
  - packaging cost

### How to use it (fast)
1) Fill out **Item info** + **Features**
2) Set your **cost** + **target sale price**
3) Copy the output into your listing
4) Upload clear photos and disclose flaws

### Pro tips
- Use “For parts/repair” when unsure — protects you
- Always include handling time + returns line
- Try “Fast sale / Market / Max profit” tiers to price quickly
"""
    )


# -----------------------------
# Owner Settings
# -----------------------------
def owner_settings_sidebar():
    st.sidebar.markdown("## ⚙️ Settings")

    with st.sidebar.expander("Branding", expanded=True):
        st.text_input("App name", key="app_name")
        st.text_input("Tagline", key="tagline")
        st.color_picker("Accent color", key="accent")

        st.caption("Logo options: set LOGO_URL env var, paste a direct image URL, or upload an image.")
        st.text_input("Logo URL (optional)", key="logo_url_raw", placeholder="https://... or data:image/...")

        upload = st.file_uploader("Upload logo (png/jpg/svg)", type=["png", "jpg", "jpeg", "svg"])
        if upload is not None:
            b = upload.read()
            mime = upload.type or _guess_mime_from_filename(upload.name)
            st.session_state["logo_data_uri_upload"] = _to_data_uri(b, mime)
            st.success("Logo uploaded ✅")

        if st.button("Clear uploaded logo"):
            st.session_state["logo_data_uri_upload"] = None
            st.success("Cleared ✅")

    with st.sidebar.expander("Personalization", expanded=False):
        st.text_input("Your name (optional)", key="your_name")
        st.text_input("City/Area", key="seller_city")
        st.text_input("Pickup line", key="pickup_line")
        st.text_input("Shipping line", key="shipping_line")
        st.text_input("Handling time", key="handling_time")
        st.text_input("Returns policy line", key="returns_line")
        st.toggle("Auto add 'For parts/repair' protection text", key="auto_parts_repair_text")

    with st.sidebar.expander("Owner Defaults (fees)", expanded=False):
        od: OwnerDefaults = st.session_state["owner_defaults"]

        od.ebay_fee_pct = st.number_input("Default eBay fee %", min_value=0.0, max_value=40.0, value=float(od.ebay_fee_pct), step=0.10)
        od.processing_pct = st.number_input("Default processing %", min_value=0.0, max_value=15.0, value=float(od.processing_pct), step=0.10)
        od.processing_fixed = st.number_input("Default processing fixed ($)", min_value=0.0, max_value=5.0, value=float(od.processing_fixed), step=0.05)
        od.packaging_cost = st.number_input("Default packaging cost ($)", min_value=0.0, max_value=10.0, value=float(od.packaging_cost), step=0.25)
        od.allow_user_edit_fees = st.toggle("Allow customers to edit fees", value=bool(od.allow_user_edit_fees))

        st.session_state["owner_defaults"] = od
        st.caption("If you turn off customer editing, the fee fields become locked for customers.")


# -----------------------------
# Main
# -----------------------------
def main():
    st.set_page_config(
        page_title="Resale Listing Builder",
        page_icon="🧾",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_state()

    apply_style(st.session_state.get("accent", "#7c3aed"))

    # Owner gate always shown (if pin exists)
    owner_gate_ui()

    # Owner-only settings sidebar
    if is_owner_mode():
        owner_settings_sidebar()
    else:
        st.sidebar.markdown("### 🔒 Settings locked")
        st.sidebar.caption("Owner Mode only. Listings + calculators are still available.")

    # Header always visible
    render_header()

    # App tabs
    tab_labels = ["🧾 Listing Builder", "✅ Flip Checker", "🚀 Coming Soon", "ℹ️ How it works"]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        page_listing_builder()
    with tabs[1]:
        page_flip_checker()
    with tabs[2]:
        page_coming_soon()
    with tabs[3]:
        page_how_it_works()

    # Footer
    st.markdown('<hr class="hr" />', unsafe_allow_html=True)
    st.caption("Offline-friendly v1 • No account required • Built for fast reselling workflows.")


if __name__ == "__main__":
    main()
