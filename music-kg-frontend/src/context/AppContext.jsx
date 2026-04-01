import React, { createContext, useContext, useState, useEffect } from 'react'
import { getStats } from '../api'

const AppContext = createContext(null)

export function AppProvider({ children }) {
  const [stats, setStats]               = useState({})
  const [recentSearches, setRecent]     = useState([])
  const [selectedGenres, setGenres]     = useState([])

  useEffect(() => {
    getStats()
      .then(r => setStats(r.data))
      .catch(() => {})
  }, [])

  const addRecentSearch = (q) => {
    if (!q.trim()) return
    setRecent(prev => {
      const filtered = prev.filter(s => s !== q)
      return [q, ...filtered].slice(0, 10)
    })
  }

  return (
    <AppContext.Provider value={{
      stats,
      recentSearches,
      addRecentSearch,
      selectedGenres,
      setSelectedGenres: setGenres,
    }}>
      {children}
    </AppContext.Provider>
  )
}

export const useApp = () => useContext(AppContext)
