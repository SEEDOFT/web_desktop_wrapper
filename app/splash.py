from __future__ import annotations

import base64
import html
from pathlib import Path

from app.config import AppConfig
from app.logger import get_logger

logger = get_logger(__name__)

# Dark background color used during splash and transition.
# Must match the splash HTML body/container background so there is
# zero visual discontinuity between the CSS-rendered content and the
# native window chrome behind it.
SPLASH_BACKGROUND = "#030712"


def _load_splash_logo_data_uri(image_path: str | None = None) -> str:
    """Load image and encode as base64 data URI."""
    candidates: list[Path] = []
    if image_path:
        candidates.append(Path(image_path))

    project_root = Path(__file__).resolve().parents[1]
    candidates.extend(
        [
            project_root / "assets" / "digi_portrait.jpg",
            project_root / "assets" / "digi_landscape.jpg",
            Path("assets/digi_portrait.jpg"),
            Path("assets/digi_landscape.jpg"),
        ]
    )

    for candidate in candidates:
        if candidate.is_file():
            try:
                suffix = candidate.suffix.lower().lstrip(".")
                mime_type = "image/png" if suffix == "png" else "image/jpeg"
                encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
                return f"data:{mime_type};base64,{encoded}"
            except Exception as e:
                logger.debug("Failed to read splash image %s: %s", candidate, e)

    # Fallback inline SVG emblem when no image asset is present
    return (
        "data:image/svg+xml;base64,"
        + base64.b64encode(
            b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">
                <defs>
                    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stop-color="#38bdf8"/>
                        <stop offset="100%" stop-color="#0284c7"/>
                    </linearGradient>
                </defs>
                <circle cx="60" cy="60" r="50" fill="url(#g)" opacity="0.9"/>
                <polygon points="45,35 85,60 45,85" fill="#ffffff"/>
            </svg>"""
        ).decode("ascii")
    )


def generate_splash_html(config: AppConfig) -> str:
    """Generate a full-window Once Human style loading splash screen.

    The splash fills the entire viewport with a deep-space dark background,
    a centred breathing logo with expanding aura halo, tracked uppercase
    title, and a pulsing status indicator.  The ``fadeOut`` JS function
    triggers a cinematic 1.2 s dissolve (scale-down + blur) that seamlessly
    transitions into the web application loaded by the same window.
    """
    title = html.escape(config.app_name)
    logo_uri = _load_splash_logo_data_uri(config.app_icon)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
*,*::before,*::after {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    user-select: none;
    -webkit-user-select: none;
}}

html, body {{
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: {SPLASH_BACKGROUND};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}}

/* ───── full-viewport splash layer ───── */
.splash {{
    position: fixed;
    inset: 0;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: radial-gradient(
        ellipse 90% 70% at 50% 46%,
        #111827 0%,
        #0a0e17 55%,
        {SPLASH_BACKGROUND} 100%
    );
    transition: opacity  1.4s cubic-bezier(0.16, 1, 0.3, 1),
                transform 1.4s cubic-bezier(0.16, 1, 0.3, 1),
                filter   1.2s cubic-bezier(0.16, 1, 0.3, 1);
    will-change: opacity, transform, filter;
}}

/* ───── atmospheric halo ring ───── */
.halo {{
    position: absolute;
    width: 380px;
    height: 380px;
    border-radius: 50%;
    border: 1px solid rgba(56, 189, 248, 0.05);
    animation: halo-expand 6s cubic-bezier(0.37, 0, 0.63, 1) infinite;
    pointer-events: none;
}}

/* ───── breathing aura glow ───── */
.aura {{
    position: absolute;
    width: 280px;
    height: 280px;
    border-radius: 50%;
    background: radial-gradient(
        circle,
        rgba(56, 189, 248, 0.30) 0%,
        rgba(14, 165, 233, 0.10) 50%,
        transparent 72%
    );
    animation: aura-breathe 5s cubic-bezier(0.37, 0, 0.63, 1) infinite;
    pointer-events: none;
}}

/* ───── logo container ───── */
.logo-frame {{
    position: relative;
    z-index: 2;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 144px;
    height: 144px;
    border-radius: 32px;
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.10);
    box-shadow:
        0 16px 50px rgba(0, 0, 0, 0.70),
        inset 0 1px 0 rgba(255, 255, 255, 0.15),
        0 0 0 1px rgba(0, 0, 0, 0.30);
    animation: frame-breathe 5s cubic-bezier(0.37, 0, 0.63, 1) infinite;
}}

.logo {{
    width: 108px;
    height: 108px;
    object-fit: contain;
    border-radius: 22px;
    filter: drop-shadow(0 0 20px rgba(56, 189, 248, 0.50));
    animation: logo-glow 5s cubic-bezier(0.37, 0, 0.63, 1) infinite;
}}

/* ───── title + status ───── */
.info {{
    position: relative;
    z-index: 2;
    margin-top: 32px;
    text-align: center;
}}

.title {{
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 7px;
    text-transform: uppercase;
    color: rgba(248, 250, 252, 0.88);
    text-shadow: 0 2px 16px rgba(0, 0, 0, 0.95);
}}

.status {{
    margin-top: 14px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 5px 16px;
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 100px;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: rgba(148, 163, 184, 0.75);
}}

.dot {{
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: #38bdf8;
    box-shadow: 0 0 10px rgba(56, 189, 248, 0.85);
    animation: dot-pulse 2.2s ease-in-out infinite;
}}

/* ───── keyframes ───── */
@keyframes frame-breathe {{
    0%, 100% {{ transform: scale(1); }}
    50%      {{ transform: scale(1.045); }}
}}

@keyframes aura-breathe {{
    0%, 100% {{ transform: scale(0.80); opacity: 0.28; }}
    50%      {{ transform: scale(1.50); opacity: 0.90; }}
}}

@keyframes halo-expand {{
    0%, 100% {{ transform: scale(0.65); opacity: 0; }}
    50%      {{ transform: scale(1.25); opacity: 0.45; }}
}}

@keyframes logo-glow {{
    0%, 100% {{ filter: drop-shadow(0 0 16px rgba(56, 189, 248, 0.35)); }}
    50%      {{ filter: drop-shadow(0 0 38px rgba(56, 189, 248, 0.90)); }}
}}

@keyframes dot-pulse {{
    0%, 100% {{ opacity: 0.30; transform: scale(0.85); }}
    50%      {{ opacity: 1;    transform: scale(1.30); }}
}}

/* ───── cinematic dissolve class ───── */
.splash.dissolve {{
    opacity: 0 !important;
    transform: scale(0.96) !important;
    filter: blur(18px) !important;
}}
</style>
</head>
<body>
<div class="splash" id="splash">
    <div class="halo"></div>
    <div class="aura"></div>
    <div class="logo-frame">
        <img class="logo" src="{logo_uri}" alt="{title}" />
    </div>
    <div class="info">
        <div class="title">{title}</div>
        <div class="status">
            <span class="dot"></span>
            <span>Loading</span>
        </div>
    </div>
</div>
<script>
window.fadeOut = function() {{
    var el = document.getElementById('splash');
    if (el) el.classList.add('dissolve');
}};
</script>
</body>
</html>"""
