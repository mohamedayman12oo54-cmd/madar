import { Component } from "react";
import { useLocation } from "react-router-dom";

// Without this, any exception while rendering unmounts the WHOLE app and the person is left with a blank white
// page and no clue why. This keeps the failure visible, says what happened, and offers a way out. It
// deliberately uses no shared components or stylesheets: it must still render when those are what broke.
class Boundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidUpdate(prev) {
    // Moving to another page gives the app a fresh chance.
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    // A lazily loaded page whose file no longer exists (the app was updated while this tab stayed open) is
    // fixed by reloading, not by retrying.
    const stale = /dynamically imported module|Importing a module script failed|Loading chunk/i.test(
      String(error?.message || error)
    );
    return (
      <div
        role="alert"
        dir="rtl"
        style={{
          minHeight: "60vh",
          display: "grid",
          placeItems: "center",
          padding: 24,
          textAlign: "center",
          color: "var(--ink, #2c3247)",
        }}
      >
        <div style={{ maxWidth: 440 }}>
          <h2 style={{ margin: "0 0 8px" }}>{stale ? "تم تحديث التطبيق" : "حدث خطأ غير متوقع"}</h2>
          <p style={{ margin: "0 0 16px", color: "var(--muted, #5f6675)" }}>
            {stale
              ? "حمّل الصفحة من جديد للحصول على آخر نسخة."
              : "تعذّر عرض هذه الصفحة. أعد تحميلها، وإن تكرر الأمر أخبر الدعم بالرسالة أدناه."}
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{
              padding: "10px 18px",
              borderRadius: 10,
              border: 0,
              background: "var(--navy, #313851)",
              color: "var(--cream, #f6f3ed)",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            إعادة تحميل الصفحة
          </button>
          {!stale && (
            <pre
              dir="ltr"
              style={{
                marginTop: 16,
                padding: 10,
                textAlign: "left",
                whiteSpace: "pre-wrap",
                fontSize: 12,
                background: "rgba(49,56,81,0.06)",
                borderRadius: 8,
              }}
            >
              {String(error?.message || error).slice(0, 300)}
            </pre>
          )}
        </div>
      </div>
    );
  }
}

export default function ErrorBoundary({ children }) {
  const { pathname } = useLocation();
  return <Boundary resetKey={pathname}>{children}</Boundary>;
}
