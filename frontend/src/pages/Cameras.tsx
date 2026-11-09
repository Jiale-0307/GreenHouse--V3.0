import { useState } from "react";
import { usePlatform } from "../data/Platform";
import { EmptyState } from "../components/EmptyState";
import { QueryNotice, Toolbar } from "../components/UI";
import { VideoPlayer } from "../components/VideoPlayer";
export function Cameras() {
  const p = usePlatform();
  const [selection, setSelection] = useState("all");
  return (
    <div className="page">
      <Toolbar title="视频监控" kicker="VIDEO / LIVE">
        <label className="compact-field">
          画面
          <select
            value={selection}
            onChange={(e) => setSelection(e.target.value)}
          >
            <option value="all">全部画面</option>
            {p.cameras.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      </Toolbar>
      <div className="info-banner">
        现场画面支持选路与全屏。配置摄像头播放地址后即可查看。
      </div>
      <QueryNotice
        error={p.cameras.error}
        loading={p.cameras.isPending}
        onRetry={() => p.cameras.refetch()}
      />
      <div className={`camera-grid ${selection !== "all" ? "single" : ""}`}>
        {p.cameras.data?.length ? (
          p.cameras.data
            .filter((c) => selection === "all" || c.id === selection)
            .map((c) => <VideoPlayer key={c.id} camera={c} />)
        ) : (
          <div className="panel">
            <EmptyState detail="暂无摄像头播放地址" />
          </div>
        )}
      </div>
    </div>
  );
}
