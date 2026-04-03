import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

interface Props {
  children: ReactNode;
  /** Optional label shown in the error card so user knows which section failed */
  section?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Catches render errors in child tree and shows a recovery card
 * instead of crashing the entire app. Wrap around each route or
 * major feature section.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[ErrorBoundary${this.props.section ? `: ${this.props.section}` : ""}]`, error, info.componentStack);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center min-h-[300px] p-8">
          <div className="neu-flat p-8 max-w-md w-full text-center space-y-4">
            <div className="neu-pressed w-14 h-14 rounded-2xl flex items-center justify-center mx-auto">
              <AlertTriangle className="w-7 h-7 text-amber-500" />
            </div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Algo salio mal
            </h2>
            {this.props.section && (
              <p className="text-sm text-[var(--text-muted)]">
                Error en: {this.props.section}
              </p>
            )}
            <p className="text-sm text-[var(--text-secondary)]">
              {this.state.error?.message ?? "Error inesperado"}
            </p>
            <button
              onClick={this.handleRetry}
              className="inline-flex items-center gap-2 px-5 py-2.5 neu-sm text-sm font-medium text-indigo-500 hover:text-indigo-600 transition-colors mx-auto"
            >
              <RotateCcw className="w-4 h-4" />
              Reintentar
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
