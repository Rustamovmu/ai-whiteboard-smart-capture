import type { Point, Detector } from './types'

export const defaultCorners: Point[] = [{ x: 0.08, y: 0.1 }, { x: 0.92, y: 0.1 }, { x: 0.92, y: 0.9 }, { x: 0.08, y: 0.9 }]

export default function BoardOverlay({ points, editing, onChange, detector }: {
  points: Point[]; editing: boolean; onChange: (points: Point[]) => void; detector?: Detector;
}) {
  return <div className="board-overlay">
    <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">
      {!!points.length && <polygon points={points.map(p => `${p.x * 1000},${p.y * 1000}`).join(' ')}
        fill={editing ? 'rgba(202,237,145,.10)' : 'transparent'} stroke={editing ? '#d4f4a5' : '#b6e889'} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeDasharray={editing ? '6 5' : undefined} />}
      {detector?.available && detector.boxes?.map((person, i) => <g key={i}>
        <rect x={person.box[0] * 1000} y={person.box[1] * 1000} width={(person.box[2] - person.box[0]) * 1000}
          height={(person.box[3] - person.box[1]) * 1000} fill="rgba(251,180,100,.08)" stroke="#ffbd7c" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </g>)}
    </svg>
    {detector?.available && detector.boxes?.map((person, i) => <span key={i} className="person-label" style={{ left: `${person.box[0] * 100}%`, top: `${person.box[1] * 100}%` }}>Person · {Math.round(person.confidence * 100)}%</span>)}
    {editing && points.map((point, index) => <button key={index} className="board-corner" aria-label={`Board corner ${index + 1}`}
      style={{ left: `${point.x * 100}%`, top: `${point.y * 100}%` }}
      onPointerDown={event => { event.currentTarget.setPointerCapture(event.pointerId); event.preventDefault() }}
      onPointerMove={event => {
        if (!event.currentTarget.hasPointerCapture(event.pointerId)) return
        const bounds = event.currentTarget.parentElement!.getBoundingClientRect()
        const next = [...points]
        next[index] = { x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)), y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)) }
        onChange(next)
      }} onPointerUp={event => event.currentTarget.releasePointerCapture(event.pointerId)}><span>{index + 1}</span></button>)}
  </div>
}
