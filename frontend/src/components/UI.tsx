import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { resourceError } from "../data/Platform";
export function QueryNotice({
  error,
  loading,
  onRetry,
}: {
  error?: Error | null;
  loading?: boolean;
  onRetry?: () => void;
}) {
  return loading ? (
    <div className="query-notice" role="status">
      <span className="spinner small" />
      正在请求数据
    </div>
  ) : error ? (
    <div className="query-notice" role="status">
      {resourceError(error)}
      {onRetry && (
        <button className="text-button" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  ) : null;
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => {
      dialog.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="modal-head">
        <h3>{title}</h3>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="关闭对话框"
        >
          <X size={17} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Toolbar({
  title,
  kicker,
  children,
}: {
  title: string;
  kicker: string;
  children?: ReactNode;
}) {
  return (
    <div className="toolbar">
      <div>
        <span className="eyebrow" aria-hidden="true" data-label={kicker}>
          装备运行管理
        </span>
        <h2>{title}</h2>
      </div>
      {children}
    </div>
  );
}
export function Pagination({
  page,
  setPage,
  total,
  count,
}: {
  page: number;
  setPage: (n: number) => void;
  total: number | null | undefined;
  count: number;
}) {
  return (
    <div className="pagination">
      <button disabled={page === 1} onClick={() => setPage(page - 1)}>
        上一页
      </button>
      <span>
        第 {page} 页 · 共 {total ?? "—"} 条
      </span>
      <button
        disabled={count < 20 || (total != null && page * 20 >= total)}
        onClick={() => setPage(page + 1)}
      >
        下一页
      </button>
    </div>
  );
}
