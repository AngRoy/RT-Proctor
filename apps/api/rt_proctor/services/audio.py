import time, numpy as np, webrtcvad
from ..config import get_config
try:
    from python_speech_features import mfcc
except Exception:
    mfcc = None

class AudioState:
    def __init__(self):
        self.enroll_pitch=None; self.enroll_energy=None; self.continuous_speech_ms=0.0
        self.last_speech_flag_ms=0.0; self.last_chunk_speech=False; self.toggle_count=0; self.toggle_window_start_ms=0.0
        self.other_speaker_ms=0.0; self.enroll_embed=None; self.embed_window=[]
STATES={}
def audio_state(session_id:str)->AudioState:
    st=STATES.get(session_id)
    if not st: st=AudioState(); STATES[session_id]=st
    return st
vad = webrtcvad.Vad(2)
def _pitch_energy(pcm: np.ndarray, rate:int):
    if pcm.size==0: return 0.0,0.0
    x=pcm.astype(np.float32); energy=float(np.sqrt(np.mean(x*x))+1e-6)
    spec=np.fft.rfft(x); freqs=np.fft.rfftfreq(len(x),d=1.0/rate); mag=np.abs(spec); pitch=float(np.sum(freqs*mag)/max(1e-6,np.sum(mag)))
    return pitch, energy
def _embed(pcm: np.ndarray, rate:int):
    if mfcc is None or pcm.size==0: return None
    try:
        feats=mfcc(pcm.astype(np.float32), samplerate=rate, winlen=0.025, winstep=0.010, numcep=20, nfilt=26, nfft=512, preemph=0.97)
        if feats.size==0: return None
        v=feats.mean(axis=0).astype(np.float32); v/= (np.linalg.norm(v)+1e-9); return v
    except Exception: return None
def _cosine(a: np.ndarray, b: np.ndarray):
    if a is None or b is None: return 1.0
    na=float(np.linalg.norm(a)); nb=float(np.linalg.norm(b))
    if na==0 or nb==0: return 1.0
    return 1.0 - float(np.dot(a,b)/(na*nb))
def process_audio_chunk(session_id:str, pcm: np.ndarray, hdr: dict):
    st=audio_state(session_id); mode=hdr.get('mode','exam'); ms=int(hdr.get('ms',20)); rate=int(hdr.get('rate',16000))
    has_speech = np.mean(np.abs(pcm))>0.01
    try:
        if rate==16000:
            raw=(pcm*32767.0).clip(-32768,32767).astype(np.int16).tobytes(); has_speech = vad.is_speech(raw, rate)
    except Exception: pass
    pitch,energy=_pitch_energy(pcm, rate)
    now=int(time.time()*1000)
    if has_speech and not st.last_chunk_speech:
        if now-st.toggle_window_start_ms>30000: st.toggle_window_start_ms=now; st.toggle_count=0
        st.toggle_count+=1
    st.last_chunk_speech=has_speech
    emb=_embed(pcm, rate)
    if mode=='calib_enroll':
        if st.enroll_pitch is None: st.enroll_pitch=pitch
        else: st.enroll_pitch=0.9*st.enroll_pitch+0.1*pitch
        if st.enroll_energy is None: st.enroll_energy=energy
        else: st.enroll_energy=0.9*st.enroll_energy+0.1*energy
        if emb is not None: st.enroll_embed = 0.9*st.enroll_embed + 0.1*emb if st.enroll_embed is not None else emb
    else:
        if emb is not None:
            st.embed_window.append(emb); 
            if len(st.embed_window)>30: st.embed_window.pop(0)
    if has_speech: st.continuous_speech_ms+=ms
    else: st.continuous_speech_ms=max(0.0, st.continuous_speech_ms - ms*0.6)
    long = st.continuous_speech_ms>=15000 and (now - st.last_speech_flag_ms>8000)
    other=False; other_strong=False
    if st.enroll_pitch and st.enroll_energy and has_speech:
        p_dev=abs(pitch-st.enroll_pitch)/max(1.0,st.enroll_pitch); e_dev=abs(energy-st.enroll_energy)/max(1e-3,st.enroll_energy)
        if p_dev>0.35 and e_dev>0.35: st.other_speaker_ms+=ms
        else: st.other_speaker_ms=max(0.0, st.other_speaker_ms - ms*0.3)
        if st.other_speaker_ms>3500: other=True; st.other_speaker_ms=0.0
    thr=float(get_config().get('audio',{}).get('other_speaker_cosine',0.35))
    if st.enroll_embed is not None and len(st.embed_window)>=5 and has_speech:
        win=np.mean(np.stack(st.embed_window[-5:],axis=0),axis=0); win/= (np.linalg.norm(win)+1e-9); cd=_cosine(st.enroll_embed, win)
        if cd>=thr: other_strong=True
    return {"speech_ms":int(st.continuous_speech_ms),"energy":float(energy),"conversation_toggles":st.toggle_count,"speech_long":long,"other_speaker":other,"other_speaker_strong":other_strong}
