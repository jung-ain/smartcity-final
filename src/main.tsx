import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles.css';
import 'maplibre-gl/dist/maplibre-gl.css';

class AppErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; message: string }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, message: '' };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, message: error?.message ?? '알 수 없는 오류' };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-screen">
          <h1>대시보드 로딩 오류</h1>
          <p>화면을 불러오는 중 문제가 발생했습니다. 브라우저 콘솔에서 상세 메시지를 확인해 주세요.</p>
          <pre>{this.state.message}</pre>
        </div>
      );
    }

    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <AppErrorBoundary>
    <App />
  </AppErrorBoundary>,
);
