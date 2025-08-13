import os, time, base64, io, numpy as np, cv2
from PIL import Image
import mediapipe as mp
from ..config import get_config
from . import ctx as ctx
mp_faces=mp.solutions.face_mesh
FACE=mp_faces.FaceMesh(static_image_mode=False, max_num_faces=2, refine_landmarks=True, min_detection_confidence=0.5, min_tracking_confidence=0.5)
SAVE_DIR="./media/images"; os.makedirs(SAVE_DIR, exist_ok=True)
class VisionState:
    def __init__(self): self.no_face_frames=0; self.gaze_hist=[]; self.blink_hist=[]; self.last_ear_below=False
STATES={}
def get_state(session_id:str)->VisionState:
    st=STATES.get(session_id); 
    if not st: st=VisionState(); STATES[session_id]=st
    return st
def _save_snapshot(img, session_id:str):
    ts=int(time.time()*1000); path=f"{SAVE_DIR}/{session_id}_{ts}.jpg"; cv2.imwrite(path, img); return f"/media/images/{os.path.basename(path)}"
def _to_img(jpeg_b64:str):
    if not jpeg_b64: return None, None, None
    b=base64.b64decode(jpeg_b64.split(',')[-1]); im=Image.open(io.BytesIO(b)).convert('RGB'); arr=np.array(im)[:,:,::-1]; return arr, arr.shape[1], arr.shape[0]
def _pt(lm, idx, w, h):
    p=lm[idx]; return np.array([p.x*w, p.y*h], dtype=np.float64)
LE={'outer':33,'inner':133,'up1':159,'up2':158,'dn1':145,'dn2':153}; RE={'outer':263,'inner':362,'up1':386,'up2':385,'dn1':374,'dn2':380}
L_IRIS=[468,469,470,471]; R_IRIS=[473,474,475,476]
def _ear(lm,w,h,left=True):
    E=LE if left else RE; p1=_pt(lm,E['outer'],w,h); p2=_pt(lm,E['inner'],w,h); up1=_pt(lm,E['up1'],w,h); dn1=_pt(lm,E['dn1'],w,h); up2=_pt(lm,E['up2'],w,h); dn2=_pt(lm,E['dn2'],w,h)
    num=np.linalg.norm(up1-dn1)+np.linalg.norm(up2-dn2); den=max(1e-5,2*np.linalg.norm(p1-p2)); return float(num/den)
def _iris_center(lm,w,h,left=True):
    idxs=L_IRIS if left else R_IRIS; pts=np.array([_pt(lm,i,w,h) for i in idxs],dtype=np.float64); return np.mean(pts,axis=0)
def _gaze_offset(lm,w,h,left=True):
    E=LE if left else RE; outer=_pt(lm,E['outer'],w,h); inner=_pt(lm,E['inner'],w,h); up=_pt(lm,E['up1'],w,h); dn=_pt(lm,E['dn1'],w,h)
    center=(outer+inner)/2.0; iris=_iris_center(lm,w,h,left); width=max(1e-5,np.linalg.norm(outer-inner)); height=max(1e-5,np.linalg.norm(up-dn)); off=(iris-center)/np.array([width,height]); return float(off[0]), float(off[1])
def face_and_gaze(session_id:str, jpeg_b64:str, phase:str='', prompt:str=''):
    img,w,h=_to_img(jpeg_b64); 
    if img is None: return []
    flags=[]; vs=get_state(session_id); res=FACE.process(cv2.cvtColor(img,cv2.COLOR_BGR2RGB)); cfgv=get_config().get('vision',{})
    if not res.multi_face_landmarks:
        vs.no_face_frames+=1
        if vs.no_face_frames>=15: flags.append({'severity':'warn','kind':'face_absent','details':{'frames':vs.no_face_frames}})
        return flags
    vs.no_face_frames=0; lm=res.multi_face_landmarks[0].landmark
    ear_l=_ear(lm,w,h,True); ear_r=_ear(lm,w,h,False); ear=(ear_l+ear_r)/2.0; ear_th=float(cfgv.get('blink_ear',0.21))
    prev=vs.last_ear_below; vs.last_ear_below=(ear<ear_th); now_ms=int(time.time()*1000)
    if vs.last_ear_below and not prev: vs.blink_hist.append(now_ms); vs.blink_hist=[t for t in vs.blink_hist if now_ms-t<=90000]
    gx_l,gy_l=_gaze_offset(lm,w,h,True); gx_r,gy_r=_gaze_offset(lm,w,h,False); gx=(gx_l+gx_r)/2.0; gy=(gy_l+gy_r)/2.0
    off=(abs(gx)>float(cfgv.get('gaze_off_x',0.35))) or (abs(gy)>float(cfgv.get('gaze_off_y',0.28)))
    vs.gaze_hist.append((now_ms,bool(off))); vs.gaze_hist=[p for p in vs.gaze_hist if now_ms-p[0]<=30000]; off_ratio = (sum(1 for _,o in vs.gaze_hist if o)/max(1,len(vs.gaze_hist))) if vs.gaze_hist else 0.0
    if len(vs.blink_hist)>=2: dur=max(1,vs.blink_hist[-1]-vs.blink_hist[0]); bl_pm=len(vs.blink_hist)*(60000/dur)
    else: bl_pm=0.0
    if off_ratio>=float(cfgv.get('gaze_high_ratio',0.6)) and bl_pm<=float(cfgv.get('blink_low_per_min',5.0)):
        snap=_save_snapshot(img,session_id); flags.append({'severity':'high','kind':'gaze_off_strong','details':{'off_ratio':round(off_ratio,2),'blinks_pm':round(bl_pm,1),'snapshot':snap}})
    elif off_ratio>=float(cfgv.get('gaze_warn_ratio',0.5)):
        flags.append({'severity':'warn','kind':'gaze_off','details':{'off_ratio':round(off_ratio,2)}})
    focus,_=ctx.get_focus(session_id); lk=ctx.last_key_ts(session_id); typing_recent=(now_ms-lk)<=3000
    if off_ratio>=float(cfgv.get('gaze_warn_ratio',0.5)) and (typing_recent or focus in ('editor','problem')):
        sev='high' if off_ratio>=float(cfgv.get('gaze_high_ratio',0.6)) else 'warn'
        flags.append({'severity':sev,'kind':'gaze_off_aoi','details':{'focus':focus,'typing_recent':typing_recent,'off_ratio':round(off_ratio,2)}})
    return flags
