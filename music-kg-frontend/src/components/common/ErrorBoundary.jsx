import React from 'react'

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center p-12 text-center">
          <div className="text-4xl mb-4">⚠️</div>
          <h2 className="text-lg font-semibold text-text-primary mb-2">Something went wrong</h2>
          <p className="text-sm text-text-secondary mb-4">{this.state.error?.message}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="px-4 py-2 bg-accent text-black font-semibold rounded-btn text-sm hover:bg-accent-hover transition-colors"
          >
            Try Again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
