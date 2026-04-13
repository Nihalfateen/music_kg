import { useState, useEffect } from 'react'
import {useParams, Link, useNavigate} from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  ResponsiveContainer
} from 'recharts'
import toast from 'react-hot-toast'

import { getArtistDetail, getRecommendations, updateTrackMetadata, deleteTrack} from '../api'
import AudioFeatureBar from '../components/common/AudioFeatureBar'
import { PageSkeleton } from '../components/common/LoadingSkeleton'
import { hashColor, formatMs } from '../utils/helpers'

import AddSongsModal from "../components/modals/AddSongsModal.jsx";

// Sortable tracks table
function SortableTable({ tracks, onEdit, onDelete }) {
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
            <Th k="album_name" label="Album"/>
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

                <td className="py-2.5 text-xs text-text-secondary truncate max-w-[150px]">
                  <span className={t.album_name === 'Single' ? 'italic opacity-50' : ''}>
                    {t.album_name}
                  </span>
                </td>

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

                <td className="py-2.5 text-right">
                  <button
                    onClick={() => onEdit(t)}
                    className="opacity-100 group-hover:opacity-100 p-1.5 hover:bg-accent/20 rounded-pill text-accent transition-all text-xs font-semibold"
                  >✎ Edit</button>
                  <button
                    onClick={() => onDelete(t)}
                    className="p-1.5 hover:bg-red-500/20 rounded text-red-500 text-xs font-bold"
                  >❌ Delete </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// Album row — expands inline to show tracks
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

// Main page
export default function ArtistDetailPage() {
  const { slug } = useParams()
  const [artist, setArtist]   = useState(null)
  const [recs, setRecs]       = useState(null)
  const [loading, setLoading] = useState(true)

  const [showAddSongs, setShowAddSongs] = useState(false)
  const [editingTrack, setEditingTrack] = useState(null)
  const [newAlbumName, setNewAlbumName] = useState("")

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getArtistDetail(slug),
      getRecommendations(slug).catch(() => ({ data: { similar_artists: [], recommended_tracks: [] } })),
    ])
      .then(([artRes, recRes]) => {
        setArtist(artRes.data)
        setRecs(recRes.data)
      })
      .catch(() => toast.error('Failed to load artist'))
      .finally(() => setLoading(false))
  }, [slug])

  const handleUpdateAlbum = async () => {
    if (!newAlbumName.trim()) return toast.error("Please enter an album name")

    try {
      await updateTrackMetadata({
        trackUri: editingTrack.uri,
        artistUri: artist.uri,
        newAlbumName: newAlbumName
      });

      const res = await getArtistDetail(slug);
      setArtist(res.data);

      setEditingTrack(null);
      toast.success('Sync complete!');

    } catch (err) {
      toast.error('Failed to update the Knowledge Graph');
      console.error(err);
    }
  }

  const handleDeleteTrack = async (track) => {
    // confirmation Pop-up
    const confirmed = window.confirm(`Are you sure you want to delete "${track.name}"? This will permanently remove it from the Knowledge Graph.`);

    if (!confirmed) return;

    const tid = toast.loading("Deleting track...");
    try {
      await deleteTrack( {trackUri: track.uri });

      const res = await getArtistDetail(slug);
      setArtist(res.data);

      toast.dismiss(tid);
      toast.success("Track deleted and graph cleaned.");
    } catch (err) {
      toast.dismiss(tid);
      toast.error("Failed to delete track.");
      console.error(err);
    }
  }

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

  const allAlbums  = artist.albums || []
  const allTracks = artist.top_tracks || []


  const albumsWithTracks = allAlbums.map(album => ({
    ...album,
    tracks: allTracks.filter(t => t.album_uri === album.uri)
  }))

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">

      {/* Header */}
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
                {allAlbums.length > 0 && <span>💿 {allAlbums.length} album{allAlbums.length !== 1 ? 's' : ''}</span>}
                <span>🎵 {allTracks.length || 0} tracks</span>
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


      {/* Audio Profile */}
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


      {/* Discography */}
      {albumsWithTracks.length > 0 && (
        <section className="mb-10">
          <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider mb-4">
            Albums
            <span className="ml-2 text-text-muted font-normal normal-case text-xs">
              — click to expand tracks
            </span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {albumsWithTracks.map(a =>
                <AlbumCard key={a.uri} album={a} />
            )}
          </div>
        </section>
      )}


      {/* Songs Table */}
      <section className="mt-8 mb-12">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-text-primary">All Songs</h2>
          <button
            onClick={() => setShowAddSongs(true)}
            className="text-xs bg-accent text-bg-primary px-4 py-2 rounded-pill hover:bg-accent-hover transition-all font-bold shadow-md"
          >
            + Add Songs
          </button>
        </div>

        {allTracks.length > 0 ? (
          <div className="bg-bg-card border border-border-col rounded-card p-4">
            <SortableTable
              tracks={allTracks}
              onEdit={(t) => {
                setEditingTrack(t);
                setNewAlbumName(t.album_name || "");
              }}
              onDelete={handleDeleteTrack}
            />
          </div>
        ) : (
          <div className="text-center py-16 bg-bg-card rounded-card border border-dashed border-border-col">
            <div className="text-4xl mb-4 opacity-30">💿</div>
            <p className="text-text-muted text-sm mb-6">This artist has no tracks in the Knowledge Graph yet.</p>
          </div>
        )}

        {showAddSongs && (
          <AddSongsModal
            artist={artist}
            onClose={() => setShowAddSongs(false)}
            onSuccess={async () => {
              setShowAddSongs(false);

              const res = await getArtistDetail(slug);
              setArtist(res.data);

              toast.success("Knowledge Graph updated!");
            }}
          />
        )}
      </section>


      {/* Similar Artists */}
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


      {/* Recommendations */}
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


      {/* Modals */}
      <AnimatePresence>
        {editingTrack && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
            <motion.div initial={{ scale: 0.9 }} animate={{ scale: 1 }} exit={{ scale: 0.9 }}
              className="bg-bg-card border border-border-col rounded-card p-6 w-full max-w-md shadow-2xl">
              <h3 className="text-lg font-bold mb-2 text-text-primary">Edit Track Metadata</h3>
              <p className="text-sm text-text-muted mb-4">Updating: <span className="text-accent">{editingTrack.name}</span></p>
              <div className="mb-6 p-3 bg-bg-primary rounded-card border border-border-col/50">
                <p className="text-[10px] text-text-muted uppercase mb-1">Current Album</p>
                <p className="text-sm font-mono text-text-primary">{editingTrack.album_name}</p>
              </div>
              <label className="block text-xs font-semibold text-text-muted uppercase mb-2">New Album Name</label>
              <input
                autoFocus
                value={newAlbumName}
                onChange={(e) => setNewAlbumName(e.target.value)}
                placeholder="Type album name..."
                className="w-full bg-bg-primary border border-border-col rounded-pill px-4 py-2 outline-none focus:border-accent text-text-primary mb-6"
              />
              <div className="flex gap-3">
                <button onClick={handleUpdateAlbum} className="flex-1 bg-accent text-bg-primary font-bold py-2 rounded-pill hover:bg-accent-hover transition-colors">Save</button>
                <button onClick={() => setEditingTrack(null)} className="flex-1 bg-bg-hover text-text-primary py-2 rounded-pill hover:bg-border-col transition-colors">Cancel</button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {showAddSongs && (
        <AddSongsModal
          artist={artist}
          onClose={() => setShowAddSongs(false)}
          onSuccess={async () => {
            setShowAddSongs(false);
            // window.location.reload();

            const tid = toast.loading("Updating your library...");

            const res = await getArtistDetail(slug);

            setArtist(res.data);

            toast.dismiss(tid);
            toast.success("Song added to Knowledge Graph!");
          }}
        />
      )}
    </div>
  )
}
