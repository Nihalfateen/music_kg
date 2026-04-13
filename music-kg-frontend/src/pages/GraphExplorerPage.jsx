import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'

import { getArtists, getGenreLandscape, getSimilarityEdges } from '../api'
import { hashColor, formatNumber } from '../utils/helpers'

// Dynamic import for react-force-graph-2d (heavy lib)
import ForceGraph2D from 'react-force-graph-2d'

export default function GraphExplorerPage() {
  const [artists, setArtists]     = useState([])
  const [genres, setGenres]       = useState([])
  const [loading, setLoading]     = useState(true)
  const [loadedCount, setLoaded]  = useState(500)

  const [showArtists, setShowArtists] = useState(true)
  const [showGenres,  setShowGenres]  = useState(true)
  const [showSimilar, setShowSimilar] = useState(true)
  const [minConn,     setMinConn]     = useState(0)
  const [searchQ,     setSearchQ]     = useState('')
  const [selectedNode, setSelected]   = useState(null)

  const [simEdges, setSimEdges ] = useState([])

  const graphRef = useRef()

  const fetchingRef = useRef(null)

  useEffect(() => {
    if (fetchingRef.current === artists.length) return

    fetchingRef.current = artists.length

    if (artists.length === 0) setLoading(true)

    const artistPromise = getArtists({
      limit: 500,
      offset: artists.length
    })

    const otherPromises = artists.length === 0
      ? [getGenreLandscape(), getSimilarityEdges()]
      : [Promise.resolve(null), Promise.resolve(null)]

    Promise.all([artistPromise, ...otherPromises])
      .then(([artRes, genRes, simRes]) => {
        const newArtists = artRes.data?.results || []

        if (newArtists.length === 0) {
          fetchingRef.current = null
        }

        setArtists(prev => [...prev, ...newArtists])

        if (genRes) setGenres(genRes.data?.genres || [])
        if (simRes) setSimEdges(simRes.data?.results || [])
      })
      .catch((err) => {
        console.error("API ERROR:", err)
        fetchingRef.current = null
        toast.error('Failed to load more data')
      })
      .finally(() => setLoading(false))

  }, [loadedCount])


  const graphData = useMemo(() => {
    const nodes = []
    const links = []
    const nodeSet = new Set()

    if (showGenres) {
      genres.forEach(g => {
        const cleanGenre = g.genre.toLowerCase().trim().replace(/\s+/g, '_')
        const id = `genre:${cleanGenre}`
        nodes.push({
          id,
          label: g.genre.toUpperCase(),
          type: 'genre',
          val: g.track_count ? Math.max(15, Math.sqrt(g.track_count) * 2) : 15,
          color: hashColor(g.genre),
          data: g
        })
        nodeSet.add(id)
      })
    }

    if (showArtists) {
      artists.forEach((a) => {
        const connections = (a.genres?.length || 0)
        if (connections < minConn) return

        const cleanSlug = a.slug.toLowerCase().trim()
        const id = `artist:${cleanSlug}`

        nodes.push({
          id,
          label: a.name,
          type: 'artist',
          val: 4,
          color: a.genres?.[0] ? hashColor(a.genres[0]) : '#535353',
          data: a
        })
        nodeSet.add(id)

        if (showGenres && a.genres) {
          a.genres.forEach(gName => {
            const cleanG = gName.toLowerCase().trim().replace(/\s+/g, '_')
            const gid = `genre:${cleanG}`
            if (nodeSet.has(gid)) {
              links.push({
                source: id,
                target: gid,
                color: hashColor(gName) + '33',
                width: 1
              })
            }
          })
        }
      })
    }

    if (showSimilar && showArtists) {
      simEdges.forEach(edge => {
        const sId = `artist:${edge.source.toLowerCase().trim()}`
        const tId = `artist:${edge.target.toLowerCase().trim()}`

        if (nodeSet.has(sId) && nodeSet.has(tId)) {
          links.push({
            source: sId,
            target: tId,
            color: '#1db95422',
            width: 1.5
          })
        }
      })
    }

    return { nodes, links }

  }, [artists, genres, simEdges, showArtists, showGenres, showSimilar, minConn])

  const handleNodeClick = useCallback((node) => {
    setSelected(node)
    if (graphRef.current) {
      graphRef.current.centerAt(node.x, node.y, 500)
      graphRef.current.zoom(4, 500)
    }
  }, [])

  const handleSearch = (q) => {
    setSearchQ(q)
    if (!q) return
    const node = graphData.nodes.find(n => n.label?.toLowerCase().includes(q.toLowerCase()))
    if (node && graphRef.current) {
      graphRef.current.centerAt(node.x, node.y, 500)
      graphRef.current.zoom(5, 500)
      setSelected(node)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-screen text-text-secondary">
      <div className="text-center">
        <div className="text-4xl mb-4 animate-pulse">🌐</div>
        <p>Building knowledge graph…</p>
      </div>
    </div>
  )

  return (
    <div className="relative" style={{ height: 'calc(100vh - 3.5rem)' }}>
      {/* Force Graph */}
      <ForceGraph2D
        ref={graphRef}
        graphData={graphData}
        backgroundColor="#0a0a0a"
        nodeLabel="label"
        nodeColor={n => n === selectedNode ? '#1db954' : n.color}
        nodeRelSize={4}
        nodeVal={n => n.val || 3}
        linkColor={l => l.color || '#282828'}
        linkWidth={l => l.width || 0.5}
        onNodeClick={handleNodeClick}
        nodeCanvasObject={(node, ctx, globalScale) => {
          const label = node.label
          const fontSize = Math.max(8, 12 / globalScale)
          ctx.beginPath()
          ctx.arc(node.x, node.y, node.val || 3, 0, 2 * Math.PI)
          ctx.fillStyle = node === selectedNode ? '#1db954' : node.color
          ctx.fill()

          if (globalScale > 2 || node.type === 'genre') {
            ctx.font = `${node.type === 'genre' ? 'bold ' : ''}${fontSize}px Syne, sans-serif`
            ctx.fillStyle = node.type === 'genre' ? '#fff' : '#b3b3b3'
            ctx.textAlign = 'center'
            ctx.fillText(label, node.x, node.y + (node.val || 3) + fontSize)
          }
        }}
        cooldownTicks={100}
        d3AlphaDecay={0.02}
        d3VelocityDecay={0.3}
      />

      {/* Controls overlay */}
      <div className="absolute top-4 left-4 bg-bg-secondary/95 border border-border-col rounded-card p-4 w-56 space-y-3 backdrop-blur-sm">
        <h3 className="text-xs font-bold text-text-primary uppercase tracking-wider">Controls</h3>

        <input value={searchQ} onChange={e => handleSearch(e.target.value)}
          placeholder="Search artist…"
          className="w-full bg-bg-card border border-border-col rounded text-xs px-2 py-1.5 text-text-primary placeholder-text-muted outline-none focus:border-accent" />

        <div className="space-y-2">
          {[
            ['Artists', showArtists, setShowArtists],
            ['Genres',  showGenres,  setShowGenres],
            ['Similarity edges', showSimilar, setShowSimilar],
          ].map(([label, val, set]) => (
            <label key={label} className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={val} onChange={e => set(e.target.checked)}
                className="accent-accent" />
              <span className="text-xs text-text-secondary">{label}</span>
            </label>
          ))}
        </div>

        <div>
          <p className="text-xs text-text-muted mb-1">Min connections: {minConn}</p>
          <input type="range" min={0} max={5} step={1} value={minConn}
            onChange={e => setMinConn(parseInt(e.target.value))}
            className="w-full accent-accent" />
        </div>

        <button onClick={() => graphRef.current?.zoomToFit(400)}
          className="w-full py-1.5 text-xs bg-bg-hover border border-border-col rounded hover:border-accent text-text-secondary hover:text-accent transition-all">
          Reset View
        </button>

        <button onClick={() => setLoaded(l => l + 500)}
          disabled={loading}
          className="w-full py-1.5 text-xs bg-accent/10 border border-accent/30 rounded hover:bg-accent/20 text-accent transition-all">
          {loading ? 'Fetching...' : 'Load More (+500)'}
        </button>

        <p className="text-xs text-text-muted">{graphData.nodes.length} nodes · {graphData.links.length} edges</p>
      </div>

      {/* Selected node panel */}
      <AnimatePresence>
        {selectedNode && (
          <motion.div
            initial={{ x: 320, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 320, opacity: 0 }}
            className="absolute top-4 right-4 w-72 bg-bg-secondary/95 border border-border-col rounded-card p-5 backdrop-blur-sm"
          >
            <button onClick={() => setSelected(null)}
              className="absolute top-3 right-3 text-text-muted hover:text-text-primary text-xl leading-none">×</button>

            {selectedNode.type === 'artist' && (
              <div>
                <div className="w-12 h-12 rounded-full mb-3 flex items-center justify-center text-2xl"
                  style={{ background: selectedNode.color + '33' }}>🎤</div>
                <h3 className="font-bold text-text-primary mb-1">{selectedNode.label}</h3>
                <div className="flex flex-wrap gap-1 mb-3">
                  {selectedNode.data?.genres?.map(g => (
                    <span key={g} className="px-2 py-0.5 text-xs rounded-pill"
                      style={{ background: hashColor(g) + '33', color: hashColor(g) }}>{g}</span>
                  ))}
                </div>
                <Link to={`/artist/${selectedNode.data?.slug}`}
                  className="block w-full text-center py-1.5 text-xs bg-accent text-black font-semibold rounded hover:bg-accent-hover transition-colors">
                  View Artist Profile →
                </Link>
              </div>
            )}

            {selectedNode.type === 'genre' && (
              <div>
                <div className="w-12 h-12 rounded-full mb-3 flex items-center justify-center text-2xl"
                  style={{ background: selectedNode.color + '33' }}>🎸</div>
                <h3 className="font-bold text-text-primary mb-1 capitalize">{selectedNode.label}</h3>
                <div className="space-y-2 text-xs text-text-secondary mt-3">
                  <div className="flex justify-between">
                    <span className="text-text-muted">Artists</span>
                    <span>{formatNumber(selectedNode.data?.artist_count)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">Tracks</span>
                    <span>{formatNumber(selectedNode.data?.track_count)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">Avg Energy</span>
                    <span>{selectedNode.data?.avg_energy?.toFixed(3) ?? '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-muted">Avg Danceability</span>
                    <span>{selectedNode.data?.avg_danceability?.toFixed(3) ?? '—'}</span>
                  </div>
                </div>
                <Link to={`/search?genre=${encodeURIComponent(selectedNode.label)}`}
                  className="block w-full text-center py-1.5 text-xs bg-accent text-black font-semibold rounded hover:bg-accent-hover transition-colors mt-4">
                  Browse {selectedNode.label} →
                </Link>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
