"""Overlay drawing. cv2.putText cannot draw Korean, so non-ASCII labels go through Pillow
with a CJK font if one is installed (sudo apt install fonts-nanum)."""
import glob
import time

import cv2
import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None

FONT_GLOBS = [
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/**/*CJK*.tt*",
    "/usr/share/fonts/**/Nanum*.ttf",
    "C:/Windows/Fonts/malgun.ttf",
]

GREEN, RED, ORANGE, GRAY, WHITE = (60, 200, 60), (40, 40, 230), (0, 160, 255), (160, 160, 160), (255, 255, 255)


def _find_font(size=18):
    if Image is None:
        return None
    for pat in FONT_GLOBS:
        for path in glob.glob(pat, recursive=True):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return None


FONT = _find_font()
if FONT is None:
    print("[draw] Korean font not found - non-ASCII names shown as ASCII. "
          "Fix: sudo apt install fonts-nanum", flush=True)


def _ascii(s):
    return s.encode("ascii", "replace").decode()


def annotate(frame, persons, faces, status):
    """persons: [(x1,y1,x2,y2,score)], faces: [((x,y,w,h), name, score)]."""
    labels = []  # (text, (x, y), color)
    for x1, y1, x2, y2, s in persons:
        cv2.rectangle(frame, (x1, y1), (x2, y2), ORANGE, 2)
        labels.append((f"person {s:.2f}", (x1 + 2, max(y1 - 20, 0)), ORANGE))
    for (x, y, w, h), name, s in faces:
        if name == "?":
            color, text = GRAY, "face (too small)"
        elif name is None:
            color, text = RED, f"Unknown {s:.2f}"
        else:
            color, text = GREEN, f"{name} {s:.2f}"
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        labels.append((text, (x, y + h + 2), color))

    # status bar
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 24), (0, 0, 0), -1)
    top = time.strftime("%Y-%m-%d %H:%M:%S") + f"  {status['fps']:.1f} FPS"
    if status.get("motion"):
        top += "  MOTION"
    labels.append((top, (6, 2), WHITE))
    if status.get("rec"):
        cv2.circle(frame, (frame.shape[1] - 60, 12), 6, (0, 0, 255), -1)
        labels.append(("REC", (frame.shape[1] - 48, 2), (0, 0, 255)))

    if FONT is not None and any(not t.isascii() for t, _, _ in labels):
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(img)
        for t, (x, y), c in labels:
            d.text((x, y), t, font=FONT, fill=(c[2], c[1], c[0]), stroke_width=2, stroke_fill=(0, 0, 0))
        frame[:] = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    else:
        for t, (x, y), c in labels:
            t = _ascii(t)
            cv2.putText(frame, t, (x, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(frame, t, (x, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, c, 1, cv2.LINE_AA)
    return frame
