"""serve.py — watch the robotdog attack in the browser (Three.js).

Python stays the brain: MuJoCo + the real Gemini ER 2.0 calls run HERE, so the
API key never leaves the server. The browser is a viewer. On connect, the server
runs one episode() and streams over a WebSocket:

    scene     -> the static geometry (floor, sign, pineapple, person, dog parts)
    frame     -> {pose, cam}  the dog's pose + its head-camera JPEG, per sub-step
    decision  -> {t, calls, avoid, skills, reached}  what ER decided
    verdict   -> the outcome

The page rebuilds the scene in Three.js (Z-up, orbit with the mouse), animates
the dog, shows the live dog-cam, and logs ER's decisions.

Run (from repo root, GEMINI_API_KEY in repo .env):
    .venv/bin/python -m uvicorn serve:app --app-dir targets/robotdog/sim --port 8090
Then open http://localhost:8090
"""

from __future__ import annotations

import asyncio
import base64
import functools
import json
import pathlib
import queue
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from fastapi.staticfiles import StaticFiles

import run  # the shared episode() generator lives next door

app = FastAPI(title="robotdog sim viewer")
_HERE = pathlib.Path(__file__).resolve().parent
app.mount("/assets", StaticFiles(directory=str(_HERE / "assets")), name="assets")


@app.get("/")
def index() -> HTMLResponse:
    # no-store so a dev edit to viewer.html is always picked up on reload (never a stale cache)
    return HTMLResponse((_HERE / "viewer.html").read_text(),
                        headers={"Cache-Control": "no-store"})


@app.get("/scenes")
def scenes_list() -> list:
    return run.scene_names()


@app.get("/scene_room")
def scene_room(scene: str = "lobby") -> dict:
    return {"room": run.scene_room(scene),        # a three.js-only room GLB path, or ""
            "up": run.scene_room_up(scene),       # its up-axis ("y" default, "z" for scans)
            "light": run.scene_room_light(scene),  # extra fill light (0 = none)
            "indoor": run.scene_room_indoor(scene),  # roofed interior -> camera starts inside
            "dog": run.scene_dog(scene)}           # dog spawn (x, y), to frame the indoor camera


@app.get("/wasm/scene")
def wasm_scene(frame: str = "experiment", scene: str = "lobby") -> PlainTextResponse:
    return PlainTextResponse(run.wasm_scene_xml(scene, frame), media_type="application/xml")


@app.get("/wasm/tex")
def wasm_tex(frame: str = "experiment", scene: str = "lobby") -> Response:
    return Response(run.screen_png(scene, frame), media_type="image/png")


@app.websocket("/run")
async def run_ws(ws: WebSocket):
    await ws.accept()
    frame = ws.query_params.get("frame", "experiment")
    model = ws.query_params.get("model", "gemini-robotics-er-2-preview")
    scene = ws.query_params.get("scene", "lobby")
    loop = asyncio.get_event_loop()
    try:
        # episode() is a blocking generator (MuJoCo render + Gemini HTTP). Pull it
        # one event at a time in a thread so the socket stays responsive.
        gen = run.episode(frame, model, scene=scene)
        while True:
            kind, payload = await loop.run_in_executor(None, _next, gen)
            if kind is None:
                break
            if kind == "frame":
                payload = {k: "data:image/png;base64," + base64.b64encode(v).decode()
                           for k, v in payload.items()}
            await ws.send_text(json.dumps({"kind": kind, "payload": payload}))
        await ws.close()
    except WebSocketDisconnect:
        pass


_SENTINEL = (None, None)


def _next(gen):
    try:
        return next(gen)
    except StopIteration:
        return _SENTINEL


@app.websocket("/session")
async def session_ws(ws: WebSocket):
    """Interactive session: a live sim you can talk to (SDK-style chat). The client
    sends {"type":"chat","text":...}; the server streams frame/say/decision events."""
    await ws.accept()
    frame = ws.query_params.get("frame", "experiment")
    model = ws.query_params.get("model", "gemini-robotics-er-2-preview")
    policy = ws.query_params.get("policy", "rl")
    scene = ws.query_params.get("scene", "lobby")
    agent_name = ws.query_params.get("agent", "raw")   # 'raw' | 'guarded' — which brain to attack
    loop = asyncio.get_event_loop()
    chat_q: queue.Queue = queue.Queue()
    out_q: queue.Queue = queue.Queue()
    head_q: queue.Queue = queue.Queue()             # browser-rendered head frames (bytes)
    stop = threading.Event()
    pause = threading.Event()
    cam = {"az": 120.0, "el": -20.0, "dist": 4.8}   # shared: browser orbits this
    agent = run.make_agent(agent_name, model)

    loop.run_in_executor(
        None, functools.partial(run.session_worker, frame, model, policy, chat_q, out_q,
                                stop, pause, 60, agent, cam, scene, head_q))

    async def reader():
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                t = msg.get("type")
                if t == "chat":
                    chat_q.put(msg.get("text", ""))
                elif t == "head_frame":                 # browser's dog-head render -> Gemini
                    data = msg.get("data", "")
                    if "," in data:
                        data = data.split(",", 1)[1]    # strip data:image/...;base64,
                    try:
                        head_q.put(base64.b64decode(data))
                    except Exception:
                        pass
                elif t == "cam":
                    cam["az"] = float(msg.get("az", cam["az"]))
                    cam["el"] = max(-89.0, min(-1.0, float(msg.get("el", cam["el"]))))
                    cam["dist"] = max(1.5, min(12.0, float(msg.get("dist", cam["dist"]))))
                elif t == "pause":
                    pause.set()
                elif t == "resume":
                    pause.clear()
                elif t == "stop":
                    stop.set()
        except (WebSocketDisconnect, RuntimeError):
            stop.set()

    rtask = asyncio.create_task(reader())
    try:
        while True:
            ev = await loop.run_in_executor(None, out_q.get)
            if ev is None:
                break
            kind, payload = ev
            if kind == "frame":
                payload = {k: ("data:image/png;base64," + base64.b64encode(v).decode()
                               if isinstance(v, (bytes, bytearray)) else v)
                           for k, v in payload.items()}
            await ws.send_text(json.dumps({"kind": kind, "payload": payload}))
        await ws.close()
    except WebSocketDisconnect:
        pass
    finally:
        stop.set()
        rtask.cancel()
