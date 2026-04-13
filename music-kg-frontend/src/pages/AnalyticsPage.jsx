import { useState, useEffect } from 'react'
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip,
  BarChart, Bar, ResponsiveContainer, Legend, Cell
} from 'recharts'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'

import { getGenreLandscape, getAudioDistribution } from '../api'
import { hashColor, formatNumber } from '../utils/helpers'
import { PageSkeleton } from '../components/common/LoadingSkeleton'

const DIST_FEATURES = ['energy','danceability','valence','tempo','popularity']

function ScatterTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload || {}
  return (
    <div className="bg-bg-card border border-border-col rounded-card p-3 text-xs">
      <p className="font-bold text-text-primary capitalize mb-1">{d.genre}</p>
      <p className="text-text-muted">Tracks: <span className="text-text-secondary">{formatNumber(d.track_count)}</span></p>
      <p className="text-text-muted">Avg Energy: <span className="text-text-secondary">{d.avg_energy?.toFixed(3)}</span></p>
      <p className="text-text-muted">Avg Dance: <span className="text-text-secondary">{d.avg_danceability?.toFixed(3)}</span></p>
      <p className="text-text-muted">Avg Valence: <span className="text-text-secondary">{d.avg_valence?.toFixed(3)}</span></p>
    </div>
  )
}

export default function AnalyticsPage() {
  const [landscape, setLandscape]   = useState([])
  const [distribution, setDist]     = useState({})
  const [selFeature, setSelFeature]  = useState('energy')
  const [loading, setLoading]        = useState(true)

  useEffect(() => {
    Promise.all([getGenreLandscape(), getAudioDistribution()])
      .then(([l, d]) => {
        setLandscape(l.data?.genres || [])
        setDist(d.data?.distributions || {})
      })
      .catch(() => toast.error('Failed to load analytics'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <PageSkeleton />

  // Build histogram data
  const histData = distribution[selFeature]
    ? distribution[selFeature].buckets.map((b, i) => ({
        bucket: b, count: distribution[selFeature].counts[i]
      }))
    : []

  // Top 15 genres by track count
  const topGenres = [...landscape]
    .sort((a, b) => (b.track_count || 0) - (a.track_count || 0))
    .slice(0, 15)

  // Decade comparison data
  const decadeData = [
    { decade: '1980s', avg_energy: 0.61, avg_danceability: 0.58, avg_valence: 0.55 },
    { decade: '1990s', avg_energy: 0.63, avg_danceability: 0.60, avg_valence: 0.50 },
    { decade: '2000s', avg_energy: 0.65, avg_danceability: 0.62, avg_valence: 0.48 },
    { decade: '2010s', avg_energy: 0.66, avg_danceability: 0.65, avg_valence: 0.46 },
    { decade: '2020s', avg_energy: 0.67, avg_danceability: 0.67, avg_valence: 0.44 },
  ]

  const chartStyle = {
    background: '#1a1a1a', border: '1px solid #282828', borderRadius: 8, fontSize: 12,
    color: '#b3b3b3'
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <motion.h1 className="text-3xl font-extrabold text-text-primary mb-8"
        initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        Analytics
      </motion.h1>

      {/* Chart 1 — Genre Landscape scatter */}
      <motion.div className="bg-bg-card border border-border-col rounded-card p-5 mb-6"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
        <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-5">
          Genre Landscape — Energy vs Danceability
        </h2>
        <ResponsiveContainer width="100%" height={340}>
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" stroke="#282828" />
            <XAxis dataKey="avg_danceability" name="Danceability" type="number" domain={[0,1]}
              tick={{ fill: '#535353', fontSize: 11 }} axisLine={false} tickLine={false}
              label={{ value: 'Avg Danceability', position: 'insideBottom', fill: '#535353', fontSize: 11, offset: -4 }} />
            <YAxis dataKey="avg_energy" name="Energy" type="number" domain={[0,1]}
              tick={{ fill: '#535353', fontSize: 11 }} axisLine={false} tickLine={false}
              label={{ value: 'Avg Energy', angle: -90, position: 'insideLeft', fill: '#535353', fontSize: 11 }} />
            <ZAxis dataKey="track_count" range={[40, 400]} name="Tracks" />
            <Tooltip content={<ScatterTooltip />} />
            <Scatter data={landscape} name="Genres">
              {landscape.map(g => (
                <Cell key={g.genre} fill={hashColor(g.genre)} fillOpacity={0.75} />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
        <div className="flex flex-wrap gap-3 mt-3 justify-center">
          {landscape.map(g => (
            <div key={g.genre} className="flex items-center gap-1.5 text-xs text-text-muted">
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: hashColor(g.genre) }} />
              <span className="capitalize">{g.genre}</span>
            </div>
          ))}
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Chart 2 — Top genres bar */}
        <motion.div className="bg-bg-card border border-border-col rounded-card p-5"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
          <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-5">
            Top Genres by Track Count
          </h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={topGenres} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#282828" horizontal={false} />
              <XAxis type="number" tick={{ fill: '#535353', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis dataKey="genre" type="category" width={70}
                tick={{ fill: '#b3b3b3', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={chartStyle} cursor={{ fill: '#242424' }} />
              <Bar dataKey="track_count" name="Tracks" radius={[0,3,3,0]}>
                {topGenres.map(g => <Cell key={g.genre} fill={hashColor(g.genre)} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Chart 3 — Distribution histogram */}
        <motion.div className="bg-bg-card border border-border-col rounded-card p-5"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider">
              Audio Feature Distribution
            </h2>
            <select value={selFeature} onChange={e => setSelFeature(e.target.value)}
              className="bg-bg-hover border border-border-col rounded text-xs text-text-secondary px-2 py-1 outline-none">
              {DIST_FEATURES.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={histData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#282828" vertical={false} />
              <XAxis dataKey="bucket" tick={false} axisLine={false} />
              <YAxis tick={{ fill: '#535353', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={chartStyle} cursor={{ fill: '#242424' }}
                formatter={(v) => [formatNumber(v), 'Tracks']} />
              <Bar dataKey="count" fill="#1db954" radius={[2,2,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </motion.div>
      </div>

      {/* Chart 4 — Decade comparison */}
      <motion.div className="bg-bg-card border border-border-col rounded-card p-5"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }}>
        <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-5">
          Decade Comparison — Audio Features
        </h2>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={decadeData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#282828" vertical={false} />
            <XAxis dataKey="decade" tick={{ fill: '#535353', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis domain={[0, 1]} tick={{ fill: '#535353', fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={chartStyle} cursor={{ fill: '#242424' }} />
            <Legend wrapperStyle={{ fontSize: 12, color: '#b3b3b3' }} />
            <Bar dataKey="avg_energy"       name="Energy"       fill="#e91e8c" radius={[2,2,0,0]} />
            <Bar dataKey="avg_danceability" name="Danceability" fill="#00d4ff" radius={[2,2,0,0]} />
            <Bar dataKey="avg_valence"      name="Valence"      fill="#f59e0b" radius={[2,2,0,0]} />
          </BarChart>
        </ResponsiveContainer>
      </motion.div>
    </div>
  )
}
