import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'
import { postSparql, getSparqlTemplates } from '../api'

const DEFAULT_QUERY = `PREFIX music: <http://musickg.org/ontology#>
PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?name ?popularity
WHERE {
  ?uri a music:Artist ;
       music:artistName ?name .
  ?track music:performedBy ?uri ;
         music:popularity ?popularity .
}
ORDER BY DESC(?popularity)
LIMIT 10`

function LineNumbers({ text }) {
  const lines = text.split('\n').length
  return (
    <div className="select-none text-right pr-3 pt-4 font-mono text-xs text-text-muted leading-relaxed min-w-8">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i}>{i + 1}</div>
      ))}
    </div>
  )
}

export default function SPARQLEditorPage() {
  const [query, setQuery]       = useState(DEFAULT_QUERY)
  const [results, setResults]   = useState(null)
  const [loading, setLoading]   = useState(false)
  const [templates, setTemplates] = useState([])
  const [sortCol, setSortCol]   = useState(null)
  const [sortAsc, setSortAsc]   = useState(true)
  const textareaRef = useRef(null)

  useEffect(() => {
    getSparqlTemplates()
      .then(r => setTemplates(r.data?.templates || []))
      .catch(() => {})
  }, [])

  const runQuery = async () => {
    if (!query.trim()) return
    setLoading(true)
    setResults(null)
    try {
      const res = await postSparql(query)
      setResults(res.data)
      if (res.data?.error) {
        toast.error(res.data.error)
      } else {
        toast.success(`${res.data.rows?.length || 0} rows in ${res.data.execution_time_ms}ms`)
      }
    } catch (e) {
      toast.error('Query failed — check your SPARQL syntax')
      setResults({ error: e.response?.data?.error || 'Unknown error', rows: [], columns: [] })
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      runQuery()
    }
    // Tab support
    if (e.key === 'Tab') {
      e.preventDefault()
      const s = e.target.selectionStart
      const v = query
      setQuery(v.substring(0, s) + '  ' + v.substring(e.target.selectionEnd))
      setTimeout(() => { e.target.selectionStart = e.target.selectionEnd = s + 2 }, 0)
    }
  }

  const exportCSV = () => {
    if (!results?.rows?.length) return
    const cols = results.columns
    const lines = [
      cols.join(','),
      ...results.rows.map(r => cols.map(c => `"${r[c] ?? ''}"`).join(','))
    ]
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'sparql-results.csv'; a.click()
    URL.revokeObjectURL(url)
  }

  const exportJSON = () => {
    if (!results?.rows?.length) return
    const blob = new Blob([JSON.stringify(results.rows, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'sparql-results.json'; a.click()
    URL.revokeObjectURL(url)
  }

  const sortedRows = results?.rows ? [...results.rows].sort((a, b) => {
    if (!sortCol) return 0
    const va = a[sortCol] ?? ''
    const vb = b[sortCol] ?? ''
    return sortAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va))
  }) : []

  const SAMPLE_QUERIES = [
    { label: 'All artists in Pop', query: `PREFIX music: <http://musickg.org/ontology#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n\nSELECT DISTINCT ?name WHERE {\n  ?uri a music:Artist ; music:artistName ?name .\n  ?track music:performedBy ?uri ; music:inGenre ?g .\n  ?g rdfs:label "pop" .\n} LIMIT 20` },
    { label: 'High energy tracks', query: `PREFIX music: <http://musickg.org/ontology#>\n\nSELECT ?name ?energy WHERE {\n  ?t a music:Track ; music:trackName ?name ;\n     music:hasAudioFeatures ?af .\n  ?af music:energy ?energy .\n  FILTER (?energy > 0.9)\n} ORDER BY DESC(?energy) LIMIT 20` },
    { label: 'Genre stats', query: `PREFIX music: <http://musickg.org/ontology#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n\nSELECT ?genre (COUNT(?t) AS ?tracks) WHERE {\n  ?g a music:Genre ; rdfs:label ?genre .\n  ?t music:inGenre ?g .\n} GROUP BY ?genre ORDER BY DESC(?tracks)` },
  ]

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <motion.h1 className="text-3xl font-extrabold text-text-primary mb-6"
        initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        SPARQL Editor
      </motion.h1>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Editor — 60% */}
        <div className="lg:col-span-3 flex flex-col gap-3">
          {/* Template selector */}
          <div className="flex gap-2">
            <select defaultValue=""
              onChange={e => { if (e.target.value) setQuery(e.target.value) }}
              className="flex-1 bg-bg-card border border-border-col rounded text-xs text-text-secondary px-3 py-2 outline-none">
              <option value="">Load template…</option>
              {templates.map(t => (
                <option key={t.id} value={t.query_text}>{t.name}</option>
              ))}
              {SAMPLE_QUERIES.map(t => (
                <option key={t.label} value={t.query}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Editor with line numbers */}
          <div className="bg-[#0d1117] border border-border-col rounded-card overflow-hidden">
            <div className="flex">
              <LineNumbers text={query} />
              <textarea
                ref={textareaRef}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                className="sparql-editor flex-1 border-0 rounded-none"
                style={{ minHeight: 320, borderLeft: '1px solid #282828', paddingLeft: 12 }}
                spellCheck={false}
              />
            </div>
            <div className="flex items-center justify-between px-4 py-2 border-t border-border-col bg-bg-secondary">
              <span className="text-xs text-text-muted font-mono">Ctrl+Enter to run</span>
              <div className="flex gap-2">
                <button onClick={() => setQuery('')}
                  className="text-xs text-text-muted hover:text-text-secondary transition-colors px-2 py-1">
                  Clear
                </button>
                <button onClick={() => { navigator.clipboard.writeText(query); toast.success('Copied!') }}
                  className="text-xs text-text-muted hover:text-text-secondary transition-colors px-2 py-1">
                  Copy
                </button>
                <button onClick={runQuery} disabled={loading}
                  className="px-4 py-1.5 bg-accent text-black font-bold text-xs rounded hover:bg-accent-hover transition-colors disabled:opacity-50">
                  {loading ? 'Running…' : '▶ Run Query'}
                </button>
              </div>
            </div>
          </div>

          {/* Ontology info */}
          <details className="bg-bg-card border border-border-col rounded-card p-4">
            <summary className="text-xs font-semibold text-text-muted uppercase tracking-wider cursor-pointer hover:text-text-primary transition-colors">
              About the Knowledge Graph
            </summary>
            <div className="mt-3 space-y-2 text-xs text-text-secondary font-mono">
              <p>PREFIX music: &lt;http://musickg.org/ontology#&gt;</p>
              <p>PREFIX base:  &lt;http://musickg.org/&gt;</p>
              <p>PREFIX schema:&lt;http://schema.org/&gt;</p>
              <p className="text-text-muted mt-2">Classes: music:Artist, music:Album, music:Track, music:Genre, music:AudioFeatures</p>
              <p className="text-text-muted">Properties: music:artistName, music:trackName, music:albumName, music:inGenre, music:performedBy, music:similarTo, music:hasAudioFeatures</p>
              <p className="text-text-muted">Audio features: music:energy, music:danceability, music:valence, music:tempo, music:loudness (all 0–1 normalised)</p>
            </div>
          </details>
        </div>

        {/* Results — 40% */}
        <div className="lg:col-span-2 flex flex-col gap-3">
          {results ? (
            <>
              {results.error ? (
                <div className="bg-red-950/30 border border-red-800/50 rounded-card p-4">
                  <p className="text-xs font-semibold text-red-400 mb-1">Query Error</p>
                  <p className="text-xs text-red-300 font-mono">{results.error}</p>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-text-muted">
                      <span className="text-accent font-semibold">{sortedRows.length}</span> rows
                      {results.execution_time_ms && (
                        <span className="ml-2">· {results.execution_time_ms}ms</span>
                      )}
                    </p>
                    <div className="flex gap-1">
                      <button onClick={exportCSV} className="px-2 py-1 text-xs bg-bg-card border border-border-col rounded hover:border-accent text-text-secondary hover:text-accent transition-all">CSV</button>
                      <button onClick={exportJSON} className="px-2 py-1 text-xs bg-bg-card border border-border-col rounded hover:border-accent text-text-secondary hover:text-accent transition-all">JSON</button>
                    </div>
                  </div>

                  <div className="bg-bg-card border border-border-col rounded-card overflow-auto" style={{ maxHeight: 480 }}>
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-bg-secondary border-b border-border-col">
                        <tr>
                          {results.columns?.map(col => (
                            <th key={col}
                              onClick={() => { setSortCol(col); setSortAsc(sortCol === col ? !sortAsc : true) }}
                              className="text-left px-3 py-2 text-text-muted uppercase tracking-wider cursor-pointer hover:text-accent transition-colors whitespace-nowrap">
                              {col} {sortCol === col ? (sortAsc ? '↑' : '↓') : ''}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {sortedRows.map((row, i) => (
                          <tr key={i} className="border-b border-border-col/30 hover:bg-bg-hover transition-colors">
                            {results.columns?.map(col => (
                              <td key={col} className="px-3 py-2 text-text-secondary font-mono max-w-48 truncate">
                                {row[col] != null ? String(row[col]) : <span className="text-text-muted">—</span>}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {sortedRows.length === 0 && (
                      <p className="text-center text-text-muted text-xs py-8">No results</p>
                    )}
                  </div>
                </>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-64 text-center bg-bg-card border border-border-col rounded-card">
              <div className="text-4xl mb-3 opacity-30">⚡</div>
              <p className="text-sm text-text-muted">Run a query to see results</p>
              <p className="text-xs text-text-muted mt-1">Press Ctrl+Enter or click Run</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
