import { Component, type ErrorInfo, type ReactNode } from "react";
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(_error: Error, _info: ErrorInfo) {
    /* 不记录响应载荷或播放签名地址，避免将敏感信息写入日志。 */
  }
  render() {
    return this.state.failed ? (
      <div className="page empty" role="alert">
        <h2>页面暂时无法显示</h2>
        <p>请重新加载页面；尚未确认的设备动作请先查询操作日志。</p>
        <button
          className="primary-button"
          onClick={() => window.location.reload()}
        >
          重新加载
        </button>
      </div>
    ) : (
      this.props.children
    );
  }
}
