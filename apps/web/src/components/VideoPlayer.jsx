/**
 * Player for an uploaded (private) video.
 *
 * The <video> src is never a stored file path: the component exchanges the
 * item id for a short-lived signed ticket and plays that. The ticket is tied
 * to the signed-in viewer, so copying the URL out of devtools gets a stranger
 * nothing, and it expires in minutes.
 *
 * `onProgress` is called with (positionSeconds, durationSeconds) at most once
 * every few seconds so viewing activity is recorded without hammering the API.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Loader } from "lucide-react";
import { BASE_URL, getActiveEnvironmentId, getTokens } from "../lib/api.js";

const SAVE_EVERY_MS = 5000;

export default function VideoPlayer({ itemId, ticketFor, onProgress, startAt = 0, poster }) {
  const [src, setSrc] = useState(null);
  const [error, setError] = useState(null);
  const videoRef = useRef(null);
  const lastSaved = useRef(0);

  useEffect(() => {
    let alive = true;
    setSrc(null); setError(null);
    ticketFor(itemId)
      .then((d) => {
        if (!alive) return;
        // The stream endpoint authenticates with the same bearer token the
        // rest of the app uses; the ticket authorises this one item.
        const params = new URLSearchParams({ t: d.ticket });
        setSrc(`${BASE_URL}/content/stream/?${params}`);
      })
      .catch(() => alive && setError("تعذّر تجهيز الفيديو. قد لا يكون متاحًا لك."));
    return () => { alive = false; };
  }, [itemId, ticketFor]);

  // <video> cannot send an Authorization header, so fetch the stream and feed
  // the player a blob URL — the bytes still come from the protected endpoint.
  const [blobUrl, setBlobUrl] = useState(null);
  useEffect(() => {
    if (!src) return undefined;
    let alive = true;
    let objectUrl = null;
    const headers = {};
    const tokens = getTokens();
    if (tokens?.access) headers.Authorization = `Bearer ${tokens.access}`;
    const envId = getActiveEnvironmentId();
    if (envId) headers["X-Madar-Environment"] = String(envId);

    fetch(src, { headers })
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.blob(); })
      .then((b) => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(b);
        setBlobUrl(objectUrl);
      })
      .catch(() => alive && setError("تعذّر تشغيل الفيديو."));
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [src]);

  const handleTime = useCallback((e) => {
    const el = e.currentTarget;
    const now = Date.now();
    if (now - lastSaved.current < SAVE_EVERY_MS) return;
    lastSaved.current = now;
    onProgress?.(Math.floor(el.currentTime), Math.floor(el.duration || 0));
  }, [onProgress]);

  const handleEnded = useCallback((e) => {
    const el = e.currentTarget;
    onProgress?.(Math.floor(el.duration || 0), Math.floor(el.duration || 0));
  }, [onProgress]);

  const onLoaded = useCallback((e) => {
    if (startAt > 0 && startAt < (e.currentTarget.duration || 0)) {
      e.currentTarget.currentTime = startAt;  // resume where they stopped
    }
  }, [startAt]);

  if (error) {
    return <div className="player-state err"><AlertCircle size={18} /> {error}</div>;
  }
  if (!blobUrl) {
    return <div className="player-state"><Loader size={18} className="ai-spin" /> جارٍ تجهيز الفيديو…</div>;
  }
  return (
    <video
      ref={videoRef}
      className="player"
      src={blobUrl}
      poster={poster}
      controls
      playsInline
      controlsList="nodownload"
      onContextMenu={(e) => e.preventDefault()}
      onLoadedMetadata={onLoaded}
      onTimeUpdate={handleTime}
      onEnded={handleEnded}
    />
  );
}
