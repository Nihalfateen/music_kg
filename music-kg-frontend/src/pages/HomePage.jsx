import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'

import { useApp } from '../context/AppContext'
import { useCountUp } from '../hooks/useCountUp'
import { formatNumber, hashColor } from '../utils/helpers'
import { getGenreLandscape } from '../api'

const DECADES = ['1960s','1970s','1980s','1990s','2000s','2010s','2020s']

function StatCard({ icon, label, value, delay = 0 }) {
  const count = useCountUp(value, 1500)
  return (
    <motion.div
      className="bg-bg-card border border-border-col rounded-card p-5"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4 }}
    >
      <div className="text-2xl mb-2">{icon}</div>
      <div className="text-2xl font-bold text-text-primary">{formatNumber(count)}</div>
      <div className="text-xs text-text-muted mt-1 uppercase tracking-wider">{label}</div>
    </motion.div>
  )
}

function Waveform() {
  return (
    <div className="flex items-end gap-1 opacity-20 select-none pointer-events-none">
      {Array.from({ length: 40 }).map((_, i) => (
        <div
          key={i}
          className="w-1 bg-accent rounded-full"
          style={{
            height: `${20 + Math.sin(i * 0.5) * 15 + Math.random() * 10}px`,
            animation: `wave ${0.8 + (i % 5) * 0.15}s ease-in-out infinite alternate`,
            animationDelay: `${i * 0.04}s`,
          }}
        />
      ))}
    </div>
  )
}

export default function HomePage() {
  const { stats } = useApp()
  const [q, setQ]          = useState('')
  const [genres, setGenres] = useState([])
  const navigate = useNavigate()

  useEffect(() => {
    getGenreLandscape()
      .then(r => setGenres(r.data?.genres || []))
      .catch(() => toast.error('Could not load genres'))
  }, [])

  const handleSearch = (e) => {
    e.preventDefault()
    if (!q.trim()) return
    navigate(`/search?q=${encodeURIComponent(q.trim())}`)
  }

  const decadeYear = (d) => {
    const start = parseInt(d) 
    navigate(`/timeline?start_year=${start}&end_year=${start + 9}`)
  }

  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="relative flex flex-col items-center justify-center px-6 py-24 overflow-hidden">
        {/* Animated BG */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <Waveform />
        </div>
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-bg-primary/60 to-bg-primary pointer-events-none" />

        <motion.div className="relative z-10 text-center max-w-3xl"
          initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
          <h1 className="text-4xl md:text-6xl font-extrabold text-text-primary leading-tight mb-4">
            Explore Music as a<br />
            <span className="text-accent">Knowledge Graph</span>
          </h1>
          <p className="text-text-secondary text-lg mb-8">
            {formatNumber(stats.unique_artists)} artists ·{' '}
            {formatNumber(stats.unique_albums)} albums ·{' '}
            {formatNumber(stats.unique_tracks)} tracks ·{' '}
            {formatNumber(stats.total_triples)} RDF triples
          </p>

          {/* Search bar */}
          <form onSubmit={handleSearch} className="flex gap-3 max-w-xl mx-auto">
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Search artists, albums, tracks..."
              className="flex-1 bg-bg-card border border-border-col rounded-pill px-6 py-3 text-sm text-text-primary placeholder-text-muted outline-none focus:border-accent transition-colors"
            />
            <button type="submit"
              className="px-6 py-3 bg-accent text-black font-bold text-sm rounded-pill hover:bg-accent-hover transition-colors whitespace-nowrap">
              Search
            </button>
          </form>
        </motion.div>
      </section>

      {/* Stats row */}
      <section className="max-w-7xl mx-auto px-6 -mt-4 mb-12">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard icon="🎤" label="Artists"     value={stats.unique_artists} delay={0}   />
          <StatCard icon="💿" label="Albums"      value={stats.unique_albums}  delay={0.1} />
          <StatCard icon="🎵" label="Tracks"      value={stats.unique_tracks}  delay={0.2} />
          <StatCard icon="🔗" label="RDF Triples" value={stats.total_triples}  delay={0.3} />
        </div>
      </section>

      {/* Genre pills */}
      {genres.length > 0 && (
        <section className="max-w-7xl mx-auto px-6 mb-12">
          <h2 className="text-xs font-semibold text-text-muted uppercase tracking-widest mb-4">Browse by Genre</h2>
          <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-thin">
            {genres.map(g => (
              <button
                key={g.genre}
                onClick={() => navigate(`/search?genre=${encodeURIComponent(g.genre)}`)}
                className="shrink-0 px-4 py-1.5 rounded-pill text-sm font-medium border transition-all hover:scale-105"
                style={{
                  background: hashColor(g.genre) + '22',
                  borderColor: hashColor(g.genre) + '55',
                  color: hashColor(g.genre),
                }}
              >
                {g.genre}
                <span className="ml-2 text-xs opacity-60">{formatNumber(g.track_count)}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Explore by Decade */}
      <section className="max-w-7xl mx-auto px-6 mb-16">
        <h2 className="text-xs font-semibold text-text-muted uppercase tracking-widest mb-4">Explore by Decade</h2>
        <div className="flex gap-3 flex-wrap">
          {DECADES.map(d => (
            <button
              key={d}
              onClick={() => decadeYear(d)}
              className="px-5 py-2 bg-bg-card border border-border-col rounded-card text-sm font-semibold text-text-secondary hover:border-accent hover:text-accent transition-all"
            >
              {d}
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}
