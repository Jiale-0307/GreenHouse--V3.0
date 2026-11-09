import { useEffect, useRef, useState } from "react";
import { Camera as CameraIcon, Maximize } from "lucide-react";
import Hls from "hls.js";
import type { Camera } from "../sdk";
export function VideoPlayer({ camera }: { camera: Camera }) {
  const ref = useRef<HTMLVideoElement>(null);
  const container = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const video = ref.current;
    setError("");
    if (!video || !camera.playbackUrl) return;
    let hls: Hls | undefined;
    if (
      camera.protocol === "hls" &&
      !video.canPlayType("application/vnd.apple.mpegurl") &&
      Hls.isSupported()
    ) {
      hls = new Hls();
      hls.loadSource(camera.playbackUrl);
      hls.attachMedia(video);
      hls.on(Hls.Events.ERROR, (_, data) => {
        if (data.fatal) setError("视频连接失败，请重试");
      });
    } else if (
      camera.protocol === "mp4" ||
      video.canPlayType("application/vnd.apple.mpegurl")
    )
      video.src = camera.playbackUrl;
    else setError("当前浏览器不支持此播放格式");
    return () => {
      hls?.destroy();
      video.pause();
      video.removeAttribute("src");
      video.load();
    };
  }, [camera.playbackUrl, camera.protocol]);
  return (
    <div className="camera-card" ref={container}>
      <div className="video-box">
        {camera.playbackUrl ? (
          <video
            ref={ref}
            controls
            playsInline
            onError={() => setError("视频加载失败，检查播放地址与权限")}
          />
        ) : (
          <>
            <CameraIcon size={30} />
            <b>未接入</b>
            <small>播放地址未配置</small>
          </>
        )}
        {error && (
          <div className="video-error" role="alert">
            {error}
          </div>
        )}
      </div>
      <div className="camera-caption">
        <div>
          <b>{camera.name}</b>
          <small>{camera.protocol || "未配置"}</small>
        </div>
        <span
          className={`connection ${camera.online === true ? "connected" : ""}`}
        >
          {camera.online === true
            ? "在线"
            : camera.online === false
              ? "离线"
              : "状态未知"}
        </span>
        <button
          className="icon-button"
          aria-label={`${camera.name}全屏`}
          onClick={() =>
            container.current
              ?.requestFullscreen()
              .catch(() => setError("无法进入全屏"))
          }
        >
          <Maximize size={15} />
        </button>
      </div>
    </div>
  );
}
