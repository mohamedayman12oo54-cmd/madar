/**
 * Player for an uploaded (private) video.
 *
 * The src is a signed, short-lived ticket URL — NOT a stored file path. That
 * matters for more than security: because the URL authenticates itself, the
 * browser streams it natively with Range requests, so playback starts at once
 * and seeking works. (The earlier version fetched the WHOLE file into a blob
 * just to attach an auth header, which meant waiting for the entire video
 * before anything played.)
 *
 * `onProgress(position, duration)` is throttled so viewing activity is
 * recorded without hammering the API.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Loader,
  Play,
  Pause,
  RotateCcw,
  RotateCw,
  Gauge,
  Settings2,
  Maximize,
  Minimize,
  Check,
} from "lucide-react";
import { BASE_URL } from "../lib/api.js";

const SAVE_EVERY_MS = 5000;
const SKIP_SECONDS = 5;
const HIDE_AFTER_MS = 5000;
const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];
const AUTO = "auto";

const fmt = (t) => {
  if (!Number.isFinite(t) || t < 0) t = 0;
  const h = Math.floor(t / 3600),
    m = Math.floor((t % 3600) / 60),
    s = Math.floor(t % 60);
  const mm = String(m).padStart(h ? 2 : 1, "0"),
    ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};

export default function VideoPlayer({ itemId, ticketFor, onProgress, startAt = 0, poster }) {
  const [src, setSrc] = useState(null);
  const [qualities, setQualities] = useState([]); // [{ label, ticket? }] — from the API when available
  const [quality, setQuality] = useState(AUTO);
  const [error, setError] = useState(null);
  const [speed, setSpeed] = useState(1);
  const [shown, setShown] = useState(true); // controls overlay visible?
  const [notice, setNotice] = useState(null); // soft, non-fatal message (e.g. quality switch failed)
  const [menu, setMenu] = useState(null); // null | "speed" | "quality"
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [full, setFull] = useState(false);
  const frameRef = useRef(null);
  const videoRef = useRef(null);
  const lastSaved = useRef(0);
  const resumed = useRef(false);
  const hideTimer = useRef(null);
  const overBar = useRef(false); // pointer is on the controls
  const menuOpen = useRef(false);
  const pending = useRef(null); // { time, play } restored after a quality switch
  const shownRef = useRef(true); // mirror of `shown`, readable inside event handlers
  const wasShownOnTouch = useRef(true); // were the controls already visible when the finger landed?

  const streamUrl = (d) => `${BASE_URL}/content/stream/?${new URLSearchParams({ t: d.ticket })}`;

  useEffect(() => {
    let alive = true;
    setSrc(null);
    setError(null);
    setQualities([]);
    setQuality(AUTO);
    resumed.current = false;
    pending.current = null;
    ticketFor(itemId)
      .then((d) => {
        if (!alive) return;
        setQualities(Array.isArray(d.qualities) ? d.qualities : []);
        setSrc(streamUrl(d));
      })
      .catch(() => alive && setError("تعذّر تجهيز الفيديو. قد لا يكون متاحًا لك."));
    return () => {
      alive = false;
    };
  }, [itemId, ticketFor]);

  // Controls appear on any pointer/touch/key activity and fade after 5s of
  // stillness — but never while a popup is open or the pointer is on the bar.
  const wake = useCallback(() => {
    setShown(true);
    clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(function tick() {
      if (overBar.current || menuOpen.current) {
        hideTimer.current = setTimeout(tick, 1000);
        return;
      }
      setShown(false);
    }, HIDE_AFTER_MS);
  }, []);
  useEffect(() => {
    shownRef.current = shown;
  }, [shown]);
  useEffect(() => {
    wake();
    return () => clearTimeout(hideTimer.current);
  }, [wake]);
  useEffect(() => {
    menuOpen.current = menu !== null;
    if (menu === null) wake();
  }, [menu, wake]);
  const sleepNow = useCallback(() => {
    // pointer left the player
    clearTimeout(hideTimer.current);
    if (!menuOpen.current) setShown(false);
  }, []);

  const changeSpeed = useCallback((value) => {
    setSpeed(value);
    setMenu(null);
    if (videoRef.current) videoRef.current.playbackRate = value;
  }, []);

  // Switching quality swaps the source, then restores the position and play state.
  const changeQuality = useCallback(
    async (value) => {
      setMenu(null);
      setNotice(null);
      if (value === quality) return;
      const el = videoRef.current;
      pending.current = { time: el?.currentTime || 0, play: el ? !el.paused : false };
      try {
        const d = await ticketFor(itemId, value === AUTO ? undefined : value);
        setQuality(value);
        setSrc(streamUrl(d));
      } catch {
        // The current video is still fine — keep playing it and just say so.
        pending.current = null;
        setNotice("تعذّر تغيير الجودة. حاول مرة أخرى.");
      }
    },
    [quality, itemId, ticketFor]
  );

  const skip = useCallback((delta) => {
    const el = videoRef.current;
    if (!el) return;
    const max = Number.isFinite(el.duration) ? el.duration : Infinity;
    el.currentTime = Math.min(max, Math.max(0, el.currentTime + delta));
  }, []);

  const toggle = useCallback(() => {
    const el = videoRef.current;
    if (!el) return;
    el.paused ? el.play().catch(() => {}) : el.pause();
  }, []);

  const toggleFull = useCallback(() => {
    const f = frameRef.current;
    if (!f) return;
    if (document.fullscreenElement) document.exitFullscreen?.();
    else (f.requestFullscreen || f.webkitRequestFullscreen)?.call(f);
  }, []);

  useEffect(() => {
    const on = () => setFull(document.fullscreenElement === frameRef.current);
    document.addEventListener("fullscreenchange", on);
    return () => document.removeEventListener("fullscreenchange", on);
  }, []);

  // Touch screens behave like YouTube: a tap on a video whose controls are
  // hidden only REVEALS them; a tap while they are visible toggles play/pause.
  // Mouse users (and tests) keep click = play/pause.
  const onVideoTap = useCallback(() => {
    setMenu(null);
    const touch =
      typeof window !== "undefined" &&
      window.matchMedia?.("(hover: none) and (pointer: coarse)").matches;
    if (touch && !wasShownOnTouch.current) {
      wasShownOnTouch.current = true;
      wake();
      return;
    }
    toggle();
    wake();
  }, [toggle, wake]);

  const handleTime = useCallback(
    (e) => {
      const el = e.currentTarget;
      setTime(el.currentTime);
      const now = Date.now();
      if (now - lastSaved.current < SAVE_EVERY_MS) return;
      lastSaved.current = now;
      onProgress?.(Math.floor(el.currentTime), Math.floor(el.duration || 0));
    },
    [onProgress]
  );

  const handleEnded = useCallback(
    (e) => {
      const d = Math.floor(e.currentTarget.duration || 0);
      onProgress?.(d, d);
    },
    [onProgress]
  );

  const onLoaded = useCallback(
    (e) => {
      const el = e.currentTarget;
      setDuration(el.duration || 0);
      el.playbackRate = speed;
      if (pending.current) {
        // after a quality switch
        el.currentTime = pending.current.time;
        if (pending.current.play) el.play().catch(() => {});
        pending.current = null;
      } else if (!resumed.current && startAt > 0 && startAt < (el.duration || 0) - 5) {
        el.currentTime = startAt; // resume once, not at the very end
      }
      resumed.current = true;
    },
    [speed, startAt]
  );

  // Shortcuts: space/k play-pause, arrows seek 5s, j/l seek 10s, f fullscreen.
  // Arrow direction is mirrored because the interface is RTL.
  const onKeyDown = useCallback(
    (e) => {
      wake();
      if (e.target.tagName === "INPUT") return;
      const key = e.key.toLowerCase();
      const seek = { arrowright: -SKIP_SECONDS, arrowleft: SKIP_SECONDS, j: -10, l: 10 };
      if (key === " " || key === "k") {
        e.preventDefault();
        toggle();
      } else if (key in seek) {
        e.preventDefault();
        skip(seek[key]);
      } else if (key === "f") {
        e.preventDefault();
        toggleFull();
      } else if (key === "escape") setMenu(null);
    },
    [toggle, skip, toggleFull, wake]
  );

  if (error)
    return (
      <div className="player-state err">
        <AlertCircle size={18} /> {error}
      </div>
    );
  if (!src)
    return (
      <div className="player-state">
        <Loader size={18} className="ai-spin" /> جارٍ تجهيز الفيديو…
      </div>
    );

  const qualityOptions = [
    { label: "تلقائي", value: AUTO },
    ...qualities.map((q) => ({ label: q.label, value: q.label })),
  ];
  const qualityLabel = qualityOptions.find((o) => o.value === quality)?.label || "تلقائي";

  return (
    <div
      className={"player-frame" + (full ? " is-full" : "") + (shown ? "" : " is-idle")}
      ref={frameRef}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onMouseMove={wake}
      onMouseEnter={wake}
      onMouseLeave={sleepNow}
      onTouchStart={() => {
        wasShownOnTouch.current = shownRef.current;
        wake();
      }}
    >
      <video
        ref={videoRef}
        className="player"
        src={src}
        poster={poster}
        playsInline
        preload="metadata"
        onClick={onVideoTap}
        onContextMenu={(e) => e.preventDefault()}
        onLoadedMetadata={onLoaded}
        onTimeUpdate={handleTime}
        onDurationChange={(e) => setDuration(e.currentTarget.duration || 0)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={(e) => {
          setPlaying(false);
          handleEnded(e);
        }}
        onError={() => setError("تعذّر تشغيل الفيديو. حدّث الصفحة وحاول مرة أخرى.")}
      />
      {!playing && !shown && (
        <div className="player-bigplay" aria-hidden="true">
          <Play size={34} />
        </div>
      )}
      {notice && (
        <div className="player-notice" role="status">
          {notice}
        </div>
      )}
      <div
        className={"player-controls" + (shown ? " is-shown" : "")}
        onMouseEnter={() => {
          overBar.current = true;
        }}
        onMouseLeave={() => {
          overBar.current = false;
        }}
      >
        <div className="player-seekrow" dir="ltr">
          <input
            type="range"
            className="player-seek"
            min={0}
            max={duration || 0}
            step={0.1}
            value={Math.min(time, duration || 0)}
            aria-label="موضع التشغيل"
            style={{ "--p": duration ? `${(time / duration) * 100}%` : "0%" }}
            onChange={(e) => {
              const v = Number(e.target.value);
              setTime(v);
              if (videoRef.current) videoRef.current.currentTime = v;
            }}
          />
        </div>
        <div className="player-row">
          <div className="pc-group pc-start">
            <button
              type="button"
              className="pc-btn pc-icon"
              onClick={toggle}
              aria-label={playing ? "إيقاف مؤقت" : "تشغيل"}
            >
              {playing ? <Pause size={20} /> : <Play size={20} />}
            </button>
            {/* Laid out left→right like the timeline: back on the left, forward on the right. */}
            <div className="pc-skips" dir="ltr">
              <button
                type="button"
                className="pc-btn pc-icon pc-skip"
                onClick={() => skip(-SKIP_SECONDS)}
                aria-label={`رجوع ${SKIP_SECONDS} ثواني`}
              >
                <RotateCcw size={20} />
                <span>{SKIP_SECONDS}</span>
              </button>
              <button
                type="button"
                className="pc-btn pc-icon pc-skip"
                onClick={() => skip(SKIP_SECONDS)}
                aria-label={`تقديم ${SKIP_SECONDS} ثواني`}
              >
                <RotateCw size={20} />
                <span>{SKIP_SECONDS}</span>
              </button>
            </div>
            <span className="pc-time" dir="ltr">
              {fmt(time)} <i>/</i> {fmt(duration)}
            </span>
          </div>

          <div className="pc-group pc-end">
            <div className="pc-menu-wrap">
              <button
                type="button"
                className={"pc-btn pc-text" + (menu === "speed" ? " is-open" : "")}
                onClick={() => setMenu(menu === "speed" ? null : "speed")}
                aria-haspopup="menu"
                aria-expanded={menu === "speed"}
              >
                <Gauge size={16} /> {speed === 1 ? "عادي" : `${speed}×`}
              </button>
              {menu === "speed" && (
                <div className="pc-popup" role="menu">
                  <div className="pc-popup-title">السرعة</div>
                  {SPEEDS.map((v) => (
                    <button
                      key={v}
                      type="button"
                      role="menuitemradio"
                      aria-checked={speed === v}
                      className={"pc-opt" + (speed === v ? " is-active" : "")}
                      onClick={() => changeSpeed(v)}
                    >
                      <span>{v === 1 ? "عادي" : `${v}×`}</span>
                      {speed === v && <Check size={14} />}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="pc-menu-wrap">
              <button
                type="button"
                className={"pc-btn pc-text" + (menu === "quality" ? " is-open" : "")}
                onClick={() => setMenu(menu === "quality" ? null : "quality")}
                aria-haspopup="menu"
                aria-expanded={menu === "quality"}
              >
                <Settings2 size={16} /> {qualityLabel}
              </button>
              {menu === "quality" && (
                <div className="pc-popup" role="menu">
                  <div className="pc-popup-title">الجودة</div>
                  {qualityOptions.map((o) => (
                    <button
                      key={o.value}
                      type="button"
                      role="menuitemradio"
                      aria-checked={quality === o.value}
                      className={"pc-opt" + (quality === o.value ? " is-active" : "")}
                      onClick={() => changeQuality(o.value)}
                    >
                      <span>{o.label}</span>
                      {quality === o.value && <Check size={14} />}
                    </button>
                  ))}
                  {qualities.length === 0 && (
                    <div className="pc-popup-note">لا توجد جودات أخرى لهذا الفيديو بعد.</div>
                  )}
                </div>
              )}
            </div>

            <button
              type="button"
              className="pc-btn pc-icon"
              onClick={toggleFull}
              aria-label={full ? "إنهاء ملء الشاشة" : "ملء الشاشة"}
            >
              {full ? <Minimize size={19} /> : <Maximize size={19} />}
            </button>
          </div>
        </div>
      </div>
      <div
        className="player-mini"
        aria-hidden="true"
        style={{ "--p": duration ? `${(time / duration) * 100}%` : "0%" }}
      />
    </div>
  );
}
