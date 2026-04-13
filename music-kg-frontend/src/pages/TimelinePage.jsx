import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
  AreaChart, Area
} from 'recharts'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'

import { getTimeline, getGenreEvolution } from '../api'
import { PageSkeleton } from '../components/common/LoadingSkeleton'
import { hashColor, formatNumber } from '../utils/helpers'

const GENRES   = ['pop','rap','rock','latin','r&b','edm']
const FEATURES = ['avg_energy','avg_danceability','avg_valence']
const FEAT_COLORS = { avg_energy: '#e91e8c', avg_danceability: '#00d4ff', avg_valence: '#f59e0b' }
const FEAT_LABELS = { avg_energy: 'Energy', avg_danceability: 'Danceability', avg_valence: 'Valence' }

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload || {}
  return (
    <div className="bg-bg-card border border-border-col rounded-card p-3 text-xs min-w-40">
      <p className="font-bold text-text-primary mb-2">{label}</p>
      {payload.map(p => (
        <div key={p.name} className="flex justify-between gap-4 mb-1">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="text-text-secondary font-mono">{typeof p.value === 'number' ? p.value.toFixed ? p.value.toFixed(3) : p.value : p.value}</span>
        </div>
      ))}
      {d.top_genre && <p className="mt-2 text-text-muted">Top genre: <span className="text-accent">{d.top_genre}</span></p>}
      {d.top_tracks?.length > 0 && (
        <div className="mt-2 pt-2 border-t border-border-col">
          {d.top_tracks.slice(0,3).map((t,i) => (
            <p key={i} className="text-text-muted truncate">{t.name} — {t.artist}</p>
          ))}
        </div>
      )}
    </div>
  )
}

export default function TimelinePage() {
  const [searchParams] = useSearchParams()

  const [timeline, setTimeline]   = useState([])
  const [evolution, setEvolution] = useState([])
  const [loading, setLoading]     = useState(true)
  const [evoLoading, setEvoLoading] = useState(false)

  const [startYear, setStartYear]   = useState(parseInt(searchParams.get('start_year')) || 1960)
  const [endYear, setEndYear]       = useState(parseInt(searchParams.get('end_year'))   || 2024)
  const [selFeature, setSelFeature] = useState('avg_energy')
  const [selGenre, setSelGenre]     = useState('')

  useEffect(() => {
    setLoading(true)
    getTimeline({ start_year: startYear, end_year: endYear })
      .then(r => setTimeline(r.data?.timeline || []))
      .catch(() => toast.error('Failed to load timeline'))
      .finally(() => setLoading(false))
  }, [startYear, endYear])

  useEffect(() => {
    if (!selGenre) return
    setEvoLoading(true)
    getGenreEvolution(selGenre)
      .then(r => setEvolution(r.data?.evolution || []))
      .catch(() => toast.error('Failed to load genre evolution'))
      .finally(() => setEvoLoading(false))
  }, [selGenre])

  // Compute highlights
  const highlights = timeline.length ? {
    mostEnergetic: timeline.reduce((a, b) => (a.avg_energy || 0) > (b.avg_energy || 0) ? a : b),
    mostDanceable: timeline.reduce((a, b) => (a.avg_danceability || 0) > (b.avg_danceability || 0) ? a : b),
    peakTracks:    timeline.reduce((a, b) => (a.track_count || 0) > (b.track_count || 0) ? a : b),
  } : null

  if (loading) return <PageSkeleton />

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <motion.h1 className="text-3xl font-extrabold text-text-primary mb-6"
        initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        Music Timeline
      </motion.h1>

      {/* Controls */}
      <div className="bg-bg-card border border-border-col rounded-card p-4 mb-6 flex flex-wrap gap-6 items-center">
        <div>
          <p className="text-xs text-text-muted mb-1">Year Range: {startYear} — {endYear}</p>
          <div className="flex gap-2">
            <input type="range" min={1950} max={2023} step={1} value={startYear}
              onChange={e => setStartYear(parseInt(e.target.value))}
              className="w-32 accent-accent" />
            <input type="range" min={1951} max={2024} step={1} value={endYear}
              onChange={e => setEndYear(parseInt(e.target.value))}
              className="w-32 accent-accent" />
          </div>
        </div>

        <div>
          <p className="text-xs text-text-muted mb-1">Audio Feature</p>
          <div className="flex gap-1">
            {FEATURES.map(f => (
              <button key={f} onClick={() => setSelFeature(f)}
                className={`px-3 py-1 text-xs rounded-pill border transition-all ${
                  selFeature === f
                    ? 'border-accent text-accent bg-accent/10'
                    : 'border-border-col text-text-secondary hover:border-text-muted'
                }`}>
                {FEAT_LABELS[f]}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main composed chart */}
      <div className="bg-bg-card border border-border-col rounded-card p-5 mb-8">
        <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-5">
          Track Volume & {FEAT_LABELS[selFeature]} Over Time
        </h2>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={timeline}>
            <CartesianGrid strokeDasharray="3 3" stroke="#282828" vertical={false} />
            <XAxis dataKey="year" tick={{ fill: '#535353', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="left"  tick={{ fill: '#535353', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="right" orientation="right" tick={{ fill: '#535353', fontSize: 11 }} axisLine={false} tickLine={false} domain={[0, 1]} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ color: '#b3b3b3', fontSize: 12 }} />
            <Bar yAxisId="left" dataKey="track_count" name="Tracks" fill="#282828" radius={[2,2,0,0]} />
            <Line yAxisId="right" type="monotone" dataKey={selFeature}
              name={FEAT_LABELS[selFeature]} stroke={FEAT_COLORS[selFeature]}
              strokeWidth={2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
        {/* Genre evolution */}
        <div className="lg:col-span-3 bg-bg-card border border-border-col rounded-card p-5">
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider">Genre Evolution by Decade</h2>
            <select value={selGenre} onChange={e => setSelGenre(e.target.value)}
              className="bg-bg-hover border border-border-col rounded text-xs text-text-secondary px-2 py-1 outline-none">
              <option value="">Select genre…</option>
              {GENRES.map(g => <option key={g} value={g}>{g}</option>)}
            </select>
          </div>
          {evolution.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={evolution}>
                <CartesianGrid strokeDasharray="3 3" stroke="#282828" vertical={false} />
                <XAxis dataKey="decade" tick={{ fill: '#535353', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 1]} tick={{ fill: '#535353', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: '#1a1a1a', border: '1px solid #282828', borderRadius: 8, fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12, color: '#b3b3b3' }} />
                <Area type="monotone" dataKey="avg_energy"       name="Energy"       stroke="#e91e8c" fill="#e91e8c" fillOpacity={0.15} strokeWidth={2} />
                <Area type="monotone" dataKey="avg_danceability" name="Danceability" stroke="#00d4ff" fill="#00d4ff" fillOpacity={0.15} strokeWidth={2} />
                <Area type="monotone" dataKey="avg_valence"      name="Valence"      stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.15} strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-40 text-text-muted text-sm">
              Select a genre to see its evolution
            </div>
          )}
        </div>

        {/* Highlights sidebar */}
        {highlights && (
          <div className="bg-bg-card border border-border-col rounded-card p-5 space-y-4">
            <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider">Highlights</h2>
            <div>
              <p className="text-xs text-text-muted mb-1">⚡ Most Energetic Year</p>
              <p className="text-2xl font-bold text-accent">{highlights.mostEnergetic.year}</p>
              <p className="text-xs text-text-muted">{highlights.mostEnergetic.avg_energy?.toFixed(3)}</p>
            </div>
            <div>
              <p className="text-xs text-text-muted mb-1">💃 Most Danceable Year</p>
              <p className="text-2xl font-bold" style={{ color: '#00d4ff' }}>{highlights.mostDanceable.year}</p>
              <p className="text-xs text-text-muted">{highlights.mostDanceable.avg_danceability?.toFixed(3)}</p>
            </div>
            <div>
              <p className="text-xs text-text-muted mb-1">🎵 Peak Production Year</p>
              <p className="text-2xl font-bold" style={{ color: '#f59e0b' }}>{highlights.peakTracks.year}</p>
              <p className="text-xs text-text-muted">{formatNumber(highlights.peakTracks.track_count)} tracks</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
