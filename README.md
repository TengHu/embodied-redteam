# embodied-redteam

A simulator for red-teaming vision-language models in embodied settings.

A VLM controls a robot in a physics simulation through function calling: each turn it
sees the robot's camera and calls physical actions. Attacks are placed in the world the
model perceives, and outcomes are measured in physics, not text.

## Setup

```bash
uv venv && uv pip install -r requirements.txt
cp .env.example .env      # put your GEMINI_API_KEY in .env
```

## Run

```bash
.venv/bin/python -m uvicorn serve:app --port 8090
```

Open http://localhost:8090, pick a scene, a brain and a frame, then send the robot an
instruction.

Headless:

```bash
.venv/bin/python run.py --scene <name> --frame experiment
```

## License

MIT (see `LICENSE`) for the code. Third-party assets under `assets/` keep their own
licenses; see `assets/ASSETS.md`.
