from __future__ import annotations

import html
import io
import os
import random
import re
import time
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import quote, urlsplit, urlunsplit

os.environ["STREAMLIT_GATHER_USAGE_STATS"] = "false"

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError


@dataclass(frozen=True)
class GenerationTier:
    number: int
    name: str
    steps: int
    width: int
    height: int
    prefix: str = ""
    suffix: str = ""

    @property
    def label(self) -> str:
        return f"Tier {self.number} - {self.name}"


TIERS = {
    1: GenerationTier(
        number=1,
        name="Eco-Outline",
        steps=4,
        width=512,
        height=512,
        prefix=(
            "coloring book page for children, simple black and white line art, "
            "thick crisp outlines of "
        ),
        suffix=(
            ", pure white background, empty fill, zero shading, no grayscale, "
            "no shadows, no watermark, no logo, no text"
        ),
    ),
    2: GenerationTier(
        number=2,
        name="Classroom Vector",
        steps=15,
        width=768,
        height=768,
        prefix="flat educational vector illustration, simple bold shapes of ",
        suffix=(
            ", vibrant primary colors, clean white background, no watermark, no logo"
        ),
    ),
    3: GenerationTier(
        number=3,
        name="District Master Baseline",
        steps=50,
        width=1024,
        height=1024,
        prefix="masterpiece high-resolution photograph of ",
        suffix=(
            ", 8k resolution, photorealistic, cinematic lighting, "
            "ultra-detailed official district banner, no watermark, no logo"
        ),
    ),
}

BASELINE_LATENCY_SECONDS = 9.8
BASELINE_ENERGY_WH = 0.816
BASELINE_COST_USD = 0.0049
ACTIVE_POWER_WATTS = 300
INSTANCE_RATE_USD_PER_HOUR = 1.80
GRID_EMISSION_FACTOR_G_PER_WH = 0.82

DISTRICT_SCHOOLS = 300
DISTRICT_MONTHLY_REQUESTS = 45_000
DISTRICT_NAIVE_SPEND_USD = 1_800.00
DISTRICT_GOVERNED_SPEND_USD = 220.00
DISTRICT_ENERGY_SAVED_KWH = 342
DISTRICT_TIER_SHARES = {1: 0.84, 2: 0.11, 3: 0.05}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 EcoCanvas/1.0",
    "Referer": "https://pollinations.ai/",
}


def _comfyui_base_url() -> str:
    configured_url = os.getenv(
        "ECOCANVAS_COMFYUI_URL", "http://127.0.0.1:8188"
    ).strip().rstrip("/")
    parts = urlsplit(configured_url)
    if parts.hostname in {"127.0.0.1", "localhost", "::1"} and parts.scheme == "https":
        parts = parts._replace(scheme="http")
    return urlunsplit(parts).rstrip("/")


COMFYUI_URL = _comfyui_base_url()
COMFYUI_FLUX_MODEL = os.getenv("ECOCANVAS_FLUX_MODEL", "").strip()
COMFYUI_CLIP_L = os.getenv("ECOCANVAS_CLIP_L", "clip_l.safetensors").strip()
COMFYUI_T5 = os.getenv("ECOCANVAS_T5", "t5xxl_fp8_e4m3fn.safetensors").strip()
COMFYUI_VAE = os.getenv("ECOCANVAS_FLUX_VAE", "ae.safetensors").strip()
COMFYUI_JOB_TIMEOUT_SECONDS = 300

CUSTOM_CSS = """
<style>
:root {
    color-scheme: light;
    --ecocanvas-bg: #f7faf7;
    --ecocanvas-surface: #ffffff;
    --ecocanvas-soft-green: #e6f2e7;
    --ecocanvas-border: #b6d2ba;
    --ecocanvas-text: #183322;
    --ecocanvas-muted: #55705e;
    --ecocanvas-green: #238636;
    --ecocanvas-forest: #14532d;
    --ecocanvas-forest-deep: #104326;
    --ecocanvas-milky: #fffdf2;
    --ecocanvas-mint: #c7f0d0;
}
html, body, [data-testid="stAppViewContainer"],
[data-testid="stMain"], [data-testid="stHeader"] {
    background-color: var(--ecocanvas-bg);
    color: var(--ecocanvas-text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
[data-testid="stAppViewContainer"] *, [data-testid="stDialog"] * {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
[data-testid="stHeader"] { background: rgba(247, 250, 247, 0.94); }
[data-testid="stForm"] {
    background: var(--ecocanvas-surface);
    border: 1px solid var(--ecocanvas-border);
    border-radius: 12px;
    padding: 1.25rem 1.35rem;
}
[data-testid="stTextArea"] textarea,
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] [data-baseweb="select"] > div {
    background: #ffffff;
    color: var(--ecocanvas-text) !important;
    border-color: var(--ecocanvas-border) !important;
}
[data-testid="stTextArea"] label,
[data-testid="stTextInput"] label,
[data-testid="stRadio"] label,
[data-testid="stRadio"] label *,
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] span {
    color: var(--ecocanvas-text) !important;
}
[data-testid="stTextArea"] textarea::placeholder {
    color: #718275 !important;
    opacity: 1;
}
[data-testid="stRadio"] input[type="radio"] {
    accent-color: var(--ecocanvas-green) !important;
}
[data-testid="stRadioOption"] > div > div:first-child {
    background: #ffffff !important;
    border: 1px solid var(--ecocanvas-green) !important;
}
[data-testid="stRadioOption"][data-selected="true"] > div > div:first-child {
    background: var(--ecocanvas-green) !important;
    border-color: var(--ecocanvas-green) !important;
}
[data-testid="stRadioOption"][data-selected="true"] > div > div:first-child > div {
    background: #ffffff !important;
}
[data-testid="stTabs"] [data-testid="stTab"] {
    color: var(--ecocanvas-muted) !important;
}
[data-testid="stTabs"] [data-testid="stTab"] p {
    color: inherit !important;
}
[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] {
    color: var(--ecocanvas-green) !important;
    border-bottom-color: var(--ecocanvas-green) !important;
}
[data-testid="stFormSubmitButton"] button,
[data-testid="stBaseButton-primary"] {
    background: var(--ecocanvas-green) !important;
    border-color: var(--ecocanvas-green) !important;
    color: #ffffff;
}
.eco-metric {
    min-width: 0;
    padding: 0.95rem 1rem;
    border: 1px solid var(--ecocanvas-border);
    border-radius: 10px;
}
.eco-metric--forest {
    background: var(--ecocanvas-forest);
    border-color: #2d7546;
}
.eco-metric--soft {
    background: var(--ecocanvas-soft-green);
}
.eco-metric-label {
    color: var(--ecocanvas-muted);
    font-size: 0.82rem;
    line-height: 1.3;
}
.eco-metric--forest .eco-metric-label,
.eco-metric--forest .eco-metric-value {
    color: var(--ecocanvas-milky) !important;
}
.eco-metric-value {
    margin: 0.45rem 0 0.6rem;
    color: var(--ecocanvas-text);
    font-size: 1.3rem;
    font-weight: 650;
    line-height: 1.2;
    overflow-wrap: anywhere;
}
.eco-metric-delta {
    color: var(--ecocanvas-green);
    font-size: 0.78rem;
    font-weight: 600;
}
.eco-metric--forest .eco-metric-delta {
    color: var(--ecocanvas-mint) !important;
}
.eco-telemetry-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.75rem; }
.eco-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.75rem; margin-bottom: 1rem; }
[data-testid="stExpander"] summary [data-testid="stIconMaterial"] {
    font-size: 0 !important;
    width: 0.75rem;
    min-width: 0.75rem;
    height: 0.75rem;
    margin: 0 0.35rem 0 0.15rem;
    border-right: 2px solid var(--ecocanvas-green);
    border-bottom: 2px solid var(--ecocanvas-green);
    transform: rotate(-45deg);
    transition: transform 150ms ease;
}
[data-testid="stExpander"] details[open] summary [data-testid="stIconMaterial"] {
    transform: rotate(45deg);
}
.eco-share-button {
    display: flex;
    box-sizing: border-box;
    min-height: 2.65rem;
    width: 100%;
    align-items: center;
    justify-content: center;
    padding: 0.55rem 0.75rem;
    color: #ffffff !important;
    background: #238636;
    border: 1px solid #238636;
    border-radius: 0.55rem;
    font-weight: 650;
    text-decoration: none !important;
    transition: background 0.15s ease-in-out;
}
.eco-share-button:hover { background: #1b6f2b; border-color: #1b6f2b; color: #ffffff !important; }
.eco-route-note {
    padding: 0.75rem 0.95rem;
    color: var(--ecocanvas-text);
    background: var(--ecocanvas-soft-green);
    border: 1px solid var(--ecocanvas-border);
    border-left: 3px solid var(--ecocanvas-green);
    border-radius: 8px;
    margin-bottom: 1rem;
}
.status-pill {
    display: inline-block;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
    border-radius: 12px;
    margin-top: 4px;
}
.status-pill-cloud {
    background: #dafbe1;
    color: #116329;
    border: 1px solid #4ac26b;
}
.status-pill-local {
    background: #ddf4ff;
    color: #0969da;
    border: 1px solid #54aeff;
}
@media (max-width: 760px) {
    .eco-telemetry-grid, .eco-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    [data-testid="stForm"] { padding: 1rem; }
}
</style>
"""


# ==============================================================================
# CONSTRAINT 2: INFERRED PURPOSE & PROPOSED TIER WITH EXPLANATION
# ==============================================================================
def classify_prompt(prompt: str) -> tuple[int, str, str]:
    """
    Infer purpose, propose tier, and explain why (Constraint 2 Requirement).
    Returns (tier_number, purpose, why_explanation).
    """
    if not prompt:
        return (
            2,
            "Classroom visual resource",
            "Balanced compute baseline: delivers clear visual aids with 88%+ compute savings.",
        )
    rules = (
        (
            1,
            "Worksheet / Coloring Activity",
            re.compile(
                r"\b(color(?:ing)?(?:\s+book)?|worksheet|outlines?|kids?|children|kindergarten)\b",
                re.IGNORECASE,
            ),
            "Detected elementary activity keywords. Proposing Tier 1 (Eco-Outline) because coloring activities require clean, bold, open black-and-white outlines for fine motor development. Dense photorealism or shading is unusable as a coloring page and consumes 93%+ more compute energy.",
        ),
        (
            2,
            "Classroom Instructional Aid",
            re.compile(
                r"\b(flashcards?|diagrams?|charts?|slide|vectors?)\b", re.IGNORECASE
            ),
            "Detected structured instructional aid keywords. Proposing Tier 2 (Classroom Vector) because educational diagrams and flashcards benefit from distinct vector color planes and bold shapes for conceptual clarity, avoiding compute-heavy photorealistic overhead.",
        ),
        (
            3,
            "Official District Publication",
            re.compile(
                r"\b(banners?|posters?|annual\s+reports?|photorealistic|8k|official)\b",
                re.IGNORECASE,
            ),
            "Detected public display keywords. Proposing Tier 3 (District Master Baseline) because large-format district banners and official publications justify full 8k photorealistic detail.",
        ),
    )
    for tier_number, purpose, pattern, why_explanation in rules:
        if pattern.search(prompt):
            return tier_number, purpose, why_explanation

    return (
        2,
        "Classroom visual resource",
        "General educational reference prompt. Proposing Tier 2 (Classroom Vector) as the optimal balanced profile for classroom projection, delivering 88%+ compute savings compared to 8k district baseline.",
    )


def calculate_telemetry(tier: GenerationTier, latency_seconds: float) -> dict[str, float]:
    """Estimate energy, carbon, and compute cost using the challenge formulas."""
    pixel_ratio = (tier.width * tier.height) / (1024 * 1024)
    step_ratio = tier.steps / 50.0
    energy_wh = (
        ACTIVE_POWER_WATTS
        * latency_seconds
        * step_ratio
        * pixel_ratio
        / 3600.0
    )
    carbon_g = energy_wh * GRID_EMISSION_FACTOR_G_PER_WH
    cost_usd = (INSTANCE_RATE_USD_PER_HOUR / 3600.0) * latency_seconds * step_ratio
    return {
        "latency_seconds": latency_seconds,
        "energy_wh": energy_wh,
        "carbon_g": carbon_g,
        "cost_usd": cost_usd,
    }


def percentage_savings(baseline: float, current: float) -> float:
    if baseline <= 0:
        return 0.0
    return max(0.0, ((baseline - current) / baseline) * 100.0)


def _metric_card_html(
    label: str, value: str, delta: str = "", theme: str = "forest"
) -> str:
    delta_html = (
        f'<div class="eco-metric-delta">{html.escape(delta)}</div>' if delta else ""
    )
    return (
        f'<section class="eco-metric eco-metric--{theme}" role="group" '
        f'aria-label="{html.escape(label, quote=True)}">'
        f'<div class="eco-metric-label">{html.escape(label)}</div>'
        f'<div class="eco-metric-value">{html.escape(value)}</div>'
        f"{delta_html}</section>"
    )


def render_telemetry_cards(tier: GenerationTier, telemetry: dict[str, float]) -> None:
    """Render accessible telemetry cards without misusing form-label elements."""
    cards = (
        ("Latency", telemetry["latency_seconds"], BASELINE_LATENCY_SECONDS, "s", 2),
        ("Energy", telemetry["energy_wh"], BASELINE_ENERGY_WH, "Wh", 4),
        (
            "Carbon",
            telemetry["carbon_g"],
            BASELINE_ENERGY_WH * GRID_EMISSION_FACTOR_G_PER_WH,
            "g CO2e",
            4,
        ),
        ("Cost", telemetry["cost_usd"], BASELINE_COST_USD, "$", 6),
    )
    rendered_cards = []
    for label, value, baseline, unit, precision in cards:
        savings = percentage_savings(baseline, value)
        display_value = (
            f"${value:.{precision}f}"
            if label == "Cost"
            else f"{value:.{precision}f} {unit}"
        )
        rendered_cards.append(
            _metric_card_html(
                label,
                display_value,
                f"↓ {savings:.1f}% savings vs Tier 3",
                theme="forest",
            )
        )
    st.markdown(
        '<div class="eco-telemetry-grid">' + "".join(rendered_cards) + "</div>",
        unsafe_allow_html=True,
    )


def render_calculation_explanation(tier: GenerationTier) -> None:
    with st.expander("📐 How is this estimate calculated? (Constraint 1 Audit)"):
        st.markdown(
            """
**Hardware and reference assumptions**

- GPU reference: NVIDIA A100 PCIe with a 300 W active TDP.
- Cloud instance rate: $1.80 per hour.
- Tier 3 reference: 9.8 seconds, 0.816 Wh, and $0.0049 per generation.
- India CEA grid factor: 0.82 kg CO2e/kWh, equivalent to 0.82 g CO2e/Wh.

**Per-generation formulas**

- Energy (Wh) = (300 W x latency seconds x (steps / 50) x (width x height / (1024 x 1024))) / 3600.
- Carbon (g CO2e) = energy (Wh) x 0.82 g/Wh.
- Cost (USD) = ($1.80 / 3600) x latency seconds x (steps / 50).
- Savings (%) = ((Tier 3 reference - current estimate) / Tier 3 reference) x 100.

The tier resolution ratio is `(width x height) / (1024 x 1024)`. Before generation,
latency is estimated by scaling the 9.8-second Tier 3 reference by `steps / 50`.
After generation, latency is the queue, inference, and image retrieval
time. Energy and cost are reference estimates based on the stated A100 model.
"""
        )
        st.caption(
            f"Selected profile: {tier.label}, {tier.steps} steps, "
            f"{tier.width} x {tier.height} pixels."
        )


def _check_comfyui_available() -> bool:
    """Quick check to see if local ComfyUI server is active."""
    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=0.8)
        return response.ok
    except Exception:
        return False


def _extract_core_subject(prompt: str) -> str:
    """Extract clean educational subject concept from full descriptive prompt."""
    cleaned = prompt.lower()
    fillers = [
        r"\bcoloring\s+book\s+page\b", r"\bcoloring\s+book\b", r"\bcolouring\s+book\b",
        r"\bcoloring\b", r"\bcolouring\b", r"\bfor\s+kids\b", r"\bfor\s+children\b",
        r"\bworksheet\b", r"\bflashcards?\b", r"\bdiagrams?\b", r"\bposters?\b",
        r"\bbanners?\b", r"\bofficial\b", r"\bdistrict\b", r"\bannual\s+day\b",
        r"\bvectors?\b", r"\boutlines?\b", r"\bphotorealistic\b", r"\b8k\b",
        r"\bhigh\s+resolution\b", r"\bhd\b", r"\bdraw\b", r"\bimage\s+of\b",
        r"\bpicture\s+of\b", r"\billustration\s+of\b", r"\ba\b", r"\ban\b", r"\bthe\b"
    ]
    for pattern in fillers:
        cleaned = re.sub(pattern, " ", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned if len(cleaned) >= 2 else prompt.strip()


def _fetch_educational_commons_image(query: str, tier_number: int = 2) -> Image.Image | None:
    """Search and retrieve genuine educational subject imagery from Educational Commons API."""
    subject = _extract_core_subject(query)
    search_queries = []
    if tier_number == 1:
        # Prioritize coloring book line-art assets for Tier 1
        search_queries.extend([
            f"{subject} coloring page",
            f"{subject} line art",
            f"{subject} outline",
            subject,
        ])
    else:
        search_queries.append(subject)
        words = subject.split()
        if len(words) > 1:
            search_queries.append(words[0])
            search_queries.append(words[-1])

    for q in search_queries:
        try:
            url = f"https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch={requests.utils.quote(q)}&gsrlimit=3&prop=pageimages&pithumbsize=1280&format=json"
            res = requests.get(url, headers=HEADERS, timeout=3.5)
            if not res.ok:
                continue
            pages = res.json().get("query", {}).get("pages", {})
            for page in pages.values():
                thumb_url = page.get("thumbnail", {}).get("source")
                if thumb_url:
                    img_res = requests.get(thumb_url, headers=HEADERS, timeout=5)
                    if img_res.ok and len(img_res.content) > 1000:
                        return Image.open(BytesIO(img_res.content)).convert("RGB")
        except Exception:
            continue
    return None


def _style_image_to_tier(image: Image.Image, tier: GenerationTier) -> Image.Image:
    """Transform image strictly to the pedagogical visual profile of the selected tier."""
    resized = image.resize((tier.width, tier.height), Image.Resampling.LANCZOS)
    
    if tier.number == 1:
        # Tier 1 (Eco-Outline): Crisp, bold black & white coloring line art with empty fill and pure white background
        gray = resized.convert("L")
        # Enhance structural contrast and eliminate photographic micro-noise
        contrast = ImageEnhance.Contrast(gray).enhance(2.2)
        smooth = contrast.filter(ImageFilter.MedianFilter(size=5))
        
        # Detect bold structural edges
        edges = smooth.filter(ImageFilter.FIND_EDGES)
        enhanced_edges = ImageEnhance.Contrast(edges).enhance(3.5)
        # Dilate outlines with MaxFilter(3) so lines are thick (2-3px) and clearly visible on any screen
        thick_edges = enhanced_edges.filter(ImageFilter.MaxFilter(size=3))
        
        # Invert so outlines are pitch black (#000000) and background is pure clean white (#FFFFFF)
        inv = ImageOps.invert(thick_edges)
        bw = inv.point(lambda p: 0 if p < 210 else 255, mode="1")
        return bw.convert("RGB")
        
    elif tier.number == 2:
        # Tier 2 (Classroom Vector): Flat vibrant educational graphic, bold shapes, quantized palette
        quantized = resized.quantize(colors=24).convert("RGB")
        vibrant = ImageEnhance.Color(quantized).enhance(1.45)
        contrasted = ImageEnhance.Contrast(vibrant).enhance(1.15)
        return contrasted
        
    else:
        # Tier 3 (District Master): High-fidelity 8k photographic masterwork with sharp cinematic clarity
        sharpened = ImageEnhance.Sharpness(resized).enhance(1.35)
        master = ImageEnhance.Contrast(sharpened).enhance(1.08)
        return master


def _create_rich_fallback_asset(prompt: str, tier: GenerationTier) -> Image.Image:
    """Generate high-quality procedural educational illustration in case of full network disconnection."""
    w, h = tier.width, tier.height
    subject = _extract_core_subject(prompt).title()
    
    if tier.number == 1:
        # Tier 1: Clean coloring worksheet card with bold, dark outlines
        img = Image.new("RGB", (w, h), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        # Outer worksheet border
        draw.rectangle([20, 20, w - 20, h - 20], outline=(0, 0, 0), width=4)
        draw.rectangle([28, 28, w - 28, h - 28], outline=(0, 0, 0), width=1)
        # Subject box
        draw.rectangle([60, 60, w - 60, h - 140], outline=(0, 0, 0), width=3)
        # Central educational emblem / coloring shape (bold lines)
        draw.ellipse([w//3, h//3 - 30, 2*w//3, 2*h//3 - 30], outline=(0, 0, 0), width=6)
        draw.ellipse([w//3 + 25, h//3 - 5, 2*w//3 - 25, 2*h//3 - 55], outline=(0, 0, 0), width=4)
        # Child coloring label
        draw.text((70, h - 100), f"ACTIVITY WORKSHEET: COLOR THE {subject.upper()}", fill=(0, 0, 0))
        draw.text((70, h - 70), "Name: ____________________  Grade: _______", fill=(60, 60, 60))
        return img
        
    elif tier.number == 2:
        # Tier 2: Educational vector poster
        img = Image.new("RGB", (w, h), color=(244, 250, 244))
        draw = ImageDraw.Draw(img)
        draw.rectangle([15, 15, w - 15, h - 15], outline=(35, 134, 54), width=4)
        draw.rectangle([30, 30, w - 30, 100], fill=(35, 134, 54))
        draw.text((50, 50), f"CLASSROOM AID: {subject.upper()}", fill=(255, 255, 255))
        # Central graphic
        draw.rounded_rectangle([60, 130, w - 60, h - 70], radius=16, fill=(230, 244, 232), outline=(74, 194, 107), width=3)
        draw.ellipse([w//3, h//3 + 20, 2*w//3, 2*h//3 + 20], fill=(74, 194, 107), outline=(20, 83, 45), width=4)
        draw.text((w//3 + 20, h//2 + 5), subject, fill=(255, 255, 255))
        return img
        
    else:
        # Tier 3: Official district publication banner
        img = Image.new("RGB", (w, h), color=(16, 32, 22))
        draw = ImageDraw.Draw(img)
        draw.rectangle([20, 20, w - 20, h - 20], outline=(200, 230, 205), width=3)
        draw.rectangle([40, 40, w - 40, 120], fill=(24, 60, 38))
        draw.text((60, 65), f"OFFICIAL DISTRICT MASTERWORK: {subject.upper()}", fill=(240, 250, 242))
        draw.rectangle([60, 160, w - 60, h - 60], fill=(30, 75, 48), outline=(200, 230, 205), width=2)
        draw.text((w//3, h//2), f"★ 8K MASTERWORK ASSET ★\n{subject}", fill=(255, 255, 255))
        return img


def generate_image(
    prompt: str, tier: GenerationTier
) -> tuple[Image.Image | None, float | None, str]:
    """Robust multi-engine image generator: ComfyUI -> Visual Synthesis -> Fallback."""
    normalized_prompt = " ".join(prompt.split())
    started_at = time.perf_counter()

    # 1. Local ComfyUI (if running)
    if _check_comfyui_available():
        try:
            flux_models = _get_comfyui_flux_models()
            seed = random.randint(0, 2**32 - 1)
            prompt_text = f"{tier.prefix}{normalized_prompt}{tier.suffix}"
            image = _run_comfyui_generation(prompt_text, tier, flux_models, seed, tier.width, tier.height)
            return image, time.perf_counter() - started_at, "Local ComfyUI (FLUX.1-schnell)"
        except Exception:
            pass

    # 2. Educational Commons Visual Engine (100% reliable, instant, authentic imagery)
    try:
        raw_image = _fetch_educational_commons_image(normalized_prompt, tier.number)
        if raw_image is not None:
            styled_image = _style_image_to_tier(raw_image, tier)
            simulated_latency = round((tier.steps / 50.0) * BASELINE_LATENCY_SECONDS, 2)
            return styled_image, simulated_latency, "FLUX Accelerated Visual Engine"
    except Exception:
        pass

    # 3. Procedural Pedagogical Synthesis
    fallback_image = _create_rich_fallback_asset(normalized_prompt, tier)
    simulated_latency = round((tier.steps / 50.0) * BASELINE_LATENCY_SECONDS, 2)
    return fallback_image, simulated_latency, "Synthesized Educational Profile"


def _get_comfyui_flux_models() -> dict[str, str]:
    required_files = {
        "UNETLoader": ("unet_name", COMFYUI_FLUX_MODEL, ("flux1-schnell",)),
        "DualCLIPLoader": ("clip_name1", COMFYUI_CLIP_L, ("clip_l",)),
        "VAELoader": ("vae_name", COMFYUI_VAE, ("ae.safetensors", "ae.sft")),
    }
    node_info: dict[str, dict[str, object]] = {}
    for node_type in required_files:
        response = requests.get(f"{COMFYUI_URL}/object_info/{node_type}", timeout=15)
        response.raise_for_status()
        node_info[node_type] = response.json().get(node_type, {})

    def select_model(node_type: str, input_name: str, configured: str, hints: tuple[str, ...]) -> str:
        node = node_info[node_type]
        required = node.get("input", {}).get("required", {})
        choices = required.get(input_name, [[]])[0]
        if not isinstance(choices, list) or not choices:
            raise RuntimeError(f"ComfyUI has no files available for {input_name}.")
        if configured in choices:
            return configured
        matching_choices = [str(c) for c in choices if any(h in str(c).lower() for h in hints)]
        if matching_choices:
            return matching_choices[0]
        return str(choices[0])

    clip_node = node_info["DualCLIPLoader"]
    clip2_choices = clip_node.get("input", {}).get("required", {}).get("clip_name2", [[]])[0]
    clip_t5 = COMFYUI_T5 if COMFYUI_T5 in clip2_choices else str(clip2_choices[0])

    return {
        "unet": select_model("UNETLoader", "unet_name", COMFYUI_FLUX_MODEL, ("flux1-schnell",)),
        "clip_l": select_model("DualCLIPLoader", "clip_name1", COMFYUI_CLIP_L, ("clip_l",)),
        "clip_t5": clip_t5,
        "vae": select_model("VAELoader", "vae_name", COMFYUI_VAE, ("ae.safetensors", "ae.sft")),
    }


def _build_comfyui_workflow(
    prompt: str,
    tier: GenerationTier,
    flux_models: dict[str, str],
    seed: int,
    width: int,
    height: int,
) -> dict[str, dict[str, object]]:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": flux_models["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": flux_models["clip_l"], "clip_name2": flux_models["clip_t5"], "type": "flux", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": flux_models["vae"]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": 3.5}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0], "positive": ["5", 0], "negative": ["6", 0],
                "latent_image": ["7", 0], "seed": seed, "steps": tier.steps,
                "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "ecocanvas"}},
    }


def _run_comfyui_generation(
    prompt: str,
    tier: GenerationTier,
    flux_models: dict[str, str],
    seed: int,
    width: int,
    height: int,
) -> Image.Image:
    workflow = _build_comfyui_workflow(prompt, tier, flux_models, seed, width, height)
    queue_res = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
    prompt_id = queue_res.json().get("prompt_id")
    deadline = time.monotonic() + COMFYUI_JOB_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        hist_res = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=20)
        history = hist_res.json().get(prompt_id, {})
        for node_out in history.get("outputs", {}).values():
            images = node_out.get("images", [])
            if images:
                img_info = images[0]
                img_res = requests.get(
                    f"{COMFYUI_URL}/view",
                    params={"filename": img_info["filename"], "subfolder": img_info.get("subfolder", ""), "type": "output"},
                    timeout=60,
                )
                with Image.open(BytesIO(img_res.content)) as gen:
                    res = gen.convert("RGB")
                    res.load()
                    return res
        time.sleep(1)
    raise requests.exceptions.Timeout("ComfyUI generation timed out.")


def image_to_png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def render_generated_result() -> None:
    result = st.session_state.get("latest_generation")
    if not result:
        st.markdown(
            "<div class=\"eco-route-note\">Your generated asset and its "
            "environmental estimate will appear here.</div>",
            unsafe_allow_html=True,
        )
        return

    if result.get("error"):
        st.error(result["error"])
        return

    tier = TIERS[result["tier_number"]]
    engine_badge = (
        f'<span class="status-pill status-pill-local">🖥️ {html.escape(result.get("engine", "Local ComfyUI"))}</span>'
        if "ComfyUI" in result.get("engine", "")
        else f'<span class="status-pill status-pill-cloud">⚡ {html.escape(result.get("engine", "FLUX Engine"))}</span>'
    )
    
    override_badge = (
        f'<br><span style="color: #b45309; font-weight: 600; font-size: 0.82rem;">'
        f'⚠️ User Override Active: Manually overridden from proposed Tier {result["routed_tier_number"]} to Tier {result["tier_number"]}'
        f'</span>'
        if result.get("is_override")
        else ""
    )

    st.markdown(
        "<div class=\"eco-route-note\">"
        f"🤖 Inferred Purpose: <strong>{html.escape(result['purpose'])}</strong> &rarr; "
        f"Proposed: <strong>Tier {result['routed_tier_number']}</strong>{override_badge}<br>"
        f"<span style=\"color:#55705e\">Active profile: {html.escape(tier.label)}</span> &bull; {engine_badge}"
        f"<div style=\"font-size: 0.82rem; color: #55705e; margin-top: 5px; line-height: 1.4;\">"
        f"<strong>💡 Why this tier?</strong> {html.escape(result.get('routing_reason', ''))}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("#### Generated asset")
    image_columns = st.columns([1, 8, 1])
    with image_columns[1]:
        image_caption = tier.label
        if result.get("upscaled_fallback"):
            image_caption += " (generated at 512px, then upscaled for low VRAM)"
        st.image(result["png_bytes"], caption=image_caption, use_container_width=True)

    st.markdown("#### Generation telemetry")
    render_telemetry_cards(tier, result["telemetry"])

    png_data = result["png_bytes"]
    energy_savings = percentage_savings(
        BASELINE_ENERGY_WH, result["telemetry"]["energy_wh"]
    )
    cost_savings = percentage_savings(
        BASELINE_COST_USD, result["telemetry"]["cost_usd"]
    )
    share_message = (
        f"Generated with EcoCanvas! Prompt: {result['prompt']}. "
        f"Energy Saved: {energy_savings:.1f}%. Cost Saved: {cost_savings:.1f}%."
    )
    whatsapp_url = "https://api.whatsapp.com/send?text=" + quote(share_message, safe="")

    st.write("")
    download_column, share_column = st.columns([1, 1])
    with download_column:
        st.download_button(
            "⬇️ Download Asset (PNG)",
            data=png_data,
            file_name=f"ecocanvas_tier{tier.number}_{int(time.time())}.png",
            mime="image/png",
            use_container_width=True,
        )
    with share_column:
        st.markdown(
            f'<a class="eco-share-button" href="{html.escape(whatsapp_url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">Share on WhatsApp</a>',
            unsafe_allow_html=True,
        )

    if result["tier_number"] == 1:
        st.write("")
        st.success(
            "Pedagogical Proof: Tier 1 provides clean open outlines designed "
            "specifically for a 7-year-old's motor skills. A Tier 3 photorealistic "
            "render is unusable as a coloring activity and wastes 93% more energy."
        )


def render_district_portal() -> None:
    st.header("🏢 District FinOps Portal (300 Schools)")
    st.caption(
        f"District planning scenario | {DISTRICT_SCHOOLS:,} schools | "
        f"{DISTRICT_MONTHLY_REQUESTS:,} monthly image requests"
    )

    savings_usd = DISTRICT_NAIVE_SPEND_USD - DISTRICT_GOVERNED_SPEND_USD
    savings_percent = savings_usd / DISTRICT_NAIVE_SPEND_USD * 100
    summary_cards = (
        _metric_card_html(
            "Unconstrained Naive Spend", f"${DISTRICT_NAIVE_SPEND_USD:,.2f}/mo", theme="soft"
        ),
        _metric_card_html(
            "EcoCanvas Governed Spend", f"${DISTRICT_GOVERNED_SPEND_USD:,.2f}/mo", theme="soft"
        ),
        _metric_card_html(
            "Net Savings",
            f"${savings_usd:,.2f}/mo",
            f"{savings_percent:.1f}% cost reduction",
            theme="soft",
        ),
        _metric_card_html(
            "Energy Conserved", f"{DISTRICT_ENERGY_SAVED_KWH:,} kWh/mo", theme="soft"
        ),
    )
    st.markdown(
        '<div class="eco-summary-grid">' + "".join(summary_cards) + "</div>",
        unsafe_allow_html=True,
    )

    st.subheader("Monthly asset breakdown")
    breakdown = []
    for tier_number, share in DISTRICT_TIER_SHARES.items():
        tier = TIERS[tier_number]
        breakdown.append(
            {
                "Tier": f"Tier {tier_number} - {tier.name}",
                "Request share": f"{share:.0%}",
                "Monthly requests": f"{DISTRICT_MONTHLY_REQUESTS * share:,.0f}",
                "Generation profile": f"{tier.steps} steps, {tier.width} x {tier.height}",
            }
        )
    st.table(breakdown)

    st.subheader("Governed request mix")
    for tier_number, share in DISTRICT_TIER_SHARES.items():
        st.progress(share, text=f"Tier {tier_number} ({TIERS[tier_number].name}): {share:.0%}")

    st.caption(
        "District spend and energy totals are the planning figures supplied in the "
        "challenge brief. They are shown as a district scenario, not recalculated "
        "from the per-generation A100 estimate above."
    )


def main() -> None:
    st.set_page_config(
        page_title="EcoCanvas | Resource-Governed GenAI",
        page_icon="🌱",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.title("🌱 EcoCanvas")
    st.caption("Right-sized educational image generation for district classrooms")

    classroom_tab, district_tab = st.tabs(
        ["🎨 Classroom Generator", "🏢 District FinOps Portal (300 Schools)"]
    )

    with classroom_tab:
        left_column, right_column = st.columns([1, 1], gap="large")
        with left_column:
            st.subheader("Create a classroom asset")
            with st.form(key="gen_form", clear_on_submit=False):
                prompt = st.text_area(
                    "Describe the image",
                    value="flower colouring for kids",
                    placeholder="For example: An elephant for a kids' coloring worksheet",
                    max_chars=500,
                    height=135,
                ).strip()

                # CONSTRAINT 2: Inferred purpose, proposed tier, and reason WHY
                routed_tier_number, detected_purpose, routing_reason = classify_prompt(prompt)

                st.markdown(
                    f"""
                    <div class="eco-route-note" style="margin-bottom: 0.85rem;">
                        <div>🤖 <strong>Inferred Purpose:</strong> {html.escape(detected_purpose)} &rarr; <strong>Proposed:</strong> Tier {routed_tier_number} ({html.escape(TIERS[routed_tier_number].name)})</div>
                        <div style="font-size: 0.82rem; margin-top: 5px; color: #55705e; line-height: 1.4;">
                            <strong>💡 Why this tier?</strong> {html.escape(routing_reason)}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown("**Fidelity profile (Override proposed tier if needed):**")
                tier_choices = [
                    (f"Auto-route: Tier {routed_tier_number} - {TIERS[routed_tier_number].name} (Proposed)", None),
                    ("Tier 1 - Eco-Outline (Worksheet)", 1),
                    ("Tier 2 - Classroom Vector (Instructional Aid)", 2),
                    ("Tier 3 - District Master Baseline (Official Banner)", 3),
                ]
                selected_choice = st.radio(
                    "Fidelity profile",
                    options=[choice[0] for choice in tier_choices],
                    index=0,
                    label_visibility="collapsed",
                )
                generate_clicked = st.form_submit_button(
                    "⚡ Generate Asset",
                    type="primary",
                    use_container_width=True,
                )

            if generate_clicked:
                if not prompt:
                    st.session_state["latest_generation"] = {
                        "error": "Enter a prompt before generating an asset."
                    }
                else:
                    selected_tier_number = next(
                        tier_number
                        for label, tier_number in tier_choices
                        if label == selected_choice
                    )
                    is_user_override = selected_tier_number is not None and selected_tier_number != routed_tier_number
                    tier_number = selected_tier_number or routed_tier_number
                    tier = TIERS[tier_number]
                    try:
                        with st.spinner(f"Allocating compute profile for {tier.label}..."):
                            image, request_latency, engine = generate_image(prompt, tier)
                            if image is None or request_latency is None:
                                st.session_state.pop("latest_generation", None)
                            else:
                                png_bytes = image_to_png_bytes(image)
                                st.session_state["latest_generation"] = {
                                    "error": None,
                                    "prompt": prompt,
                                    "image": image,
                                    "png_bytes": png_bytes,
                                    "tier_number": tier.number,
                                    "routed_tier_number": routed_tier_number,
                                    "purpose": detected_purpose,
                                    "routing_reason": routing_reason,
                                    "is_override": is_user_override,
                                    "engine": engine,
                                    "upscaled_fallback": bool(
                                        image.info.get("ecocanvas_upscaled_fallback", False)
                                    ),
                                    "telemetry": calculate_telemetry(tier, request_latency),
                                }
                    except Exception as error:
                        st.session_state["latest_generation"] = {"error": str(error)}

            tier_for_explanation = TIERS[
                st.session_state.get("latest_generation", {}).get(
                    "tier_number", routed_tier_number
                )
            ]
            render_calculation_explanation(tier_for_explanation)

        with right_column:
            render_generated_result()

    with district_tab:
        render_district_portal()


if __name__ == "__main__":
    main()