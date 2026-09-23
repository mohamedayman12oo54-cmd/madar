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

## Backend
This frontend now talks to a real Django REST API — see `../madar-backend/README.md`
for setup. Point it at a different backend via `VITE_API_URL` (copy `.env.example` to `.env`).
`src/lib/api.js` is the low-level fetch client (token storage + auto-refresh);
`src/auth/api.js` wraps every backend endpoint one-to-one for the auth screens.

## Authentication experience
Arabic-first, RTL, **split-screen** auth (form + cinematic brand panel) under `/auth`, sharing one design system. The marketing navbar/footer are hidden on auth routes.

- **Browse every screen:** open **`/auth/all`** (gallery of all flows and states).
- Entry `/auth` · Teacher `/auth/teacher/{login,signup,forgot,environments,welcome}` · Student `/auth/student` (login), `/auth/student/claim`, `/auth/student/environments` · Team `/auth/team/login` · states `/auth/state/:key` (incl. `unauthorized`, `session-expired`) · `/auth/logout`, `/auth/loading`.
- Includes: split layout with brand panel, reusable components, live **password-requirements checklist**, reserved validation space (no layout jump), OTP boxes (auto-advance/paste), resend timer, loading-button text, success ring, environment cards.

**Product rules honored:** no public student signup (claim-by-phone only); no `teacher_environment_id` field and no manual tenant entry; single active environment with a "never merge teachers" note; Content Maintainer (team) walled off from teacher/student records; one unified backend (`/api/v1`, one user table, one JWT scheme across all three roles) rather than separate teacher/student services. Auth mechanics use a real Django backend now — see `../madar-backend/README.md`.
