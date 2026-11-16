"""Build the HA brand PNGs from images/brand/strung-logo.jpg (mark + wordmark, no tagline)."""
import sys
import numpy as np
from PIL import Image, ImageChops, ImageDraw

src, out = sys.argv[1], sys.argv[2]
BG = np.array([21, 34, 53], float)
im = Image.open(src).convert("RGB")
# Mark + wordmark: everything above the tagline
bgimg = Image.new("RGB", im.size, tuple(int(c) for c in BG))
mask = ImageChops.difference(im, bgimg).convert("L").point(lambda v: 255 if v > 40 else 0)
top = mask.crop((0, 0, im.width, 1230)).getbbox()
pad = 24
box = (top[0] - pad, top[1] - pad, top[2] + pad, top[3] + pad)
mark = im.crop(box)

def color_to_alpha(img: Image.Image) -> np.ndarray:
    """Remove the navy background: alpha from distance to it, colour un-blended."""
    a = np.asarray(img, float)
    d = a - BG
    # Largest fraction of the way from the background to black/white, per pixel
    room = np.where(d > 0, 255 - BG, BG)
    alpha = np.clip(np.max(np.abs(d) / room, axis=2), 0, 1)
    # JPEG noise and a faint vignette sit just above the background: drop them
    alpha = np.clip((alpha - 0.15) / 0.85, 0, 1)
    safe = np.where(alpha > 0, alpha, 1)[..., None]
    fg = np.clip(BG + d / safe, 0, 255)
    return np.dstack([fg, alpha * 255])

def save(rgba: np.ndarray, name: str, height: int) -> None:
    img = Image.fromarray(rgba.astype("uint8"), "RGBA")
    w = round(img.width * height / img.height)
    for scale, suffix in ((1, ""), (2, "@2x")):
        img.resize((w * scale, height * scale), Image.LANCZOS).save(f"{out}/{name}{suffix}.png", optimize=True)

dark = color_to_alpha(mark)
save(dark, "dark_logo", 128)
# Light backgrounds: white lettering becomes the logo's navy
light = dark.copy()
white = (light[..., 0] > 200) & (light[..., 1] > 200) & (light[..., 2] > 200)
light[white, :3] = BG
save(light, "logo", 128)

# Icon: the logo on its navy, as a rounded square
side = round(max(mark.size) * 1.15)
sq = Image.new("RGB", (side, side), tuple(int(c) for c in BG))
sq.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
icon = sq.convert("RGBA")
radius = side // 6
m = Image.new("L", (side, side), 0)
ImageDraw.Draw(m).rounded_rectangle((0, 0, side - 1, side - 1), radius, fill=255)
icon.putalpha(m)
for px, suffix in ((256, ""), (512, "@2x")):
    icon.resize((px, px), Image.LANCZOS).save(f"{out}/icon{suffix}.png", optimize=True)
print("mark", mark.size)
