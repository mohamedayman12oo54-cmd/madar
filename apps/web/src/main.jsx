import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { SessionProvider } from "./state/session.jsx";
import { EnvironmentProvider } from "./state/environment.jsx";
import InstallPrompt from "./components/InstallPrompt.jsx";
import "./index.css";

// Register the service worker in production only: in dev it would cache the
// module graph and hide edits. Failure is non-fatal — the app works without it,
// it just is not installable.
if (import.meta.env?.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <SessionProvider>
        <EnvironmentProvider>
          <App />
          <InstallPrompt />
        </EnvironmentProvider>
      </SessionProvider>
    </BrowserRouter>
  </React.StrictMode>
);
