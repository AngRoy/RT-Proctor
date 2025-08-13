from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session as DB
from .models import Session as DBSession
DEFAULT = { "hardware":{"camera_ok":False,"mic_ok":False,"no_headphones":True}, "audio":{"silence_ok":False,"enroll_ok":False}, "video":{"face_seen":False,"CENTER":False,"LEFT":False,"RIGHT":False,"UP":False,"DOWN":False} }
def _merge(a:Dict[str,Any], b:Dict[str,Any]):
    for k,v in b.items():
        if isinstance(v,dict): a[k]=_merge(a.get(k,{}), v)
        else: a[k]=v
    return a
def get_state(db:DB, session_id:str)->Dict[str,Any]:
    row=db.query(DBSession).filter_by(session_id=session_id).first()
    if not row: row=DBSession(session_id=session_id, calibrated=0, calib_json=DEFAULT.copy()); db.add(row); db.commit()
    merged=DEFAULT.copy(); _merge(merged, row.calib_json or {}); row.calib_json=merged; db.commit(); return merged
def update(db:DB, session_id:str, patch:Dict[str,Any]):
    row=db.query(DBSession).filter_by(session_id=session_id).first()
    if not row: row=DBSession(session_id=session_id, calib_json=DEFAULT.copy()); db.add(row); db.commit()
    merged=DEFAULT.copy(); _merge(merged, row.calib_json or {}); _merge(merged, patch); row.calib_json=merged; db.commit(); return merged
def check_ready(state:Dict[str,Any])->Tuple[bool,list]:
    miss=[]; hw,au,vi=state["hardware"],state["audio"],state["video"]
    if not hw["camera_ok"]: miss.append("camera_ok")
    if not hw["mic_ok"]: miss.append("mic_ok")
    if not hw["no_headphones"]: miss.append("no_headphones")
    if not vi["face_seen"]: miss.append("face_seen")
    for p in ["CENTER","LEFT","RIGHT","UP","DOWN"]:
        if not vi[p]: miss.append(f"pose_{p.lower()}")
    if not au["enroll_ok"]: miss.append("audio_enroll")
    return (len(miss)==0), miss
