import time
class Ctx:
    def __init__(self):
        self.last_focus={}
        self.last_key={}
        self.aoi={} # session_id -> rects
CTX=Ctx()
def set_focus(session_id:str, panel:str): CTX.last_focus[session_id]=(panel, time.time()*1000)
def get_focus(session_id:str): return CTX.last_focus.get(session_id, ('other',0))
def mark_key(session_id:str): CTX.last_key[session_id]=time.time()*1000
def last_key_ts(session_id:str): return CTX.last_key.get(session_id,0)
def set_aoi(session_id:str, kind:str, rect:dict): CTX.aoi.setdefault(session_id, {})[kind]=rect
def get_aoi(session_id:str): return CTX.aoi.get(session_id, {})
