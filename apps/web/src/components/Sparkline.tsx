import React from 'react'
export default function Sparkline({bins}:{bins:number[]}){const w=240,h=40,max=Math.max(1,...bins);const points=bins.map((b,i)=>[(i/(bins.length-1||1))*w,h-(b/max)*h]);const d=points.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ');return <svg width={w} height={h}><path d={d} fill='none' stroke='currentColor' strokeWidth='2'/></svg>}
