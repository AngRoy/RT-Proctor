import os, time, json, io, csv
from typing import Any, Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session as DB
from .db import engine, SessionLocal, Base
from .models import Session as DBSession, Event, Flag, Submission
from .calibration import get_state, update as calib_update, check_ready
from .services.vision import face_and_gaze
from .services.audio import process_audio_chunk, audio_state
from .services import ctx as ctx
from .keystrokes import process_keys
from .plagiarism import similarity_score, web_like_local_search
from .config import get_config
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import httpx

DEBUG_ENDPOINTS = os.getenv('DEBUG_ENDPOINTS','false').lower()=='true'
USE_FAKE_EXEC = os.getenv('USE_FAKE_EXEC','true').lower()=='true'
JUDGE0_URL = os.getenv('JUDGE0_URL','http://localhost:2358')

app = FastAPI(title="RT Proctor API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

Base.metadata.create_all(bind=engine)

def _exam_ok(request: Request):
    cfg = get_config().get('auth',{})
    tok = (request.headers.get('x-exam') if request else None) or (request.query_params.get('token') if request else None)
    return (tok and tok == cfg.get('exam_token'))
def _admin_ok(request: Request):
    cfg = get_config().get('auth',{})
    pwd = (request.headers.get('x-admin') if request else None) or (request.query_params.get('admin') if request else None)
    return (pwd and pwd == cfg.get('admin_password'))

@app.get("/")
def root(): return {"ok":True}

@app.get("/media/images/{name}")
async def media_image(name: str):
    path = f"./media/images/{name}"
    if not os.path.exists(path): return JSONResponse({"error":"not found"}, status_code=404)
    return FileResponse(path)

# Calibration
@app.post("/api/calibration/start")
async def calib_start(payload: dict = {}, request: Request = None):
    if not _exam_ok(request): return JSONResponse({'error':'unauthorized'}, status_code=401)
    session_id = payload.get("session_id","demo-session")
    now = time.time()*1000
    db = SessionLocal()
    try:
        row = db.query(DBSession).filter_by(session_id=session_id).first()
        if not row:
            row = DBSession(session_id=session_id, calibrated=0, started_at=now, ended_at=0.0); db.add(row); db.commit()
        get_state(db, session_id)
        return {"session_id": session_id, "calibrated": bool(row.calibrated)}
    finally: db.close()

@app.get("/api/calibration/state")
async def calib_state(session_id: str = "demo-session", request: Request = None):
    if not _exam_ok(request) and not _admin_ok(request): return JSONResponse({'error':'unauthorized'}, status_code=401)
    db = SessionLocal()
    try:
        st = get_state(db, session_id); ready, missing = check_ready(st)
        return {"state": st, "ready": ready, "missing": missing}
    finally: db.close()

@app.post("/api/calibration/finalize")
async def calib_finalize(payload: dict, request: Request = None):
    if not _exam_ok(request): return JSONResponse({'error':'unauthorized'}, status_code=401)
    session_id = payload.get("session_id","demo-session")
    db = SessionLocal()
    try:
        st = get_state(db, session_id); ready, missing = check_ready(st)
        if not ready: return JSONResponse({"error":"calibration_incomplete","missing": missing, "state": st}, status_code=400)
        row = db.query(DBSession).filter_by(session_id=session_id).first()
        if not row: row = DBSession(session_id=session_id, calibrated=1, started_at=time.time()*1000); db.add(row)
        else: row.calibrated = 1
        db.commit(); return {"ok": True, "calibrated": True}
    finally: db.close()

# WebSockets
@app.websocket("/api/session/{session_id}/events")
async def ws_events(ws: WebSocket, session_id: str):
    token = ws.query_params.get('token')
    if token != get_config().get('auth',{}).get('exam_token'): await ws.close(code=4403); return
    await ws.accept()
    db = SessionLocal()
    try:
        while True:
            text = await ws.receive_text()
            evt = json.loads(text); etype = evt.get("t"); data = {k:v for k,v in evt.items() if k!='t'}
            ts_ms = int(time.time()*1000)
            if etype == "fs":
                db.add(Flag(session_id=session_id, ts=ts_ms, severity="warn" if data.get("state")=="exit" else "info", kind=f"fs_{data.get('state')}", details={})); db.commit()
                await ws.send_text(json.dumps({"level":"warn","code":"fs_exit"} if data.get("state")=="exit" else {"level":"info","code":"fs_enter"}))
            elif etype == "tab":
                db.add(Flag(session_id=session_id, ts=ts_ms, severity="warn", kind="tab_blur" if data.get("state")=="blur" else "tab_focus", details={})); db.commit()
                await ws.send_text(json.dumps({"level":"warn","code":"tab_blur"} if data.get("state")=="blur" else {"level":"info","code":"tab_focus"}))
            elif etype == "headphones":
                present = data.get("present") is True
                s = get_state(db, session_id)
                if present:
                    s['hardware']['no_headphones'] = False
                    db.add(Flag(session_id=session_id, ts=ts_ms, severity="high", kind="headphones", details={"present": True})); db.commit()
                    await ws.send_text(json.dumps({"level":"high","code":"headphones"}))
                else:
                    s['hardware']['no_headphones'] = True
                calib_update(db, session_id, s)
            elif etype == "ui_focus":
                ctx.set_focus(session_id, data.get("panel","other"))
            elif etype == "aoi":
                ctx.set_aoi(session_id, data.get("kind","other"), data.get("rect",{}))
            elif etype == "key":
                ctx.mark_key(session_id)
                for (sev, kind, det) in process_keys(session_id, etype, data):
                    db.add(Flag(session_id=session_id, ts=ts_ms, severity=sev, kind=kind, details=det)); db.commit()
                    await ws.send_text(json.dumps({"level":sev,"code":kind,"details":det}))
            elif etype == "frame":
                flags = face_and_gaze(session_id, data.get("jpegB64",""), data.get("phase",""), data.get("prompt"))
                s = get_state(db, session_id)
                s['hardware']['camera_ok'] = True
                if data.get("phase") == "calib":
                    s['video']['face_seen'] = True
                    pr = data.get("prompt")
                    if pr in ["CENTER","LEFT","RIGHT","UP","DOWN"]:
                        s['video'][pr] = True
                calib_update(db, session_id, s)
                for f in flags:
                    db.add(Flag(session_id=session_id, ts=ts_ms, severity=f["severity"], kind=f["kind"], details=f.get("details"))); db.commit()
                    await ws.send_text(json.dumps({"level": f["severity"], "code": f["kind"], "details": f.get("details",{})}))
    except WebSocketDisconnect: pass
    finally: db.close()

@app.websocket("/api/session/{session_id}/audio")
async def ws_audio(ws: WebSocket, session_id: str):
    token = ws.query_params.get('token')
    if token != get_config().get('auth',{}).get('exam_token'): await ws.close(code=4403); return
    await ws.accept()
    db = SessionLocal()
    st = audio_state(session_id)
    try:
        while True:
            head = await ws.receive_text(); hdr = json.loads(head)
            blob = await ws.receive_bytes()
            import numpy as np
            rate = int(hdr.get("rate",16000))
            pcm = np.frombuffer(blob, dtype=np.int16).astype(np.float32)/32768.0
            res = process_audio_chunk(session_id, pcm, hdr)
            now = time.time()*1000; mode = hdr.get("mode")
            if mode == "calib_enroll":
                s = get_state(db, session_id); s['hardware']['mic_ok'] = True
                if res.get("speech_ms",0) >= 800: s['audio']['enroll_ok'] = True
                calib_update(db, session_id, s)
            if res.get("speech_long"):
                db.add(Flag(session_id=session_id, ts=now, severity='warn', kind='speech_long', details={'dur_ms': st.continuous_speech_ms})); db.commit()
                await ws.send_text(json.dumps({'level':'warn','code':'speech_long'})); st.last_speech_flag_ms = now
            if res.get("conversation_toggles") is not None and res["conversation_toggles"] >= int(get_config().get('audio',{}).get('conversation_warn',6)):
                db.add(Flag(session_id=session_id, ts=now, severity='warn', kind='conversation_pattern', details={'toggles': res["conversation_toggles"]})); db.commit()
                await ws.send_text(json.dumps({'level':'warn','code':'conversation_pattern'}))
            if res.get("conversation_toggles") is not None and res["conversation_toggles"] >= int(get_config().get('audio',{}).get('conversation_high',10)):
                db.add(Flag(session_id=session_id, ts=now, severity='high', kind='conversation_pattern_strong', details={'toggles': res["conversation_toggles"]})); db.commit()
                await ws.send_text(json.dumps({'level':'high','code':'conversation_pattern_strong'}))
            if res.get("other_speaker"):
                db.add(Flag(session_id=session_id, ts=now, severity='high', kind='other_speaker', details={})); db.commit()
                await ws.send_text(json.dumps({'level':'high','code':'other_speaker'}))
            if res.get("other_speaker_strong"):
                db.add(Flag(session_id=session_id, ts=now, severity='high', kind='other_speaker_strong', details={})); db.commit()
                await ws.send_text(json.dumps({'level':'high','code':'other_speaker_strong'}))
            await ws.send_text(json.dumps({"accepted": True}))
    except WebSocketDisconnect: pass
    finally: db.close()

# Problems & Judge0
def _load_problems():
    import json, os
    with open(os.path.join(os.path.dirname(__file__), "problems.json"), "r", encoding="utf-8") as f:
        return json.load(f)
@app.get("/api/problem/{pid}")
def get_problem(pid: str, request: Request = None):
    if not _exam_ok(request) and not _admin_ok(request): return JSONResponse({'error':'unauthorized'}, status_code=401)
    p = _load_problems().get(pid)
    if not p: return JSONResponse({"error":"not found"}, status_code=404)
    return {"id": p["id"], "title": p["title"], "prompt": p["prompt"], "constraints": p["constraints"], "visible_tests": p["visible_tests"]}

LANG_MAP = { "c": 50, "cpp": 54, "java": 62, "python": 71 }
async def _judge0_run(source: str, language: str, stdin: str) -> Dict[str, Any]:
    if os.getenv('USE_FAKE_EXEC','true').lower()=='true':
        if language == "python":
            import subprocess, tempfile, sys
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
                tf.write(source); pth = tf.name
            p = subprocess.run([sys.executable, pth], input=stdin.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=6)
            return {"stdout": p.stdout.decode("utf-8"), "stderr": p.stderr.decode("utf-8"), "status": {"id": 3}}
        return {"stdout":"", "stderr":"FAKE_EXEC enabled for non-python. Set USE_FAKE_EXEC=false", "status":{"id": 6}}
    lang_id = LANG_MAP.get(language, 71)
    async with httpx.AsyncClient() as client:
        sub = {"source_code": source, "language_id": lang_id, "stdin": stdin}
        r = await client.post(f"{JUDGE0_URL}/submissions?base64_encoded=false&wait=true", json=sub, timeout=45)
        r.raise_for_status(); return r.json()

@app.post("/api/submit")
async def submit(payload: dict, request: Request = None):
    if not _exam_ok(request): return JSONResponse({'error':'unauthorized'}, status_code=401)
    session_id = payload.get("session_id", "demo-session")
    pid = payload.get("pid", "longest-bounded-diff")
    language = payload.get("language","python")
    source = payload.get("source","")
    visible_only = bool(payload.get("visible_only", True))
    p = _load_problems().get(pid)
    if not p: return JSONResponse({"error":"problem not found"}, status_code=404)
    tests = p["visible_tests"] if visible_only else (p["visible_tests"] + p["hidden_tests"])
    results = []; pass_ct = 0
    for t in tests:
        out = await _judge0_run(source, language, t["input"])
        stdout = (out.get("stdout") or "").strip()
        ok = (stdout.splitlines()[-1].strip() if stdout else "") == t["output"]
        results.append({"stdin": t["input"], "expected": t["output"], "stdout": stdout, "stderr": out.get("stderr",""), "ok": ok})
        if ok: pass_ct += 1
    db = SessionLocal()
    try:
        last_sub = db.query(Submission).filter_by(session_id=session_id).order_by(Submission.id.desc()).first()
        if last_sub and last_sub.language and last_sub.language != language:
            db.add(Flag(session_id=session_id, ts=time.time()*1000, severity="warn", kind="language_change", details={"from": last_sub.language, "to": language})); db.commit()
        db.add(Submission(session_id=session_id, question_id=pid, language=language, source=source, stdout=str(results), stderr="", status=f"{pass_ct}/{len(tests)}", time_ms=0)); db.commit()
    finally: db.close()
    return {"passed": pass_ct, "total": len(tests), "results": results}

# Report/Admin
@app.get("/api/report/{session_id}")
def report(session_id: str, request: Request = None):
    if not _admin_ok(request) and not _exam_ok(request): return JSONResponse({'error':'unauthorized'}, status_code=401)
    db = SessionLocal()
    try:
        flags = db.query(Flag).filter_by(session_id=session_id).order_by(Flag.ts.asc()).all()
        out = [ {"ts": f.ts, "severity": f.severity, "kind": f.kind, "details": f.details } for f in flags ]
        return {"session_id": session_id, "flags": out}
    finally: db.close()

@app.get("/api/report/{session_id}/csv")
def report_csv(session_id: str, request: Request = None):
    if not _admin_ok(request) and not _exam_ok(request): return JSONResponse({'error':'unauthorized'}, status_code=401)
    db = SessionLocal()
    try:
        flags = db.query(Flag).filter_by(session_id=session_id).order_by(Flag.ts.asc()).all()
        buf = io.StringIO(); w = csv.writer(buf); w.writerow(['ts','severity','kind','details'])
        for f in flags: w.writerow([int(f.ts), f.severity, f.kind, json.dumps(f.details or {})])
        return Response(content=buf.getvalue().encode('utf-8'), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="{session_id}.csv"'})
    finally: db.close()

@app.get("/api/report/{session_id}/pdf")
def report_pdf(session_id: str, request: Request = None):
    if not _admin_ok(request) and not _exam_ok(request): return JSONResponse({'error':'unauthorized'}, status_code=401)
    db = SessionLocal()
    try:
        flags = db.query(Flag).filter_by(session_id=session_id).order_by(Flag.ts.asc()).all()
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=letter); width, height = letter; y = height - 50
        c.setFont("Helvetica-Bold", 14); c.drawString(50, y, f"RT Proctor Report: {session_id}"); y -= 20
        c.setFont("Helvetica", 10)
        for f in flags:
            line = f"{int(f.ts)}  [{f.severity.upper()}]  {f.kind}  {json.dumps(f.details or {})}"
            for chunk in [line[i:i+95] for i in range(0, len(line), 95)]:
                if y < 60: c.showPage(); y = height - 50; c.setFont("Helvetica", 10)
                c.drawString(50, y, chunk); y -= 12
        c.showPage(); c.save(); pdf = buf.getvalue()
        return Response(content=pdf, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{session_id}.pdf"'})
    finally: db.close()

@app.get("/api/admin/sessions")
def admin_sessions(request: Request = None):
    if not _admin_ok(request): return JSONResponse({'error':'unauthorized'}, status_code=401)
    db = SessionLocal()
    try:
        rows = db.query(DBSession).all(); out = []
        for r in rows:
            sc = 0; flags = db.query(Flag).filter_by(session_id=r.session_id).all()
            for f in flags: sc += 3 if f.severity=="high" else (1 if f.severity=="warn" else 0)
            out.append({"session_id": r.session_id, "calibrated": bool(r.calibrated), "started_at": r.started_at, "ended_at": r.ended_at, "flag_count": len(flags), "suspicion": sc})
        return out
    finally: db.close()

@app.post("/api/plagiarism/web")
async def plagiarism_web(payload: dict, request: Request = None):
    if not _admin_ok(request) and not _exam_ok(request): return JSONResponse({'error':'unauthorized'}, status_code=401)
    code = payload.get("code","")
    top = web_like_local_search(code, os.path.join(os.path.dirname(__file__),'..','corpus'))
    return {"top": top}
