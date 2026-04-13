import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'

import { getAlbumDetail, updateAlbumYear } from '../api'
import AudioFeatureBar from '../components/common/AudioFeatureBar'
import { PageSkeleton } from '../components/common/LoadingSkeleton'
import { formatMs } from '../utils/helpers'

export default function AlbumDetailPage() {
  const { slug } = useParams()
  const [album, setAlbum]   = useState(null)
  const [loading, setLoading] = useState(true)

  const [isEditingYear, setIsEditingYear] = useState(false)
  const [tempYear, setTempYear] = useState('')

  useEffect(() => {
    setLoading(true)
    getAlbumDetail(slug)
      .then(r => setAlbum(r.data))
      .catch(() => toast.error('Failed to load album'))
      .finally(() => setLoading(false))
  }, [slug])

  const handleSaveYear = async () => {
    try {
      await updateAlbumYear({
        albumUri: album.uri,
        newYear: parseInt(tempYear)
      });
      setAlbum({ ...album, year: tempYear });
      setIsEditingYear(false);
      toast.success('Release year updated');
    } catch (err) {
      toast.error('Update failed');
    }
  }

  if (loading) return <PageSkeleton />
  if (!album) return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="text-5xl mb-4">💿</div>
      <h2 className="text-xl font-bold text-text-primary">Album not found</h2>
    </div>
  )

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>

        {/* Header Section */}
        <div className="bg-bg-card border border-border-col rounded-card p-6 mb-8 flex items-center gap-6">
          <div className="w-20 h-20 rounded-card bg-bg-hover flex items-center justify-center text-4xl shrink-0">💿</div>

          <div>
            <h1 className="text-3xl font-extrabold text-text-primary mb-1">{album.name}</h1>
            <Link to={`/artist/${album.artist_slug}`}
              className="text-accent hover:text-accent-hover transition-colors text-sm font-medium">
              {album.artist_name}
            </Link>
            <div className="flex items-center gap-2 mt-1">
              {isEditingYear ? (
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    autoFocus
                    value={tempYear}
                    onChange={(e) => setTempYear(e.target.value)}
                    className="bg-bg-primary border border-border-col rounded px-2 py-0.5 text-xs w-20 text-text-primary outline-none focus:border-accent"
                  />
                  <button onClick={handleSaveYear} className="text-[10px] text-accent font-bold uppercase hover:underline">Save</button>
                  <button onClick={() => setIsEditingYear(false)} className="text-[10px] text-text-muted font-bold uppercase hover:underline">Cancel</button>
                </div>
              ) : (
                <p className="group text-xs text-text-muted flex items-center gap-2">
                  <span>{album.year} · {album.track_count} tracks</span>
                  <button
                    onClick={() => { setTempYear(album.year); setIsEditingYear(true); }}
                    className="opacity-0 group-hover:opacity-100 transition-opacity text-accent text-[10px]"
                  >
                    ✎ Edit Year
                  </button>
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Tracks List */}
        <div className="bg-bg-card border border-border-col rounded-card overflow-hidden">
          <div className="px-5 py-3 border-b border-border-col">
            <h2 className="text-xs font-bold text-text-muted uppercase tracking-wider">Tracks</h2>
          </div>
          <div className="divide-y divide-border-col/40">
            {album.tracks?.map((t, i) => {
              const af = t.audio_features || {}
              return (
                <motion.div key={t.uri || i}
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.03 }}
                  className="p-4 hover:bg-bg-hover transition-colors"
                >
                  <div className="flex items-center gap-4 mb-2">
                    <span className="text-sm text-text-muted w-6 shrink-0">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-sm text-text-primary truncate">{t.name}</p>
                    </div>
                    <span className="text-xs text-text-muted shrink-0">{formatMs(t.duration_ms)}</span>
                    <div className="flex items-center gap-1 shrink-0">
                      <div className="w-12 h-1 bg-bg-primary rounded-full overflow-hidden">
                        <div className="h-full bg-accent rounded-full" style={{ width: `${t.popularity || 0}%` }} />
                      </div>
                      <span className="text-xs text-text-muted w-6">{t.popularity}</span>
                    </div>
                  </div>
                  {(af.energy != null || af.danceability != null) && (
                    <div className="ml-10 grid grid-cols-3 gap-x-6">
                      {af.energy       != null && <AudioFeatureBar featureName="energy"   value={af.energy}       color="#e91e8c" />}
                      {af.danceability != null && <AudioFeatureBar featureName="dance"    value={af.danceability} color="#00d4ff" />}
                      {af.valence      != null && <AudioFeatureBar featureName="valence"  value={af.valence}      color="#f59e0b" />}
                    </div>
                  )}
                </motion.div>
              )
            })}
          </div>
        </div>
      </motion.div>
    </div>
  )
}
