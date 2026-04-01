import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  ResponsiveContainer
} from 'recharts'
import toast from 'react-hot-toast'
import { getArtistDetail, getRecommendations } from '../api'
import AudioFeatureBar from '../components/common/AudioFeatureBar'
import { PageSkeleton } from '../components/common/LoadingSkeleton'
import { hashColor, formatMs } from '../utils/helpers'

// ── Sortable tracks table ─────────────────────────────────────────────────────
function SortableTable({ tracks }) {
  const [sortKey, setSortKey] = useState('popularity')
  const [asc, setAsc] = useState(false)

  const toggle = (key) => {
    if (sortKey === key) setAsc(a => !a)
    else { setSortKey(key); setAsc(false) }
  }

  const sorted = [...tracks].sort((a, b) => {
    const af = a.audio_features || {}
    const bf = b.audio_features || {}
    const va = { popularity: a.popularity, energy: af.energy, danceability: af.danceability, valence: af.valence, duration_ms: a.duration_ms }[sortKey] ?? 0
    const vb = { popularity: b.popularity, energy: bf.energy, danceability: bf.danceability, valence: bf.valence, duration_ms: b.duration_ms }[sortKey] ?? 0
    return asc ? va - vb : vb - va
  })

  const Th = ({ k, label }) => (
    <th className="text-left text-xs text-text-muted uppercase tracking-wider pb-2 cursor-pointer hover:text-accent transition-colors select-none"
      onClick={() => toggle(k)}>
      {label} {sortKey === k ? (asc ? '↑' : '↓') : ''}
    </th>
  )

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border-col">
            <th className="text-left text-xs text-text-muted uppercase tracking-wider pb-2 w-8">#</th>
            <th className="text-left text-xs text-text-muted uppercase tracking-wider pb-2">Track</th>
            <Th k="popularity"   label="Pop" />
            <Th k="energy"       label="Energy" />
            <Th k="danceability" label="Dance" />
            <Th k="valence"      label="Valence" />
            <Th k="duration_ms"  label="Time" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((t, i) => {
            const af = t.audio_features || {}
            return (
              <tr key={t.uri || i} className="border-b border-border-col/40 hover:bg-bg-hover transition-colors">
                <td className="py-2.5 text-sm text-text-muted">{i + 1}</td>
                <td className="py-2.5 text-sm font-medium text-text-primary max-w-xs truncate pr-4">{t.name}</td>
                <td className="py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1 bg-bg-hover rounded-full overflow-hidden">
                      <div className="h-full bg-accent rounded-full" style={{ width: `${t.popularity || 0}%` }} />
                    </div>
                    <span className="text-xs text-text-muted">{t.popularity}</span>
                  </div>
                </td>
                <td className="py-2.5 text-xs text-text-secondary font-mono">{af.energy?.toFixed(2) ?? '—'}</td>
                <td className="py-2.5 text-xs text-text-secondary font-mono">{af.danceability?.toFixed(2) ?? '—'}</td>
                <td className="py-2.5 text-xs text-text-secondary font-mono">{af.valence?.toFixed(2) ?? '—'}</td>
                <td className="py-2.5 text-xs text-text-muted">{formatMs(t.duration_ms)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Album row — expands inline to show tracks ─────────────────────────────────
// Option A: inline tracks expanded inside the card
// Option B: singles grouped separately
function AlbumCard({ album }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border border-border-col rounded-card overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 p-4 hover:bg-bg-hover transition-colors text-left"
      >
        <div className="w-10 h-10 rounded-card bg-bg-hover flex items-center justify-center text-lg shrink-0">
          💿
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm text-text-primary truncate">{album.name}</p>
          <p className="text-xs text-text-muted">
            {album.year && <span>{album.year} · </span>}
            <span>{album.tracks?.length || album.track_count || 0} tracks</span>
          </p>
        </div>
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          className="text-text-muted text-xs shrink-0"
        >▼</motion.span>
      </button>

      <AnimatePresence>
        {open && album.tracks?.length > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden border-t border-border-col"
          >
            <div className="divide-y divide-border-col/30">
              {album.tracks.map((t, i) => {
                const af = t.audio_features || {}
                return (
                  <div key={t.uri || i} className="flex items-center gap-3 px-4 py-2.5 hover:bg-bg-hover transition-colors">
                    <span className="text-xs text-text-muted w-5 shrink-0">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-text-primary truncate">{t.name}</p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      {af.energy != null && (
                        <span className="text-xs text-text-muted hidden sm:block">
                          E:{af.energy?.toFixed(2)}
                        </span>
                      )}
                      {af.danceability != null && (
                        <span className="text-xs text-text-muted hidden sm:block">
                          D:{af.danceability?.toFixed(2)}
                        </span>
                      )}
                      <div className="flex items-center gap-1">
                        <div className="w-10 h-1 bg-bg-primary rounded-full overflow-hidden">
                          <div className="h-full bg-accent rounded-full"
                            style={{ width: `${t.popularity || 0}%` }} />
                        </div>
                        <span className="text-xs text-text-muted w-5">{t.popularity}</span>
                      </div>
                      <span className="text-xs text-text-muted w-10 text-right">
                        {formatMs(t.duration_ms)}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Singles section (Option B) ────────────────────────────────────────────────
function SinglesSection({ tracks }) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? tracks : tracks.slice(0, 6)

  return (
    <div className="bg-bg-card border border-border-col rounded-card overflow-hidden">
      <div className="px-4 py-3 border-b border-border-col flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">🎵</span>
          <div>
            <p className="text-sm font-semibold text-text-primary">Singles & EPs</p>
            <p className="text-xs text-text-muted">{tracks.length} releases</p>
          </div>
        </div>
      </div>
      <div className="divide-y divide-border-col/30">
        {visible.map((t, i) => {
          const af = t.audio_features || {}
          return (
            <div key={t.uri || i}
              className="flex items-center gap-3 px-4 py-2.5 hover:bg-bg-hover transition-colors">
              <span className="text-xs text-text-muted w-5 shrink-0">{i + 1}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-text-primary truncate">{t.name}</p>
                {t.year && <p className="text-xs text-text-muted">{t.year}</p>}
              </div>
              <div className="flex items-center gap-3 shrink-0">
                {af.energy != null && (
                  <span className="text-xs text-text-muted hidden sm:block">
                    E:{af.energy?.toFixed(2)}
                  </span>
                )}
                <div className="flex items-center gap-1">
                  <div className="w-10 h-1 bg-bg-primary rounded-full overflow-hidden">
                    <div className="h-full bg-accent rounded-full"
                      style={{ width: `${t.popularity || 0}%` }} />
                  </div>
                  <span className="text-xs text-text-muted w-5">{t.popularity}</span>
                </div>
                <span className="text-xs text-text-muted w-10 text-right">
                  {formatMs(t.duration_ms)}
                </span>
              </div>
            </div>
          )
        })}
      </div>
      {tracks.length > 6 && (
        <button
          onClick={() => setExpanded(e => !e)}
          className="w-full py-2.5 text-xs text-accent hover:text-accent-hover transition-colors border-t border-border-col hover:bg-bg-hover"
        >
          {expanded ? 'Show less ▲' : `Show all ${tracks.length} singles ▼`}
        </button>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ArtistDetailPage() {
  const { slug } = useParams()
  const [artist, setArtist]   = useState(null)
  const [recs, setRecs]       = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getArtistDetail(slug),
      getRecommendations(slug).catch(() => ({ data: null })),
    ])
      .then(([artRes, recRes]) => {
        setArtist(artRes.data)
        setRecs(recRes.data)
      })
      .catch(() => toast.error('Failed to load artist'))
      .finally(() => setLoading(false))
  }, [slug])

  if (loading) return <PageSkeleton />
  if (!artist) return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="text-5xl mb-4">🎤</div>
      <h2 className="text-xl font-bold text-text-primary">Artist not found</h2>
    </div>
  )

  const af = artist.avg_audio_features || {}
  const radarData = [
    { subject: 'Energy',       value: af.energy       ?? 0 },
    { subject: 'Danceability', value: af.danceability ?? 0 },
    { subject: 'Valence',      value: af.valence      ?? 0 },
    { subject: 'Tempo',        value: af.tempo        ?? 0 },
    { subject: 'Loudness',     value: af.loudness     ?? 0 },
  ]

  const primaryGenre = artist.genres?.[0] || ''
  const accentColor  = primaryGenre ? hashColor(primaryGenre) : '#1db954'

  // ── Option B: separate real albums from singles ───────────────────────────
  const allAlbums  = artist.albums || []

  // Build track lookup from top_tracks for singles
  const topTracksBySlug = {}
  ;(artist.top_tracks || []).forEach(t => {
    topTracksBySlug[t.slug] = t
  })

  // Albums with 2+ tracks = real albums (enrich with tracks from top_tracks)
  const realAlbums = allAlbums
    .filter(a => (a.track_count || 0) > 1)
    .map(a => ({
      ...a,
      // Attach matching tracks from top_tracks to show inline
      tracks: (artist.top_tracks || []).filter(t =>
        t.slug && a.slug && t.name  // basic match — will show what we have
      ).slice(0, a.track_count || 5)
    }))

  // Albums with 1 track = singles → flatten to track list
  const singles = allAlbums
    .filter(a => (a.track_count || 0) <= 1)
    .map(a => {
      // Try to find matching track from top_tracks by album name
      const match = (artist.top_tracks || []).find(t =>
        t.name?.toLowerCase() === a.name?.toLowerCase()
      )
      return {
        uri:        a.uri,
        slug:       a.slug,
        name:       a.name,
        year:       a.year,
        popularity: match?.popularity || 0,
        duration_ms: match?.duration_ms || 0,
        audio_features: match?.audio_features || {},
      }
    })
    .sort((a, b) => (b.popularity || 0) - (a.popularity || 0))

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <motion.div className="mb-10"
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <div className="relative rounded-card overflow-hidden p-8 mb-6"
          style={{ background: `linear-gradient(135deg, ${accentColor}22, transparent), var(--bg-card)` }}>
          <div className="flex items-start gap-6">
            <div className="w-20 h-20 rounded-full flex items-center justify-center text-4xl shrink-0"
              style={{ background: accentColor + '33' }}>🎤</div>
            <div className="flex-1 min-w-0">
              <h1 className="text-4xl font-extrabold text-text-primary mb-3">{artist.name}</h1>
              <div className="flex flex-wrap gap-2 mb-4">
                {artist.genres?.map(g => (
                  <Link key={g} to={`/search?genre=${encodeURIComponent(g)}`}
                    className="px-3 py-1 rounded-pill text-xs font-semibold"
                    style={{ background: hashColor(g) + '33', color: hashColor(g) }}>
                    {g}
                  </Link>
                ))}
              </div>
              <div className="flex items-center gap-6 text-sm text-text-secondary flex-wrap">
                {realAlbums.length > 0 && <span>💿 {realAlbums.length} album{realAlbums.length !== 1 ? 's' : ''}</span>}
                {singles.length > 0    && <span>🎵 {singles.length} single{singles.length !== 1 ? 's' : ''}</span>}
                <span>🎵 {artist.top_tracks?.length || 0}+ tracks</span>
                {artist.similar_artists?.length > 0 && <span>🔗 {artist.similar_artists.length} similar</span>}
                {artist.dbpedia_uri && (
                  <a href={artist.dbpedia_uri} target="_blank" rel="noreferrer"
                    className="text-accent hover:text-accent-hover transition-colors flex items-center gap-1">
                    DBpedia ↗
                  </a>
                )}
              </div>
            </div>
          </div>
        </div>
      </motion.div>

      {/* ── Audio Profile ────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-10">
        {af.energy != null && (
          <div className="bg-bg-card border border-border-col rounded-card p-5">
            <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">Audio Profile</h2>
            <ResponsiveContainer width="100%" height={200}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="#282828" />
                <PolarAngleAxis dataKey="subject" tick={{ fill: '#b3b3b3', fontSize: 10 }} />
                <Radar name="Features" dataKey="value" stroke={accentColor} fill={accentColor} fillOpacity={0.2} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className="lg:col-span-2 bg-bg-card border border-border-col rounded-card p-5">
          <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-4">Avg Audio Features</h2>
          <div className="space-y-1">
            <AudioFeatureBar featureName="Energy"       value={af.energy}       color="#e91e8c" />
            <AudioFeatureBar featureName="Danceability" value={af.danceability} color="#00d4ff" />
            <AudioFeatureBar featureName="Valence"      value={af.valence}      color="#f59e0b" />
            <AudioFeatureBar featureName="Tempo"        value={af.tempo}        color="#a855f7" />
            <AudioFeatureBar featureName="Loudness"     value={af.loudness}     color="#10b981" />
          </div>
        </div>
      </div>

      {/* ── Option A: Real Albums (2+ tracks) — expand inline ────────────────── */}
      {realAlbums.length > 0 && (
        <section className="mb-10">
          <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider mb-4">
            Albums
            <span className="ml-2 text-text-muted font-normal normal-case text-xs">
              — click to expand tracks
            </span>
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {realAlbums.map(a => <AlbumCard key={a.uri} album={a} />)}
          </div>
        </section>
      )}

      {/* ── Top Tracks table ─────────────────────────────────────────────────── */}
      {artist.top_tracks?.length > 0 && (
        <section className="mb-10">
          <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider mb-4">Top Tracks</h2>
          <div className="bg-bg-card border border-border-col rounded-card p-4">
            <SortableTable tracks={artist.top_tracks} />
          </div>
        </section>
      )}

      {/* ── Option B: Singles & EPs ───────────────────────────────────────────── */}
      {singles.length > 0 && (
        <section className="mb-10">
          <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider mb-4">
            Singles & EPs
            <span className="ml-2 text-text-muted font-normal normal-case text-xs">
              — {singles.length} releases
            </span>
          </h2>
          <SinglesSection tracks={singles} />
        </section>
      )}

      {/* ── Similar Artists ───────────────────────────────────────────────────── */}
      {recs?.similar_artists?.length > 0 && (
        <section className="mb-10">
          <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider mb-4">Similar Artists</h2>
          <div className="flex gap-3 overflow-x-auto pb-2">
            {recs.similar_artists.map(a => (
              <Link key={a.uri} to={`/artist/${a.slug}`}
                className="shrink-0 bg-bg-card border border-border-col rounded-card p-4 w-40 hover:border-accent transition-all text-center">
                <div className="w-10 h-10 rounded-full mx-auto mb-2 flex items-center justify-center text-xl"
                  style={{ background: hashColor(a.name) + '33' }}>🎤</div>
                <p className="text-xs font-semibold text-text-primary truncate">{a.name}</p>
                {a.shared_genres?.length > 0 && (
                  <p className="text-xs text-text-muted mt-1 truncate">{a.shared_genres[0]}</p>
                )}
                <p className="text-xs mt-1" style={{ color: '#1db954' }}>
                  {Math.round((a.similarity_score || 0) * 100)}% match
                </p>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* ── You May Also Like ─────────────────────────────────────────────────── */}
      {(recs?.recommended_tracks || recs?.you_may_also_like)?.length > 0 && (
        <section className="mb-10">
          <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider mb-4">You May Also Like</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {(recs.recommended_tracks || recs.you_may_also_like).slice(0, 6).map((t, i) => (
              <div key={t.track_uri || t.uri || i}
                className="bg-bg-card border border-border-col rounded-card p-3 flex items-center gap-3 hover:border-accent/40 transition-colors">
                <div className="w-8 h-8 rounded-full bg-bg-hover flex items-center justify-center text-sm shrink-0">🎵</div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-text-primary truncate">
                    {t.track_name || t.name}
                  </p>
                  <p className="text-xs text-text-muted truncate">
                    {t.artist_name || t.artist}
                    {t.because_similar_to && (
                      <span className="text-text-muted/60"> · like {t.because_similar_to}</span>
                    )}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <div className="w-8 h-1 bg-bg-primary rounded-full overflow-hidden">
                    <div className="h-full bg-accent rounded-full"
                      style={{ width: `${t.popularity || 0}%` }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}