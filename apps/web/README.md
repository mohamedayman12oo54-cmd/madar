# مدار — Madar Frontend

Arabic-first, RTL landing experience for **Madar**, built with **React + Vite**, **React Router**, and **Framer Motion**.

> This is the UI/UX **prototype track**. It renders behaviour and scope already
> established in the System/Backend documentation. It is **not** a product-level
> technology decision, and it does not invent product facts (side "stats" are
> conceptual labels, AI is advisory, tenant isolation is preserved).

## Requirements
- Node.js 18+ and npm

## Getting started
```bash
npm install
npm run dev      # start the dev server (http://localhost:5173)
npm run build    # production build → dist/
npm run preview  # preview the production build
```

## Assets
- `public/main.png` — hero background (the voxel-globe brand image).
- `src/assets/madar-logo.png` — the Madar logo lockup (navbar, loader, footer).

Replace either file in place to update the visuals; no code changes needed.

## Structure
```
src/
  assets/            logo
  components/        Navbar, LogoLoader, Hero, section components, Footer, Reveal, Page…
  pages/             Home, Teachers, Students, Features, HowItWorks, About, Contact, Privacy, Terms
  data/content.js    all Arabic copy in one place
  App.jsx            router + intro loader + page transitions
  main.jsx           entry (BrowserRouter)
  index.css          design tokens + all styles (navy #313851 / blue-gray #C2CBD3 / cream #F6F3ED)
```

## Notes
- Fonts load from Google Fonts (IBM Plex Sans Arabic). Swap in `index.html` if you self-host.
- `prefers-reduced-motion` is respected globally (loader skipped, animations reduced).
- The **Fast Session** block is an interactive demo: per-tap persistence, no batch save on close.
- Login / "ابدأ الآن" CTAs are inert placeholders (no auth flow in this scaffold).

## Authentication experience
Arabic-first, RTL, **split-screen** auth (form + cinematic brand panel) under `/auth`, sharing one design system. The marketing navbar/footer are hidden on auth routes.

- **Browse every screen:** open **`/auth/all`** (gallery of all flows and states).
- Entry `/auth` · Teacher `/auth/teacher/{login,signup,forgot,environments,welcome}` · Student `/auth/student` (login), `/auth/student/claim`, `/auth/student/environments` · Team `/auth/team/login` · states `/auth/state/:key` (incl. `unauthorized`, `session-expired`) · `/auth/logout`, `/auth/loading`.
- Includes: split layout with brand panel, reusable components, live **password-requirements checklist**, reserved validation space (no layout jump), OTP boxes (auto-advance/paste), resend timer, loading-button text, success ring, environment cards.

**Demo triggers (prototype):** password `wrong` → invalid credentials; OTP `000000` → wrong code; student claim phone ending in `0` → "no account found", otherwise proceeds.

**Product rules honored:** no public student signup (claim-by-phone only); no `teacher_environment_id` field and no manual tenant entry; single active environment with a "never merge teachers" note; Content Maintainer walled off from records; unified `/api/v1` (no separate teacher/student APIs). Auth mechanics are shown generically — no provider is invented. Note: the student **password** shown here is one plausible design over a still-open backend decision on the student credential mechanism, not a locked product fact.
