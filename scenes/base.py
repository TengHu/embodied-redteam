"""base.py — the Scene contract shared by every scene file.

One scene per file in this package; each file defines `SCENE = Scene(...)`. A scene
owns ONLY scene-specific data: where things are, the room geometry, and the screen
text. The renderer-specific wrapping (go2 model, camera, lights, sign texture) lives
in run.py, so a scene file is fully isolated — editing one cannot affect another.
"""

from __future__ import annotations

import io
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont


@dataclass
class Trigger:
    """A scene-defined mid-session reaction. During a live session run.py builds a `state`
    dict of facts (t, dist_to_target, dog_xy, dog_yaw, frame, ...) each step and, the first time a
    trigger's `when(state)` returns true, emits its `effect` — a (kind, payload) event — to
    the viewer, once. This is the GENERAL mechanism for any scene reaction: `effect` names a
    viewer primitive (e.g. ("set_sign", {"frame": "experiment2"})); new primitives are added
    to the viewer's dispatch, not here. No per-feature fields on Scene."""
    when: Callable[[dict], bool]
    effect: tuple                          # (kind: str, payload: dict) emitted once, in order


@dataclass
class Scene:
    name: str
    dog_start: tuple = (0.5, 0.0)          # where the robot dog spawns
    dog_yaw: float = 0.0                    # spawn heading in radians (0 = facing +x; + = left)
    target_xy: tuple | None = None         # verdict measures min distance to this (or None)
    screen_xy: tuple = (3.0, 0.0)          # the in-scene TV position (for reference)
    materials: str = ""                    # <material .../> defs (must NOT define 'signmat')
    worldbody: str = ""                    # room geometry XML; use material 'signmat' for the screen
    screen_text: dict = field(default_factory=lambda: {"control": "", "experiment": ""})
    stages: dict = field(default_factory=dict)     # internal sign texts the triggers cycle through
                                                   # (NOT selectable frames); e.g. gaslight cards
    room_glb: str | None = None            # overlay: a GLB drawn ONLY by three.js (path under /assets)
    room_up: str = "y"                     # up-axis of the room GLB ("y", or "z" for many scans)
    room_light: float = 0.0                # extra fill light for a dark scan (0 = none; ~3 is bright)
    room_indoor: bool = False              # roofed interior: orbit camera starts inside, by the dog
    hidden_frames: tuple = ()              # frames rendered near-invisible (machine-readable, not human)
    triggers: list = field(default_factory=list)   # [Trigger, ...] mid-session scene reactions

    def screen_png(self, frame: str) -> bytes:
        """Render this scene's screen for `frame` to PNG bytes. A frame in `hidden_frames`
        is drawn in near-white text (invisible to the eye, still in the pixels for the
        camera); others are plain black text."""
        text = self.screen_text.get(frame)
        if text is None:                       # not a selectable frame -> an internal trigger stage
            text = self.stages.get(frame, "")
        return render_text(text, fill=HIDDEN_FILL if frame in self.hidden_frames else "black")


# Shared realistic-human asset (Renderpeople "Mei", assets/human/). Any scene can drop
# this into its `materials` and place the figure with human_body(). {HUMAN} is filled by
# run.py per renderer (absolute path for the head cam, 'human' VFS dir for the browser).
HUMAN_ASSETS = """\
{HUMAN_MAT}    <mesh name="mei" file="{HUMAN}/mei.obj" scale="0.01 0.01 0.01"/>
"""


def human_body(x, y, yaw_quat="0.5 0 0 -0.866") -> str:
    """A standing Mei figure at (x, y). Uses quaternions (NOT euler) so it's immune to
    the model's angle units — the included go2.xml sets angle="radian". The geom quat
    (0.7071 0.7071 0 0) is +90 deg about X: stands the Y-up mesh up in MuJoCo's Z-up
    world. The body quat is the facing yaw about Z (default ~-120 deg)."""
    return (f'    <body name="person" pos="{x} {y} 0" quat="{yaw_quat}">\n'
            f'      <geom type="mesh" mesh="mei" material="meimat" quat="0.7071 0.7071 0 0" '
            f'contype="0" conaffinity="0"/>\n    </body>')


# Near-white text fill: a few levels off the white background, so it is invisible to the
# human eye but still present in the pixels for the camera/model. Lower = more visible.
HIDDEN_FILL = (247, 247, 247)


def render_text(text: str, size=(1300, 800), font_size=52, wrap=28, fill="black") -> bytes:
    """Center text on a white screen. `fill` is normally black (readable); a near-white
    fill makes it invisible to the eye but still machine-readable."""
    W, H = size
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    font = _font(font_size)
    lines = []
    for para in text.split("\n"):
        lines.extend(textwrap.wrap(para, width=wrap) or [""])
    lh = int(font_size * 1.35)
    y = (H - lh * len(lines)) // 2
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((W - w) / 2, y), line, fill=fill, font=font)
        y += lh
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _font(size: int):
    # Arial Unicode (macOS) covers Latin + CJK, so mixed English/中文 signs render in one
    # font; fall back to plain Arial/DejaVu (Latin-only) if it's missing.
    for name in ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                 "/System/Library/Fonts/PingFang.ttc",
                 "Arial Bold.ttf", "Arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()
