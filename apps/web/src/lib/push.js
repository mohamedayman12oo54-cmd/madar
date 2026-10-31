// Web Push (browser notifications while the app is closed). The server holds the VAPID key; this module
// asks the user for permission, subscribes this device and tells the server about it.
import { api } from "./api.js";

const optInKey = (userId) => `madar:push-optin:${userId}`;
const getOptIn = (userId) => {
  try {
    return localStorage.getItem(optInKey(userId)) === "1";
  } catch {
    return false;
  }
};
const setOptIn = (userId, on) => {
  try {
    if (on) localStorage.setItem(optInKey(userId), "1");
    else localStorage.removeItem(optInKey(userId));
  } catch {
    /* storage blocked */
  }
};

export const pushSupported = () =>
  typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

/** iPhone/iPad only allow Web Push for a site added to the Home Screen. */
export const needsInstallOnIos = () => {
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const standalone = window.navigator.standalone === true || window.matchMedia?.("(display-mode: standalone)").matches;
  return ios && !standalone;
};

const keyToBytes = (b64) => {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
};

async function registration() {
  return navigator.serviceWorker.ready;
}
export async function currentSubscription() {
  if (!pushSupported()) return null;
  return (await registration()).pushManager.getSubscription();
}

async function sendToServer(sub) {
  const j = sub.toJSON();
  await api.post("/notifications/push/subscribe/", { endpoint: j.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth });
}

/** Ask permission, subscribe, register with the server. Throws an Error with .code on a known failure. */
export async function enablePush(userId) {
  const fail = (code) => Object.assign(new Error(code), { code });
  if (!pushSupported()) throw fail("unsupported");
  const { enabled, public_key } = await api.get("/notifications/push/public-key/");
  if (!enabled) throw fail("server_off");
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw fail("denied");
  const reg = await registration();
  const sub = (await reg.pushManager.getSubscription()) ||
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyToBytes(public_key) }));
  await sendToServer(sub);
  setOptIn(userId, true);
}

export async function disablePush(userId) {
  setOptIn(userId, false);
  const sub = await currentSubscription();
  if (!sub) return;
  await api.post("/notifications/push/unsubscribe/", { endpoint: sub.endpoint }).catch(() => {});
  await sub.unsubscribe().catch(() => {});
}

/** After sign-in: if THIS user already opted in on this device, attach the device to the account again. */
export async function syncPush(userId) {
  try {
    if (!pushSupported() || !getOptIn(userId) || Notification.permission !== "granted") return;
    const sub = await currentSubscription();
    if (sub) await sendToServer(sub);
  } catch {
    /* best effort */
  }
}

/** Before sign-out: stop this device receiving the signed-out user's notifications (keeps the browser permission). */
export async function detachDevice() {
  try {
    const sub = await currentSubscription();
    if (sub) await api.post("/notifications/push/unsubscribe/", { endpoint: sub.endpoint });
  } catch {
    /* best effort */
  }
}
