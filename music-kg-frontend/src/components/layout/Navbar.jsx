import { useState, useRef, useEffect } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useApp } from '../../context/AppContext'
import { formatNumber } from '../../utils/helpers'

const NAV = [
  { to: '/',          label: 'Explore'    },
  { to: '/search',    label: 'Search'     },
  { to: '/timeline',  label: 'Timeline'   },
  { to: '/analytics', label: 'Analytics'  },
  { to: '/graph',     label: 'Graph'      },
]

export default function Navbar() {
  const { stats } = useApp()
  const [searchOpen, setSearchOpen] = useState(false)
  const [q, setQ] = useState('')
  const inputRef = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (searchOpen) inputRef.current?.focus()
  }, [searchOpen])

  const handleSearch = (e) => {
    e.preventDefault()
    if (!q.trim()) return
    navigate(`/search?q=${encodeURIComponent(q.trim())}`)
    setSearchOpen(false)
    setQ('')
  }

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-bg-secondary border-b border-border-col">
      <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-8">

        {/* Logo */}
        <NavLink to="/" className="flex items-center gap-2 shrink-0">
          <span className="text-xl">🎵</span>
          <span className="font-bold text-accent tracking-tight">MusicKG</span>
        </NavLink>

        {/* Nav links */}
        <div className="hidden md:flex items-center gap-1 flex-1">
          {NAV.map(({ to, label }) => (
            <NavLink key={to} to={to} end={to === '/'}
              className={({ isActive }) =>
                `px-3 py-1.5 text-sm rounded-btn transition-colors ${
                  isActive
                    ? 'text-text-primary bg-bg-hover'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-hover'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </div>

        {/* Stats badge */}
        {stats.total_triples > 0 && (
          <div className="hidden lg:flex items-center gap-1.5 px-3 py-1 bg-bg-card border border-border-col rounded-pill text-xs text-text-muted shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
            {formatNumber(stats.total_triples)} triples
          </div>
        )}

        {/* Search toggle */}
        <button
          onClick={() => setSearchOpen(v => !v)}
          className="p-2 text-text-secondary hover:text-text-primary transition-colors shrink-0"
          aria-label="Search"
        >
          🔍
        </button>
      </div>

      {/* Expandable search */}
      <AnimatePresence>
        {searchOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 56, opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden border-t border-border-col bg-bg-secondary"
          >
            <form onSubmit={handleSearch} className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-3">
              <input
                ref={inputRef}
                value={q}
                onChange={e => setQ(e.target.value)}
                placeholder="Search artists, albums, tracks..."
                className="flex-1 bg-bg-card border border-border-col rounded-card px-4 py-2 text-sm text-text-primary placeholder-text-muted outline-none focus:border-accent transition-colors"
              />
              <button type="submit"
                className="px-4 py-2 bg-accent text-black font-semibold text-sm rounded-btn hover:bg-accent-hover transition-colors">
                Search
              </button>
              <button type="button" onClick={() => setSearchOpen(false)}
                className="text-text-muted hover:text-text-primary transition-colors text-xl leading-none">
                ×
              </button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  )
}
