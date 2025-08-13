import time
from .config import get_config
IDLE_MS_TH = int(get_config().get('keystrokes',{}).get('idle_ms',4000))
BURST_WINDOW_MS = int(get_config().get('keystrokes',{}).get('burst_window_ms',3500))
BURST_KEYS_TH = int(get_config().get('keystrokes',{}).get('burst_keys',25))
MASS_DELETE_TH = int(get_config().get('keystrokes',{}).get('mass_delete',25))

class KeyState:
    def __init__(self):
        self.last_key_ts=0; self.window_keys=[]; self.delete_count=0; self.delete_since=0
        self.first_ts=0; self.key_count=0; self.baseline_keys_per_min=None; self.baseline_ready=False
STATES={}
def get_state(session_id:str)->KeyState:
    st=STATES.get(session_id)
    if not st: st=KeyState(); STATES[session_id]=st
    return st
def process_keys(session_id:str, etype:str, data:dict):
    now=int(time.time()*1000); ks=get_state(session_id); ev=[]
    if etype=='key':
        if ks.first_ts==0: ks.first_ts=now
        ks.key_count+=1; elapsed=max(1, now-ks.first_ts)
        if not ks.baseline_ready and (elapsed>=120000 or ks.key_count>=200):
            ks.baseline_keys_per_min= ks.key_count * (60000/elapsed); ks.baseline_ready=True
        if data.get('key') in ['Backspace','Delete']:
            if ks.delete_since==0: ks.delete_since=now
            ks.delete_count+=1
        else:
            ks.delete_since=0; ks.delete_count=0
        ks.window_keys.append(now); ks.window_keys=[t for t in ks.window_keys if now-t<=BURST_WINDOW_MS]
        if ks.last_key_ts==0: ks.last_key_ts=now; return []
        idle = now-ks.last_key_ts; ks.last_key_ts=now
        thr=BURST_KEYS_TH
        if ks.baseline_ready:
            thr=max(BURST_KEYS_TH, int((ks.baseline_keys_per_min or 30) * (BURST_WINDOW_MS/60000.0) * 2.5))
        if idle>=IDLE_MS_TH and len(ks.window_keys)>=thr:
            ev.append(('high','burst_after_idle', {'idle_ms':idle,'keys':len(ks.window_keys),'thr':thr,'baseline_kpm':ks.baseline_keys_per_min}))
        if ks.delete_count>=MASS_DELETE_TH and ks.delete_since and (now-ks.delete_since)<=5000:
            ev.append(('warn','mass_delete', {'count': ks.delete_count}))
    return ev
