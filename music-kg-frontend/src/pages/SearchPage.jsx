import { useState, useEffect, useCallback, useRef } from 'react'
import {useNavigate, useSearchParams} from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'

import { searchAll, getArtists } from '../api'
import EntityCard from '../components/common/EntityCard'
import { CardSkeleton } from '../components/common/LoadingSkeleton'
import { hashColor } from '../utils/helpers'
import AddArtistModal from "../components/modals/AddArtistModal.jsx";

const GENRES = ['pop','rap','rock','latin','r&b','edm']
const ENTITY_TYPES = ['Artists & Albums','Artists','Albums','Tracks']
const SORT_OPTIONS = ['Relevance','Popularity','Year','Name']

function DualSlider({ min, max, step = 0.01, value, onChange, label, format = v => v.toFixed(2) }) {
  return (
    <div className="mb-4">
      <div className="flex justify-between text-xs text-text-muted mb-1">
        <span>{label}</span>
        <span>{format(value[0])} — {format(value[1])}</span>
      </div>
      <div className="space-y-1">
        <input type="range" min={min} max={max} step={step}
          value={value[0]}
          onChange={e => onChange([parseFloat(e.target.value), value[1]])}
          className="w-full accent-accent h-1"
        />
        <input type="range" min={min} max={max} step={step}
          value={value[1]}
          onChange={e => onChange([value[0], parseFloat(e.target.value)])}
          className="w-full accent-accent h-1"
        />
      </div>
    </div>
  )
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams()

  const navigate = useNavigate()

  const [q, setQ]               = useState(params.get('q') || '')
  const [results, setResults]   = useState([])
  const [loading, setLoading]   = useState(false)
  const [page, setPage]         = useState(1)
  const [hasMore, setHasMore]   = useState(false)
  const [total, setTotal]       = useState(0)

  const [showAddModal, setShowAddModal] = useState(false)

  // Filters
  const [selectedGenres, setSelectedGenres] = useState(
    params.get('genre') ? [params.get('genre')] : []
  )
  const [yearRange, setYearRange]       = useState([1950, 2024])
  const [energyRange, setEnergyRange]   = useState([0, 1])
  const [danceRange, setDanceRange]     = useState([0, 1])
  const [minPop, setMinPop]             = useState(0)
  const [entityType, setEntityType]     = useState('Artists & Albums')
  const [sortBy, setSortBy]             = useState('Relevance')

  const debounceRef  = useRef(null)
  const loaderRef    = useRef(null)
  const isFetching   = useRef(false)

  const doSearch = useCallback(async (query, pageNum = 1, append = false) => {
    const hasQuery = query && query.trim().length > 0
    const hasGenre = selectedGenres.length > 0

    if (!hasQuery && !hasGenre) {
      setResults([])
      setTotal(0)
      return
    }

    if (!append) {
      setResults([]);
      setPage(1);
    }

    // Prevent concurrent non-append calls
    if (isFetching.current && !append) return
    isFetching.current = true
    setLoading(true)

    const typeMap = {
      'Artists': 'artist',
      'Albums': 'album',
      'Tracks': 'track',
      'Artists & Albums': 'artist_album',
      'All': 'artist_album'
    }

    try {
      const searchParams = {
        genre: selectedGenres[0] || null,
        type: typeMap[entityType],
        limit: 20,
        page: pageNum
      }

      const res = await searchAll(query.trim(), searchParams)
      const data = res?.data?.results || []

      setTotal(append ? (prev => prev + data.length) : (res?.data?.count || data.length))
      setHasMore(data.length >= 20)
      setResults(prev => append ? [...prev, ...data] : data)
    } catch (err) {
      console.error('[Search error]', err?.response?.data || err?.message || err)
      toast.error(`Search failed: ${err?.response?.data?.error || err?.message || 'Unknown error'}`)
      if (!append) setResults([])
    } finally {
      setLoading(false)
      isFetching.current = false
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedGenres, entityType])

  // Trigger search with debounce whenever q / genre / entityType changes
  useEffect(() => {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setPage(1)
      doSearch(q, 1, false)
    }, 300)
    return () => clearTimeout(debounceRef.current)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, selectedGenres, entityType])

  // Sync URL
  useEffect(() => {
    const p = {}
    if (q) p.q = q
    if (selectedGenres.length) p.genre = selectedGenres[0]
    setParams(p, { replace: true })
  }, [q, selectedGenres, setParams])

  // Infinite scroll
  useEffect(() => {
    const obs = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasMore && !loading && !isFetching.current) {
        const next = page + 1
        setPage(next)
        doSearch(q, next, true)
      }
    }, { threshold: 0.5 })
    if (loaderRef.current) obs.observe(loaderRef.current)
    return () => obs.disconnect()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasMore, loading, page, q])

  const clearFilters = () => {
    setSelectedGenres([])
    setYearRange([1950, 2024])
    setEnergyRange([0, 1])
    setDanceRange([0, 1])
    setMinPop(0)
    setEntityType('All')
  }

  const toggleGenre = (g) => {
    setSelectedGenres(prev =>
      prev.includes(g) ? prev.filter(x => x !== g) : [...prev, g]
    )
  }

  // Sort results
  const sorted = [...results].sort((a, b) => {
    if (sortBy === 'Popularity') return (b.extra_info?.popularity || b.popularity || 0) - (a.extra_info?.popularity || a.popularity || 0)
    if (sortBy === 'Name') return (a.name || '').localeCompare(b.name || '')
    if (sortBy === 'Year') return (b.extra_info?.year || 0) - (a.extra_info?.year || 0)
    return (b.score || 0) - (a.score || 0)
  })


  const hasExactMatch = results.some(item =>
    item.name?.toLowerCase() === q.trim().toLowerCase() &&
    item.type === 'artist'
  );

  const showAddBanner = q && !loading && !hasExactMatch
      && (entityType === 'Artists' || entityType === 'Artists & Albums');

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 border-r border-border-col bg-bg-secondary p-5 sticky top-14 h-[calc(100vh-3.5rem)] overflow-y-auto">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider">Filters</h2>
          <button onClick={clearFilters} className="text-xs text-text-muted hover:text-accent transition-colors">
            Clear all
          </button>
        </div>

        {/* Entity type */}
        <div className="mb-5">
          <p className="text-xs text-text-muted uppercase tracking-wider mb-2">Type</p>
          <div className="flex flex-wrap gap-1.5">
            {ENTITY_TYPES.map(t => (
              <button key={t} onClick={() => setEntityType(t)}
                className={`px-2.5 py-1 text-xs rounded-pill border transition-all ${
                  entityType === t
                    ? 'bg-accent text-black border-accent font-semibold'
                    : 'border-border-col text-text-secondary hover:border-text-muted'
                }`}
              >{t}</button>
            ))}
          </div>
        </div>

        {/* Genres */}
        <div className="mb-5">
          <p className="text-xs text-text-muted uppercase tracking-wider mb-2">Genre</p>
          <div className="space-y-1.5">
            {GENRES.map(g => (
              <label key={g} className="flex items-center gap-2 cursor-pointer group">
                <input type="checkbox" checked={selectedGenres.includes(g)}
                  onChange={() => toggleGenre(g)}
                  className="accent-accent rounded"
                />
                <span className="text-sm text-text-secondary group-hover:text-text-primary transition-colors capitalize">
                  {g}
                </span>
                <span className="ml-auto w-2 h-2 rounded-full shrink-0"
                  style={{ background: hashColor(g) }} />
              </label>
            ))}
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 p-6">
        {/* Search input + controls */}
        <div className="flex items-center gap-3 mb-5">
          <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Search artists or albums…"
              className="flex-1 bg-bg-card border border-border-col rounded-card px-4 py-2.5 text-sm text-text-primary placeholder-text-muted outline-none focus:border-accent transition-colors"
          />
          <select value={sortBy} onChange={e => setSortBy(e.target.value)}
                  className="bg-bg-card border border-border-col rounded-card px-3 py-2.5 text-sm text-text-secondary outline-none">
            {SORT_OPTIONS.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>

        <p className="text-[11px] text-text-muted mb-5 ml-1">
        {(() => {
          switch (entityType) {
            case 'Tracks': return <span>Viewing all matching songs.</span>;
            case 'Artists': return <span>Viewing all matching artists.</span>;
            case 'Albums': return <span>Viewing all matching albums.</span>;
            case 'Artists & Albums':
            default: return ( <> Viewing artists and albums. Switch to "Tracks" for song results.</>);
          }
        })()}
        </p>

        {/* Result count */}
        {(q || selectedGenres.length > 0) && !loading && (
            <p className="text-xs text-text-muted mb-4">
              {total} result{total !== 1 ? 's' : ''}
              {q && <span> for <span className="text-accent">"{q}"</span></span>}
            </p>
        )}

        {showAddBanner && (
            <motion.div
                initial={{opacity: 0, y: -10}}
                animate={{opacity: 1, y: 0}}
                className="mb-8 p-6 bg-accent/5 border border-accent/20 rounded-card flex flex-col md:flex-row items-center justify-between gap-4"
            >
              <div className="text-center md:text-left">
                <h3 className="text-lg font-bold text-text-primary">Artist not found?</h3>
              </div>
              <button
                  onClick={() => setShowAddModal(true)}
                  className="px-6 py-2.5 bg-accent text-black font-bold rounded-pill hover:bg-accent-hover transition-all shadow-lg shadow-accent/20 shrink-0"
              >
                + Add "{q}" to Graph
              </button>
            </motion.div>
        )}

        {/* Results grid */}
        {loading && results.length === 0 ? (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {[...Array(8)].map((_, i) => <CardSkeleton key={i}/>)}
            </div>
        ) : sorted.length > 0 ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                <AnimatePresence>
                  {sorted.map((item, i) => (
                      <motion.div key={item.uri || item.slug || i}
                                  initial={{opacity: 0, y: 10}}
                                  animate={{opacity: 1, y: 0}}
                                  transition={{delay: i * 0.03}}>
                        <EntityCard type={item.type || 'artist'} data={item}/>
                      </motion.div>
                  ))}
                </AnimatePresence>
              </div>
              {/* Infinite scroll sentinel */}
              <div ref={loaderRef} className="h-10 flex items-center justify-center mt-6">
                {loading && <span className="text-xs text-text-muted">Loading more…</span>}
              </div>
            </>
        ) : (q || selectedGenres.length > 0) ? (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="text-5xl mb-4">🔍</div>
              <h3 className="text-lg font-semibold text-text-primary mb-2">No results found</h3>
              <p className="text-sm text-text-secondary">Try a different search term or clear some filters.</p>
            </div>
        ) : (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="text-5xl mb-4">🎵</div>
              <h3 className="text-lg font-semibold text-text-primary mb-2">Start exploring</h3>
              <p className="text-sm text-text-secondary">Search for an artist or album. Use the "Tracks" filter to see
                songs.</p>
            </div>
        )}
        {showAddModal && (
            <AddArtistModal
                initialName={q}
                onClose={() => setShowAddModal(false)}
                onSuccess={(slug) => {
                  setShowAddModal(false)
                  navigate(`/artist/${slug}`)
                }}
            />
        )}
      </div>
    </div>
  )
}
