export function EmptyState({
  title = "暂无数据",
  detail,
}: {
  title?: string;
  detail?: string;
}) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {detail && <span>{detail}</span>}
    </div>
  );
}
export function Loading({ label = "加载中" }: { label?: string }) {
  return (
    <div className="loading">
      <span className="spinner" />
      {label}
    </div>
  );
}
