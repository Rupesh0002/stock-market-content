# ─────────────────────────────────────────────────────────────
#  video_maker.py  —  MoviePy video assembly
# ─────────────────────────────────────────────────────────────
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    concatenate_videoclips,
)

import config

logger = logging.getLogger(__name__)

W = config.VIDEO_WIDTH    # 1080
H = config.VIDEO_HEIGHT   # 1920


# ── Text overlay ──────────────────────────────────────────────

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Load a TrueType font at *size* pts. Searches common cross-platform paths
    and falls back to PIL's built-in bitmap font if nothing is found.
    """
    search_paths = [
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"  if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf"        if bold else "/Library/Fonts/Arial.ttf",
        # Windows
        "C:/Windows/Fonts/arialbd.ttf"         if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf"        if bold else "C:/Windows/Fonts/calibri.ttf",
    ]
    for fp in search_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (OSError, IOError):
            continue
    # Ultimate fallback — no sizing control
    return ImageFont.load_default()


def _make_text_overlay(width: int, height: int, channel_name: str) -> np.ndarray:
    """
    Build a full-frame RGBA numpy array with a semi-transparent bottom strip
    containing the channel name and disclaimer.

    Returns shape (H, W, 4) uint8.
    """
    img  = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    strip_h = 160
    strip_y = height - strip_h
    draw.rectangle([(0, strip_y), (width, height)], fill=(0, 0, 0, 175))

    font_ch   = _load_font(54, bold=True)
    font_disc = _load_font(34, bold=False)

    # Channel name — centred
    draw.text(
        (width // 2, strip_y + 52), channel_name,
        font=font_ch, fill=(255, 255, 255, 230), anchor="mm",
    )
    # Disclaimer
    draw.text(
        (width // 2, strip_y + 118), "Not Financial Advice",
        font=font_disc, fill=(180, 180, 180, 200), anchor="mm",
    )

    return np.array(img)


# ── Ken Burns zoom ────────────────────────────────────────────

def _zoom_in(clip: ImageClip, zoom_ratio: float = 0.05) -> ImageClip:
    """
    Apply a slow Ken Burns zoom-in effect.

    At t=0 the frame is shown at 100%; at t=duration it is shown at
    (100 + zoom_ratio*100)% and cropped back to the original size.
    """
    base_w, base_h = clip.size

    def effect(get_frame, t: float) -> np.ndarray:
        frame  = get_frame(t)
        scale  = 1.0 + zoom_ratio * (t / clip.duration)
        new_w  = math.ceil(base_w * scale)
        new_h  = math.ceil(base_h * scale)
        # Ensure even dimensions (required by libx264)
        new_w += new_w % 2
        new_h += new_h % 2

        resized = Image.fromarray(frame).resize((new_w, new_h), Image.LANCZOS)
        x_off   = (new_w - base_w) // 2
        y_off   = (new_h - base_h) // 2
        cropped = resized.crop((x_off, y_off, x_off + base_w, y_off + base_h))
        return np.array(cropped)

    return clip.fl(effect, apply_to=["mask"])


# ── Single-video assembler ────────────────────────────────────

def _assemble(
    chart_path: Path,
    audio_path: Path,
    output_path: Path,
    channel_name: str,
) -> None:
    """
    Assemble one video from a chart image and an audio file.

    Steps:
        1. Load audio — its duration drives everything.
        2. Zoom chart with Ken Burns effect.
        3. Composite static text overlay on top.
        4. Fade in/out (video + audio).
        5. Export with libx264 / aac.
    """
    logger.info("Loading audio: %s", audio_path.name)
    audio = AudioFileClip(str(audio_path))
    duration = audio.duration
    logger.info("  Duration: %.1fs", duration)

    # ── Base image clip ───────────────────────────────────────
    img_clip = ImageClip(str(chart_path), duration=duration)
    img_clip = _zoom_in(img_clip)

    # ── Text overlay ──────────────────────────────────────────
    overlay_rgba = _make_text_overlay(W, H, channel_name)
    overlay_rgb  = overlay_rgba[:, :, :3]
    overlay_a    = overlay_rgba[:, :, 3].astype("float32") / 255.0

    text_clip = ImageClip(overlay_rgb, duration=duration)
    mask_clip = ImageClip(overlay_a, ismask=True, duration=duration)
    text_clip = text_clip.set_mask(mask_clip)

    # ── Composite ─────────────────────────────────────────────
    video = CompositeVideoClip([img_clip, text_clip], size=(W, H))

    # ── Fades ─────────────────────────────────────────────────
    fade_dur = 0.5
    video = video.fadein(fade_dur).fadeout(fade_dur)

    audio_faded = audio.audio_fadein(fade_dur).audio_fadeout(fade_dur)
    video = video.set_audio(audio_faded)

    # ── Export ────────────────────────────────────────────────
    logger.info("Exporting → %s", output_path.name)
    video.write_videofile(
        str(output_path),
        fps=config.VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
        preset=config.VIDEO_PRESET,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        logger=None,            # suppress moviepy's built-in progress output
        verbose=False,
    )

    video.close()
    audio.close()
    logger.info("Saved: %s  (%.1f MB)", output_path.name,
                output_path.stat().st_size / 1_048_576)


# ── Pipeline entry point ──────────────────────────────────────

def assemble_all_videos(
    charts: Dict[str, Path],
    audios: Dict[str, Path],
) -> Dict[str, Path]:
    """
    Assemble both videos and save them to the output directory.

    Args:
        charts: {'gainers': Path, 'overview': Path}
        audios: {'gainers': Path, 'overview': Path}

    Returns:
        {'gainers': Path, 'overview': Path}
    """
    out_dir = Path(config.OUTPUT_DIR)
    out_dir.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")

    outputs: Dict[str, Path] = {}
    for key in charts:
        if key not in audios:
            logger.warning("No audio for '%s' — skipping video.", key)
            continue
        output_path = out_dir / f"{key}_{date_str}.mp4"
        outputs[key] = output_path
        logger.info("Assembling %s video…", key)
        _assemble(
            chart_path=charts[key],
            audio_path=audios[key],
            output_path=output_path,
            channel_name=config.CHANNEL_NAME,
        )

    return outputs
