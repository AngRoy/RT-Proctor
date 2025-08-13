# RT Proctor — Sprint 13 (MVP)

Real‑time cheating detection for online coding assessments with strict calibration, video/audio/keystroke proctoring, AOI‑aware gaze, speaker embeddings (MFCC), Judge0 execution (C/C++/Java/Python), final report (PDF/CSV), admin dashboard, auth‑lite, and configurable thresholds.

## Quick Start

### API
```bat
cd apps\api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn rt_proctor.main:app --reload
```

### Judges / Compilers (Judge0)
```bat
cd infra
docker compose up -d
```

In the API shell set:
```bat
set USE_FAKE_EXEC=false
set JUDGE0_URL=http://localhost:2358
```

### Web
```bat
cd apps\web
npm i
npm run dev
```

Open http://localhost:5173 and enter **exam token** `EXAM123`. For /admin or report export, use **admin password** `ADMIN123`.

See `apps/api/config.yaml` to change thresholds and credentials.

---

## Features
- Server‑gated **Calibration** (camera+mic+no‑headphones+5 poses+audio enrollment).
- **Fullscreen** exit: beep + modal + **persisted flag** in report.
- **Gaze**: off‑screen ratio + blink rate + **AOI‑aware** (when on editor/problem).
- **Audio**: VAD, conversation toggles, **other_speaker_strong** (MFCC cosine).
- **Keystrokes**: burst after idle (adaptive), mass delete.
- **Language change** flag across submissions.
- **Judge0** compile/execute for C/C++/Java/Python (or local Python fast path).
- **Report** page with timeline sparkline, snapshot gallery, **CSV/PDF** export.
- **Admin** sessions list with suspicion score.
- **Auth‑lite**: exam token + admin password; WebSockets also gated.
- **Config YAML** for thresholds (no code edits to tune).

## Troubleshooting
- If Node 20 throws `crypto.hash is not a function`, we pin Vite **5.4.10** (works).
- MediaPipe heavy? Optional; if it fails to load, calibration still blocks without face.
- Judge0 errors: ensure Docker is up and port 2358 is unused.
