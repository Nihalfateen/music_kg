import axios from 'axios'

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 60000,  // 60s — first search builds the in-memory index (~2-5s)
  headers: { 'Content-Type': 'application/json' },
})

// Request interceptor — log timing
api.interceptors.request.use((config) => {
  config._t0 = Date.now()
  return config
})

// Response interceptor — unwrap paginated
api.interceptors.response.use(
  (res) => {
    const elapsed = Date.now() - (res.config._t0 || Date.now())
    if (process.env.NODE_ENV === 'development') {
      console.debug(`[API] ${res.config.method?.toUpperCase()} ${res.config.url} → ${res.status} (${elapsed}ms)`)
    }
    return res
  },
  (err) => {
    console.error('[API Error]', err.response?.data || err.message)
    return Promise.reject(err)
  }
)

export const getStats          = ()           => api.get('/stats/')
export const getArtists        = (params)     => api.get('/artists/', { params })
export const getArtistDetail   = (slug)       => api.get(`/artists/${encodeURIComponent(slug)}/`)
export const getAlbumDetail    = (slug)       => api.get(`/albums/${encodeURIComponent(slug)}/`)
export const getTracks         = (params)     => api.get('/tracks/', { params })
export const searchAll         = (q, params)  => api.get('/search/', { params: { q, ...params } })
export const postSparql        = (query)      => api.post('/sparql/', { query })
export const getTimeline       = (params)     => api.get('/timeline/', { params })
export const getGenreEvolution = (genre)      => api.get(`/timeline/${encodeURIComponent(genre)}/`)
export const getGenreLandscape = ()           => api.get('/genre-landscape/')
export const getAudioDistribution = ()        => api.get('/audio-distribution/')
export const getSparqlTemplates   = (params)  => api.get('/sparql-templates/', { params })
export const getRecommendations   = (slug)    => api.get(`/recommendations/${encodeURIComponent(slug)}/`)
export const createArtist = (data) => api.post('/artists/create/', data)

export default api