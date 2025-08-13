import React from 'react'
import { Link, Outlet } from 'react-router-dom'
function TokenGate(){const [tok,setTok]=React.useState(localStorage.getItem('exam_token')||'');React.useEffect(()=>{if(!tok){const t=prompt('Enter exam token (default: EXAM123)')||'';if(t){localStorage.setItem('exam_token',t);setTok(t)}}},[tok]);return null}
export default function App(){return(<div><TokenGate/><div className='topbar'><b>RT Proctor</b><Link to='/calibration'>Calibration</Link><Link to='/problem'>Exam</Link><Link to='/admin'>Admin</Link></div><div className='container'><Outlet/></div></div>)}
