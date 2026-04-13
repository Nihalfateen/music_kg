import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { hashColor, formatMs } from '../../utils/helpers'
import AudioFeatureBar from './AudioFeatureBar'

export default function EntityCard({ type, data, onClick }) {
  const navigate = useNavigate()

  const handleClick = () => {
    if (onClick) return onClick(data)
    if (type === 'artist') navigate(`/artist/${encodeURIComponent(data.slug)}`)
    if (type === 'album')  navigate(`/album/${encodeURIComponent(data.slug)}`)
  }

  return (
    <motion.div
      onClick={handleClick}
      className="bg-bg-card border border-border-col rounded-card p-4 cursor-pointer select-none"
      whileHover={{ scale: 1.02, borderColor: '#1db954', boxShadow: '0 0 0 1px #1db95440' }}
      transition={{ duration: 0.15 }}
    >
      {type === 'artist' && <ArtistCard data={data} />}
      {type === 'album'  && <AlbumCard  data={data} />}
      {type === 'track'  && <TrackCard  data={data} />}
    </motion.div>
  )
}

function ArtistCard({ data }) {
  const genre = data.genres?.[0]
  return (
    <div>
      <div className="w-12 h-12 rounded-full flex items-center justify-center text-xl mb-3"
           style={{ background: hashColor(data.name || '') + '33' }}>
        🎤
      </div>
      <h3 className="font-semibold text-sm text-text-primary truncate">{data.name}</h3>
      {genre && (
        <span className="inline-block mt-1 px-2 py-0.5 text-xs rounded-pill font-medium"
              style={{ background: hashColor(genre) + '33', color: hashColor(genre) }}>
          {genre}
        </span>
      )}
    </div>
  )
}

function AlbumCard({ data }) {
  return (
    <div>
      <div className="w-12 h-12 rounded-card flex items-center justify-center text-xl mb-3 bg-bg-hover">
        💿
      </div>
      <h3 className="font-semibold text-sm text-text-primary truncate">{data.name}</h3>
      <p className="text-xs text-text-secondary mt-0.5 truncate">{data.artist_name || data.artist}</p>
      <div className="flex items-center gap-2 mt-1">
        {data.year && <span className="text-xs text-text-muted">{data.year}</span>}
        {data.track_count > 0 && (
          <span className="text-xs text-text-muted">{data.track_count} tracks</span>
        )}
      </div>
    </div>
  )
}

function TrackCard({ data }) {
  const af = data.audio_features || {}
  const pop = (data.popularity || 0) / 100
  return (
    <div>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <h3 className="font-semibold text-sm text-text-primary truncate">{data.name}</h3>
          <p className="text-xs text-text-secondary truncate">{data.artist}</p>
        </div>
        {data.duration_ms && (
          <span className="text-xs text-text-muted shrink-0">{formatMs(data.duration_ms)}</span>
        )}
      </div>
      <AudioFeatureBar featureName="popularity" value={pop}     color="#1db954" />
      {af.energy       != null && <AudioFeatureBar featureName="energy"   value={af.energy}       color="#e91e8c" />}
      {af.danceability != null && <AudioFeatureBar featureName="dance"    value={af.danceability} color="#00d4ff" />}
    </div>
  )
}
