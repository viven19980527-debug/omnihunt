"""Generate OmniHunt app icons (PWA + iOS AppIcon).

Outputs:
  omnihunt/assets/icons/icon-180.png
  omnihunt/assets/icons/icon-192.png
  omnihunt/assets/icons/icon-512.png
  ios/OmniHunt/Assets.xcassets/AppIcon.appiconset/Icon-1024.png

Run: python tools/make_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SIZE = 1024
BG = (10, 12, 16)
C1 = (94, 242, 176)   # mint
C2 = (78, 168, 255)   # blue
C3 = (196, 139, 255)  # violet


def lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def gradient_color(t: float) -> tuple[int, int, int]:
    if t < 0.55:
        return lerp(C1, C2, t / 0.55)
    return lerp(C2, C3, (t - 0.55) / 0.45)


def build_master() -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), BG)
    pad = int(SIZE * 0.115)
    w = SIZE - 2 * pad

    panel = Image.new("RGB", (w, w))
    draw = ImageDraw.Draw(panel)
    for i in range(2 * w - 1):
        draw.line([(i, 0), (0, i)], fill=gradient_color(i / (2 * w - 2)))

    mask = Image.new("L", (w, w), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, w - 1], radius=int(w * 0.235), fill=255)
    img.paste(panel, (pad, pad), mask)

    inner = int(SIZE * 0.395)
    off = (SIZE - inner) // 2
    ImageDraw.Draw(img).rounded_rectangle(
        [off, off, off + inner, off + inner], radius=int(inner * 0.27), fill=BG
    )
    return img


def main() -> None:
    master = build_master()
    targets = {
        ROOT / "omnihunt" / "assets" / "icons" / "icon-512.png": 512,
        ROOT / "omnihunt" / "assets" / "icons" / "icon-192.png": 192,
        ROOT / "omnihunt" / "assets" / "icons" / "icon-180.png": 180,
        ROOT
        / "ios"
        / "OmniHunt"
        / "Assets.xcassets"
        / "AppIcon.appiconset"
        / "Icon-1024.png": 1024,
    }
    for path, size in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        img = master if size == SIZE else master.resize((size, size), Image.LANCZOS)
        img.save(path, format="PNG", optimize=True)
        print(f"{size:>4}px -> {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
