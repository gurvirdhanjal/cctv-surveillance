import { Component, type ErrorInfo, type PropsWithChildren } from 'react'

interface State {
  error: Error | null
}

interface Props extends PropsWithChildren {
  fallback?: (error: Error, reset: () => void) => React.ReactNode
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info)
  }

  reset = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (error) {
      return this.props.fallback ? (
        this.props.fallback(error, this.reset)
      ) : (
        <div
          role="alert"
          className="flex min-h-screen flex-col items-center justify-center gap-4 bg-surface-base p-8 text-center"
        >
          <p className="text-[18px] font-semibold text-text-primary">Something went wrong.</p>
          <p className="text-[14px] text-text-secondary">{error.message}</p>
          <button
            onClick={this.reset}
            className="rounded-md bg-brand-500 px-4 py-2 text-[14px] font-medium text-white hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
