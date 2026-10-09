import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
const dom = new JSDOM("<!doctype html><body><div id=root></div></body>", { url: "http://localhost/", pretendToBeVisual: true });
const w = dom.window;
for (const k of ["window","document","navigator","HTMLElement","Element","Node","MutationObserver","getComputedStyle","requestAnimationFrame","cancelAnimationFrame","Event","CustomEvent","localStorage"])
  Object.defineProperty(globalThis,k,{value:k==="window"?w:w[k],configurable:true,writable:true});
for (const k of Object.getOwnPropertyNames(w)) if(!(k in globalThis)&&/^[A-Z]/.test(k)) Object.defineProperty(globalThis,k,{value:w[k],configurable:true,writable:true});
w.matchMedia = () => ({ matches:false, addEventListener(){}, removeEventListener(){} });
globalThis.matchMedia = w.matchMedia;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React=(await import("react")).default; const {createRoot}=await import("react-dom/client"); const {act}=await import("react");
const {createServer}=await import("vite");
const vite=await createServer({server:{middlewareMode:true},appType:"custom",logLevel:"error",optimizeDeps:{noDiscovery:true}});
const InstallPrompt=(await vite.ssrLoadModule("/src/components/InstallPrompt.jsx")).default;

test("renders nothing until the browser offers installation", () => {
  const host=w.document.createElement("div"); w.document.body.appendChild(host);
  const root=createRoot(host); act(()=>root.render(React.createElement(InstallPrompt)));
  assert.equal(host.textContent.trim(), "", "must stay silent on first paint");
  act(()=>root.unmount());
});

test("shows the card when beforeinstallprompt fires", () => {
  const host=w.document.createElement("div"); w.document.body.appendChild(host);
  const root=createRoot(host); act(()=>root.render(React.createElement(InstallPrompt)));
  act(()=>{ const e=new w.Event("beforeinstallprompt"); e.prompt=()=>{}; e.userChoice=Promise.resolve({outcome:"accepted"}); w.dispatchEvent(e); });
  assert.match(host.textContent, /ثبّت مدار/);
  assert.ok(host.querySelector(".install-btn"), "install button rendered");
  act(()=>root.unmount());
});

test("dismissing hides it and remembers the choice", () => {
  const host=w.document.createElement("div"); w.document.body.appendChild(host);
  const root=createRoot(host); act(()=>root.render(React.createElement(InstallPrompt)));
  act(()=>{ const e=new w.Event("beforeinstallprompt"); e.prompt=()=>{}; e.userChoice=Promise.resolve({outcome:"accepted"}); w.dispatchEvent(e); });
  act(()=>{ host.querySelector(".install-close").dispatchEvent(new w.Event("click",{bubbles:true})); });
  assert.equal(host.textContent.trim(), "");
  assert.ok(w.localStorage.getItem("madar.install.dismissed"), "dismissal remembered");
  act(()=>root.unmount());
});
test.after(()=>vite.close());
