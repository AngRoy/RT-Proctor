import React, { useEffect, useRef, useState } from 'react'
import CodeEditor from '../components/Editor'

function beep(pattern:number[]=[300]){
  try{
    const a = new (window.AudioContext|| (window as any).webkitAudioContext)()
    const o = a.createOscillator(); const g = a.createGain(); o.type='sine'; o.frequency.value=880; o.connect(g).connect(a.destination); g.gain.value=0.001; o.start()
    let t=a.currentTime
    pattern.forEach((dur)=>{ g.gain.exponentialRampToValueAtTime(0.25, t+0.02); g.gain.exponentialRampToValueAtTime(0.001, t+dur/1000.0); t += dur/1000.0 })
    o.stop(t)
  }catch{}
}

export default function ProblemExam(){
  const sessionId = 'demo-session'
  const [lang, setLang] = useState<'python'|'cpp'|'java'|'c'>('python')
  const [code, setCode] = useState('')
  const [problem, setProblem] = useState<any>(null)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [flags, setFlags] = useState<any[]>([])
  const eventsWS = useRef<any>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const camStream = useRef<MediaStream|null>(null)
  const [showFsModal, setShowFsModal] = useState(false)

  useEffect(()=>{ fetch('/api/problem/longest-bounded-diff', { headers: { 'x-exam': localStorage.getItem('exam_token')||'' } }).then(r=>r.json()).then(setProblem) },[])

  useEffect(()=>{
    const url = `ws://`+location.host+`/api/session/${sessionId}/events?token=${localStorage.getItem('exam_token')||''}`
    const ws = new WebSocket(url); (ws as any).sendJSON = (obj:any)=> ws.readyState===1 && ws.send(JSON.stringify(obj)); eventsWS.current = ws
    ws.onmessage = (ev:any)=>{ try{ const m=JSON.parse(ev.data); if(m.level) setFlags((f:any[])=> [...f, {ts: Date.now(), severity: m.level, kind: m.code, details: m.details||{}}]) }catch{} }
    const onVis = ()=> (ws as any).sendJSON({ t:'tab', state: document.visibilityState==='visible' ? 'focus':'blur' })
    document.addEventListener('visibilitychange', onVis)

    document.addEventListener('fullscreenchange', ()=>{
      const inFs = !!(document.fullscreenElement || (document as any).webkitFullscreenElement || (document as any).msFullscreenElement)
      ;(ws as any).sendJSON({ t:'fs', state: inFs ? 'enter' : 'exit' })
      if (!inFs){ setShowFsModal(true); beep([200,120,200,120,300]) } else { setShowFsModal(false) }
    })
    document.documentElement.requestFullscreen?.()

    const checkFsAndSignal = ()=>{
      const inFs = !!(document.fullscreenElement || (document as any).webkitFullscreenElement || (document as any).msFullscreenElement)
      if (!inFs){ setShowFsModal(true); (ws as any).sendJSON({ t:'fs', state:'exit' }); beep([200,120,200,120,300]) } else { setShowFsModal(false); (ws as any).sendJSON({ t:'fs', state:'enter' }) }
    }
    setTimeout(checkFsAndSignal, 100); const fsTick = setInterval(checkFsAndSignal, 3000)

    ;(async ()=>{
      try{
        camStream.current = await navigator.mediaDevices.getUserMedia({ video: true, audio:false })
        if (videoRef.current){ videoRef.current.srcObject = camStream.current; await videoRef.current.play() }
        const can = document.createElement('canvas'); const g = can.getContext('2d')!
        const tick = ()=>{
          const v = videoRef.current; if (!v || v.videoWidth===0){ requestAnimationFrame(tick); return }
          can.width = v.videoWidth; can.height = v.videoHeight; g.drawImage(v,0,0)
          const jpegB64 = can.toDataURL('image/jpeg', 0.6)
          ;(ws as any).sendJSON({ t:'frame', phase:'exam', jpegB64 })
          requestAnimationFrame(tick)
        }; requestAnimationFrame(tick)
      }catch{}
    })()

    const sendAoi = ()=>{
      const pe = document.getElementById('pane-editor')?.getBoundingClientRect()
      const pp = document.getElementById('pane-problem')?.getBoundingClientRect()
      if (pe) (ws as any).sendJSON({ t:'aoi', kind:'editor', rect:{x:pe.x,y:pe.y,w:pe.width,h:pe.height} })
      if (pp) (ws as any).sendJSON({ t:'aoi', kind:'problem', rect:{x:pp.x,y:pp.y,w:pp.width,h:pp.height} })
    }
    window.addEventListener('resize', sendAoi); const t=setInterval(sendAoi, 3000); setTimeout(sendAoi, 500)

    return ()=>{ document.removeEventListener('visibilitychange', onVis); clearInterval(fsTick); window.removeEventListener('resize', sendAoi); ws.close() }
  },[])

  function onEditorEvent(t:string, data?:any){ (eventsWS.current as any)?.sendJSON({ t, ...(data||{}) }) }

  async function runVisible(){ setRunning(true); const r=await fetch('/api/submit',{method:'POST',headers:{'Content-Type':'application/json','x-exam':localStorage.getItem('exam_token')||''},body:JSON.stringify({session_id:sessionId,pid:'longest-bounded-diff',language:lang,source:code,visible_only:true})}); const js=await r.json(); setResult(js); setRunning(false) }
  async function runAll(){ setRunning(true); const r=await fetch('/api/submit',{method:'POST',headers:{'Content-Type':'application/json','x-exam':localStorage.getItem('exam_token')||''},body:JSON.stringify({session_id:sessionId,pid:'longest-bounded-diff',language:lang,source:code,visible_only:false})}); const js=await r.json(); setResult(js); setRunning(false); location.href='/report/'+sessionId }

  return <div className='panes'>
    <section className='pane problem' id='pane-problem' onMouseEnter={()=> (eventsWS.current as any)?.sendJSON({ t:'ui_focus', panel:'problem' })} onScroll={()=> (eventsWS.current as any)?.sendJSON({ t:'ui_focus', panel:'problem' })}>
      <h3>{problem?.title}</h3>
      <pre>{problem?.prompt}</pre>
      <div className='card'><h4>Visible Test Cases (input → expected output)</h4><ul>{(problem?.visible_tests||[]).map((t:any,i:number)=>(<li key={i}><code>{t.input.replace(/\n/g,' / ')}</code> → <b>{t.output}</b></li>))}</ul></div>
    </section>
    <section className='pane'>
      <div style={{display:'flex', gap:8, marginBottom:8}}>
        <select value={lang} onChange={e=> setLang(e.target.value as any)}><option value='python'>Python</option><option value='cpp'>C++</option><option value='c'>C</option><option value='java'>Java</option></select>
        <button className='btn' disabled={running} onClick={runVisible}>Run (visible tests)</button>
        <button className='btn' disabled={running} onClick={runAll}>Submit (all)</button>
      </div>
      <div id='pane-editor' style={{height:'70%'}}><CodeEditor language={lang} value={code} onChange={setCode} onEditorEvent={onEditorEvent}/></div>
      <div className='card' style={{marginTop:8}}><h4>Results</h4><pre style={{whiteSpace:'pre-wrap'}}>{result? JSON.stringify(result,null,2): '—'}</pre></div>
    </section>
    <section className='pane'><video ref={videoRef} muted playsInline style={{width:'100%',borderRadius:8}}/><h4>Flags</h4><div className='card' style={{maxHeight:'40vh',overflow:'auto'}}>{flags.map((f,i)=>(<div key={i} className='flag'><b className={'sev '+f.severity}>{f.severity.toUpperCase()}</b> • {f.kind}</div>))}</div></section>
    {showFsModal && <div className='modal'><div className='panel'><h3>Fullscreen is required</h3><p>Please return to fullscreen to continue. This event is recorded.</p><button className='btn' onClick={()=> document.documentElement.requestFullscreen?.()}>Go fullscreen</button></div></div>}
  </div>
}
