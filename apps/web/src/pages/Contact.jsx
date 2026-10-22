import { useState } from "react";
import Page from "../components/Page.jsx";

export default function Contact() {
  const [sent, setSent] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", message: "" });
  const on = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <Page>
      <div className="page-head">
        <div className="wrap">
          <div className="kicker">تواصل معنا</div>
          <h2 className="h2">نحبّ أن نسمع منك.</h2>
        </div>
      </div>
      <section className="section">
        <div className="wrap" style={{ maxWidth: "560px" }}>
          {sent ? (
            <div className="mock" style={{ textAlign: "center" }}>
              <h3 style={{ color: "var(--navy)", marginBlockEnd: "8px" }}>تم استلام رسالتك</h3>
              <p style={{ color: "var(--muted)" }}>شكرًا لتواصلك — سنعود إليك قريبًا.</p>
            </div>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setSent(true);
              }}
              style={{ display: "grid", gap: "14px" }}
            >
              <input
                required
                placeholder="الاسم الكامل"
                value={form.name}
                onChange={on("name")}
                style={inp}
              />
              <input
                required
                type="email"
                placeholder="البريد الإلكتروني"
                value={form.email}
                onChange={on("email")}
                style={inp}
              />
              <textarea
                required
                placeholder="رسالتك"
                rows={5}
                value={form.message}
                onChange={on("message")}
                style={{ ...inp, resize: "vertical" }}
              />
              <button
                className="btn btn-primary btn-lg"
                type="submit"
                style={{ justifyContent: "center" }}
              >
                إرسال الرسالة
              </button>
            </form>
          )}
        </div>
      </section>
    </Page>
  );
}

const inp = {
  font: "inherit",
  padding: "14px 16px",
  borderRadius: "12px",
  border: "1px solid var(--line-2)",
  background: "var(--panel)",
  color: "var(--ink)",
};
