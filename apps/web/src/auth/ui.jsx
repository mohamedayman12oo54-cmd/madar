import { Children, cloneElement, isValidElement, useState, useRef, useEffect, useId } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
  Eye,
  EyeOff,
  Check,
  AlertCircle,
  Info,
  ArrowRight,
  ChevronLeft,
  X,
  Smartphone,
  Mail,
} from "lucide-react";
import logo from "../assets/madar-logo.png";
import {
  COUNTRIES,
  COUNTRY_BY_ISO,
  DEFAULT_ISO,
  cleanNational,
  dialLabel,
  parseInternational,
} from "../lib/phone.js";
import "./auth.css";

/* ---------------- layout: centered AuthLayout ---------------- */
function AuthDeco() {
  return (
    <div className="auth-deco" aria-hidden="true">
      <div className="ring r1" />
      <div className="ring r2" />
      <div className="ring r3" />
      <div className="orbiter">
        <span className="planet" />
      </div>
      <div className="orbiter o2">
        <span className="planet" />
      </div>
      <span className="star" style={{ top: "22%", left: "26%" }} />
      <span className="star" style={{ top: "68%", left: "32%" }} />
      <span className="star" style={{ top: "30%", left: "72%" }} />
      <span className="star" style={{ top: "74%", left: "66%" }} />
      <span className="star" style={{ top: "16%", left: "58%" }} />
    </div>
  );
}

export function AuthShell({ children }) {
  return (
    <div className="auth">
      <AuthDeco />
      <div className="auth-shell">{children}</div>
    </div>
  );
}

export function AuthCard({ children, back }) {
  const nav = useNavigate();
  return (
    <>
      <div className="auth-logo">
        <img src={logo} alt="مدار Madar" />
      </div>
      <motion.div
        className="auth-card"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        {back && (
          <button
            className="auth-back"
            aria-label="رجوع"
            onClick={() => (typeof back === "string" ? nav(back) : nav(-1))}
          >
            <ChevronLeft size={20} style={{ transform: "scaleX(-1)" }} />
          </button>
        )}
        {children}
      </motion.div>
    </>
  );
}

export function Head({ title, sub }) {
  return (
    <div className="auth-head">
      <h1 className="auth-h">{title}</h1>
      {sub && <p className="auth-sub">{sub}</p>}
    </div>
  );
}

export function Stepper({ total, current }) {
  return (
    <div className="stepper" aria-hidden="true">
      {Array.from({ length: total }).map((_, i) => (
        <span key={i} className={i <= current ? "on" : ""} />
      ))}
    </div>
  );
}

/* ---------------- fields (label + required + reserved message) ---------------- */
export function Field({ label, required, error, hint, children, className = "" }) {
  const uid = useId();
  const messageId = `${uid}-msg`;
  // When the field wraps exactly one control, tie everything together for assistive technology: the label
  // names the control (for/id), and the hint or error is its accessible description, announced when it
  // appears. (Previously a screen reader met every input in the app as an unnamed edit box.)
  const only = Children.count(children) === 1 && isValidElement(children) ? children : null;
  const controlId = only ? only.props.id || `${uid}-ctl` : undefined;
  const control = only
    ? cloneElement(only, {
        id: controlId,
        "aria-describedby": [only.props["aria-describedby"], messageId].filter(Boolean).join(" "),
        ...(error ? { "aria-invalid": true } : {}),
        ...(required ? { "aria-required": true } : {}),
      })
    : children;
  return (
    <div className={"field" + (className ? " " + className : "")}>
      {label && (
        <label htmlFor={controlId}>
          {label}
          {required && (
            <span className="req" aria-hidden="true">
              {" "}
              *
            </span>
          )}
        </label>
      )}
      {control}
      <div id={messageId} aria-live="polite" className={"field-msg" + (error ? " err" : "")}>
        {error ? (
          <>
            <AlertCircle size={13} aria-hidden="true" /> {error}
          </>
        ) : (
          hint || ""
        )}
      </div>
    </div>
  );
}

/* Two-way choice of where the verification code is delivered: SMS or email.
   Controlled: value is "phone" | "email". */
export function ChannelPicker({ value, onChange, label = "أرسل رمز التحقق عبر", disabled }) {
  const opts = [
    { v: "phone", t: "رسالة SMS", icon: <Smartphone size={18} /> },
    { v: "email", t: "البريد (Gmail)", icon: <Mail size={18} /> },
  ];
  return (
    <div className="field">
      {label && <label>{label}</label>}
      <div className="channel-picker" role="radiogroup" aria-label={label}>
        {opts.map((o) => (
          <button
            key={o.v}
            type="button"
            role="radio"
            aria-checked={value === o.v}
            disabled={disabled}
            className={"channel-opt" + (value === o.v ? " on" : "")}
            onClick={() => onChange(o.v)}
          >
            {o.icon}
            <span>{o.t}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export const emailLooksValid = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test((v || "").trim());

export function TextInput({ ltr, error, className = "", ...p }) {
  return (
    <input
      {...p}
      className={
        "inp" + (ltr ? " ltr" : "") + (error ? " err" : "") + (className ? " " + className : "")
      }
    />
  );
}

export function PasswordInput({ error, ...p }) {
  const [show, setShow] = useState(false);
  return (
    <div className="inp-wrap pw-field">
      <input className={"inp" + (error ? " err" : "")} type={show ? "text" : "password"} {...p} />
      <button
        type="button"
        className="inp-eye"
        aria-label={show ? "إخفاء كلمة المرور" : "إظهار كلمة المرور"}
        onClick={() => setShow((s) => !s)}
      >
        {show ? <EyeOff size={18} /> : <Eye size={18} />}
      </button>
    </div>
  );
}

/** Country-aware mobile field. `value` / onChange use the FULL international
 *  string ("+201001234567", or "" while empty) so callers just validate it with
 *  phoneError() from lib/phone.js and send it to the API unchanged. */
export function PhoneInput({
  value = "",
  onChange,
  error,
  defaultIso = DEFAULT_ISO,
  disabled,
  id,
  ...rest
}) {
  const parsed = parseInternational(value);
  const [iso, setIso] = useState(parsed?.country.iso || defaultIso);
  const [national, setNational] = useState(parsed?.national || "");
  const country = COUNTRY_BY_ISO[iso] || COUNTRY_BY_ISO[DEFAULT_ISO];

  // Follow external resets / edits of the value (e.g. opening the edit modal).
  useEffect(() => {
    if (!value) {
      setNational("");
      return;
    }
    const p = parseInternational(value);
    if (p && "+" + p.country.dial + p.national !== "+" + country.dial + national) {
      setIso(p.country.iso);
      setNational(p.national);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const emit = (nextIso, nextNational) => {
    const c = COUNTRY_BY_ISO[nextIso];
    onChange?.({ target: { value: nextNational ? `+${c.dial}${nextNational}` : "" } });
  };

  return (
    <div className="phone-row" dir="ltr">
      <select
        className={"inp phone-sel" + (error ? " err" : "")}
        value={iso}
        disabled={disabled}
        aria-label="دولة رقم الهاتف"
        onChange={(e) => {
          setIso(e.target.value);
          emit(e.target.value, national);
        }}
      >
        {COUNTRIES.map((c) => (
          <option key={c.iso} value={c.iso}>
            {dialLabel(c)}
          </option>
        ))}
      </select>
      <input
        id={id}
        className={"inp phone-num" + (error ? " err" : "")}
        type="tel"
        inputMode="numeric"
        autoComplete="tel-national"
        disabled={disabled}
        placeholder={country.example}
        value={national}
        maxLength={14}
        onChange={(e) => {
          const n = cleanNational(e.target.value);
          setNational(n);
          emit(iso, n);
        }}
        {...rest}
      />
    </div>
  );
}

export const PW_RULES = [
  { k: "len", t: "٨ أحرف على الأقل", test: (v) => v.length >= 8 },
  { k: "up", t: "حرف كبير (A-Z)", test: (v) => /[A-Z]/.test(v) },
  { k: "low", t: "حرف صغير (a-z)", test: (v) => /[a-z]/.test(v) },
  { k: "num", t: "رقم (0-9)", test: (v) => /\d/.test(v) },
  { k: "sp", t: "رمز خاص (!@#…)", test: (v) => /[^A-Za-z0-9]/.test(v) },
];
export const passwordValid = (v) => PW_RULES.every((r) => r.test(v));
export function PasswordChecklist({ value }) {
  return (
    <ul className="pw-req">
      {PW_RULES.map((r) => {
        const ok = r.test(value);
        return (
          <li key={r.k} className={ok ? "ok" : ""}>
            <span className="rc">
              <Check size={11} strokeWidth={3} />
            </span>
            {r.t}
          </li>
        );
      })}
    </ul>
  );
}

/* ---------------- OTP ---------------- */
export function Otp({ length = 6, value, onChange, error }) {
  const refs = useRef([]);
  const set = (i, v) => {
    const n = value.split("");
    n[i] = v;
    onChange(n.join("").slice(0, length));
  };
  const onKey = (i, e) => {
    if (e.key === "Backspace" && !value[i] && i > 0) refs.current[i - 1]?.focus();
  };
  const onInput = (i, e) => {
    const v = e.target.value.replace(/\D/g, "");
    if (!v) {
      set(i, "");
      return;
    }
    if (v.length > 1) {
      onChange(v.slice(0, length));
      refs.current[Math.min(v.length, length - 1)]?.focus();
      return;
    }
    set(i, v);
    if (i < length - 1) refs.current[i + 1]?.focus();
  };
  return (
    <div className={"otp" + (error ? " err" : "")}>
      {Array.from({ length }).map((_, i) => (
        <motion.input
          key={i}
          ref={(el) => (refs.current[i] = el)}
          inputMode="numeric"
          maxLength={1}
          value={value[i] || ""}
          className={value[i] ? "filled" : ""}
          onChange={(e) => onInput(i, e)}
          onKeyDown={(e) => onKey(i, e)}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 * i, duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          aria-label={"خانة " + (i + 1)}
        />
      ))}
    </div>
  );
}

export function Timer({ seconds = 45, onResend }) {
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    if (left <= 0) return;
    const t = setTimeout(() => setLeft((l) => l - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);
  const mm = String(Math.floor(left / 60)).padStart(2, "0");
  const ss = String(left % 60).padStart(2, "0");
  if (left <= 0)
    return (
      <div className="timer">
        <button
          className="link"
          onClick={() => {
            setLeft(seconds);
            onResend && onResend();
          }}
        >
          إعادة إرسال الرمز
        </button>
      </div>
    );
  return (
    <div className="timer">
      إعادة إرسال الرمز بعد{" "}
      <span className="num">
        {mm}:{ss}
      </span>
    </div>
  );
}

/* ---------------- buttons ---------------- */
export function Btn({ variant = "primary", loading, loadingText, children, ...p }) {
  return (
    <button className={"abtn abtn-" + variant} {...p} disabled={Boolean(loading || p.disabled)}>
      {loading ? (
        <>
          <span className={"orbit-loader" + (variant !== "primary" ? " dark" : "")} />
          {loadingText}
        </>
      ) : (
        children
      )}
    </button>
  );
}

/* ---------------- banners / states ---------------- */
export function Banner({ tone = "err", children }) {
  const I = tone === "err" ? AlertCircle : Info;
  return (
    <div className={"banner " + tone}>
      <I className="bi" size={17} />
      {children}
    </div>
  );
}

export function StateView({ tone = "info", icon, title, text, children }) {
  return (
    <div className="state">
      <div className={"state-ic " + tone}>{icon}</div>
      <div className="state-t">{title}</div>
      {text && <div className="state-x">{text}</div>}
      {children && (
        <div style={{ width: "100%", marginBlockStart: "18px", display: "grid", gap: "10px" }}>
          {children}
        </div>
      )}
    </div>
  );
}

export function SuccessRing() {
  return (
    <svg className="success-ring" viewBox="0 0 52 52" aria-hidden="true">
      <circle className="sr-c" cx="26" cy="26" r="24" />
      <path className="sr-k" d="M15 27l7 7 15-15" />
    </svg>
  );
}

export function OrbitBig() {
  return (
    <div className="orbit-big" role="status" aria-label="جارٍ التحميل">
      <div className="ring" />
      <div className="ring inner" />
      <div className="spin">
        <span className="dot" />
      </div>
    </div>
  );
}

export function EnvCard({ initials, name, meta, last, onEnter }) {
  return (
    <button className="env-card" onClick={onEnter}>
      <span className="env-ava">{initials}</span>
      <span className="env-info">
        <span className="en">{name}</span>
        <span className="em">{meta}</span>
        {last && <span className="last">{last}</span>}
      </span>
      <ArrowRight className="env-go" size={18} style={{ transform: "scaleX(-1)" }} />
    </button>
  );
}

let _openModals = 0;

/** Locks the page behind the dialog so the background never scrolls while a
 *  modal is open. Reference-counted: nested/stacked modals unlock only once
 *  the last one closes. Compensates for the scrollbar width so the page
 *  doesn't visibly shift. */
function useBodyScrollLock() {
  useEffect(() => {
    const body = document.body;
    if (_openModals === 0) {
      const gap = window.innerWidth - document.documentElement.clientWidth;
      body.dataset.prevOverflow = body.style.overflow;
      body.dataset.prevPadding = body.style.paddingInlineEnd;
      body.style.overflow = "hidden";
      if (gap > 0) body.style.paddingInlineEnd = `${gap}px`;
    }
    _openModals += 1;
    return () => {
      _openModals -= 1;
      if (_openModals === 0) {
        body.style.overflow = body.dataset.prevOverflow || "";
        body.style.paddingInlineEnd = body.dataset.prevPadding || "";
        delete body.dataset.prevOverflow;
        delete body.dataset.prevPadding;
      }
    };
  }, []);
}

/**
 * Shared dialog for the whole app. Structure is always
 *   header (sticky) → body (the ONLY scroller) → footer (sticky, optional)
 * so a long form is fully reachable at normal browser zoom on any screen.
 *
 * `size`: "sm" (default, confirmations) | "md" | "lg" (multi-field forms).
 * `footer`: action buttons pinned to the bottom. When omitted the children
 * scroll as one block — existing call sites keep working unchanged.
 */
// Open dialogs, top-most last: only the top one reacts to Escape / Tab, so closing a confirmation that sits
// on top of a form does not also close the form underneath.
const _modalStack = [];
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Modal({ title, text, children, onClose, size = "sm", footer = null }) {
  const panelRef = useRef(null);
  const titleId = useId();
  // Always call the LATEST onClose without re-subscribing. Re-running the effect on every new function
  // identity (inline handlers are new on every render) used to pull focus back to the dialog panel while
  // the person was typing in one of its fields.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useBodyScrollLock();

  useEffect(() => {
    const opener = document.activeElement;
    const token = {};
    _modalStack.push(token);
    panelRef.current?.focus({ preventScroll: true });

    const onKey = (e) => {
      if (_modalStack[_modalStack.length - 1] !== token) return;
      if (e.key === "Escape") {
        closeRef.current?.();
        return;
      }
      if (e.key !== "Tab") return;
      // Keep Tab inside the dialog (WCAG 2.1.2 / 2.4.3): wrap at both ends instead of walking out into the
      // page behind it.
      const panel = panelRef.current;
      if (!panel) return;
      const items = [...panel.querySelectorAll(FOCUSABLE)].filter((el) => !el.closest("[hidden], [aria-hidden='true']"));
      if (items.length === 0) {
        e.preventDefault();
        panel.focus({ preventScroll: true });
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (!panel.contains(active)) {
        e.preventDefault();
        first.focus();
      } else if (e.shiftKey && (active === first || active === panel)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      const at = _modalStack.indexOf(token);
      if (at >= 0) _modalStack.splice(at, 1);
      // Give focus back to whatever opened the dialog, if it is still on the page.
      if (opener && opener.isConnected && typeof opener.focus === "function") {
        opener.focus({ preventScroll: true });
      }
    };
  }, []);

  return (
    <div
      className="modal-back"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
    >
      <motion.div
        ref={panelRef}
        className={`modal modal-${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onMouseDown={(e) => e.stopPropagation()}
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="modal-grab" aria-hidden="true" />
        <header className="modal-head">
          <div className="mt" id={titleId}>
            {title}
          </div>
          {text && <div className="mx">{text}</div>}
          <button type="button" className="modal-x" aria-label="إغلاق" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        <div className="ma">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </motion.div>
    </div>
  );
}

export { Check, AlertCircle, Info, ArrowRight };
