import { Routes, Route } from 'react-router-dom'

import Navbar from './components/layout/Navbar'
import { ErrorBoundary } from './components/common/ErrorBoundary'
import { Suspense, lazy } from 'react'
import { PageSkeleton } from './components/common/LoadingSkeleton'

const HomePage          = lazy(() => import('./pages/HomePage'))
const SearchPage        = lazy(() => import('./pages/SearchPage'))
const ArtistDetailPage  = lazy(() => import('./pages/ArtistDetailPage'))
const AlbumDetailPage   = lazy(() => import('./pages/AlbumDetailPage'))
const TimelinePage      = lazy(() => import('./pages/TimelinePage'))
const GraphExplorerPage = lazy(() => import('./pages/GraphExplorerPage'))
const AnalyticsPage     = lazy(() => import('./pages/AnalyticsPage'))

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen text-center">
      <div className="text-6xl mb-4">🎵</div>
      <h1 className="text-2xl font-bold text-text-primary mb-2">404 — Page Not Found</h1>
      <p className="text-text-secondary mb-6">This track doesn't exist in the knowledge graph.</p>
      <a href="/" className="px-6 py-2 bg-accent text-black font-semibold rounded-btn hover:bg-accent-hover transition-colors">
        Back to Explore
      </a>
    </div>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-bg-primary">
      <Navbar />
      <main className="pt-14">
        <ErrorBoundary>
          <Suspense fallback={<PageSkeleton />}>
            <Routes>
              <Route path="/"            element={<HomePage />} />
              <Route path="/search"      element={<SearchPage />} />
              <Route path="/artist/:slug" element={<ArtistDetailPage />} />
              <Route path="/album/:slug"  element={<AlbumDetailPage />} />
              <Route path="/timeline"    element={<TimelinePage />} />
              <Route path="/graph"       element={<GraphExplorerPage />} />
              <Route path="/analytics"   element={<AnalyticsPage />} />
              <Route path="*"            element={<NotFound />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>
    </div>
  )
}
