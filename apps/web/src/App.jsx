import { lazy, Suspense, useState, useEffect } from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import { AnimatePresence, MotionConfig } from "framer-motion";

import LogoLoader from "./components/LogoLoader.jsx";
import Navbar from "./components/Navbar.jsx";
import Footer from "./components/Footer.jsx";

import Home from "./pages/Home.jsx";
import Teachers from "./pages/Teachers.jsx";
import Students from "./pages/Students.jsx";
import Features from "./pages/Features.jsx";
import HowItWorksPage from "./pages/HowItWorksPage.jsx";
import About from "./pages/About.jsx";
import Contact from "./pages/Contact.jsx";
import Privacy from "./pages/Privacy.jsx";
import Terms from "./pages/Terms.jsx";

import AuthEntry from "./auth/screens/AuthEntry.jsx";
import {
  TeacherLogin,
  TeacherSignup,
  TeacherForgot,
  TeacherEnvSelect,
  TeacherWelcome,
} from "./auth/screens/TeacherAuth.jsx";
import {
  StudentLogin,
  StudentClaim,
  StudentForgot,
  StudentEnvSelect,
} from "./auth/screens/StudentAuth.jsx";
import { ParentLogin } from "./auth/screens/ParentAuth.jsx";
import { CheckinPage } from "./auth/screens/Checkin.jsx";
import { RegisterPage } from "./auth/screens/Register.jsx";
import { TeamLogin } from "./auth/screens/TeamAuth.jsx";
import {
  AuthGallery,
  AuthStateScreen,
  LogoutConfirm,
  LoadingDemo,
} from "./auth/screens/AuthStates.jsx";

import { OrbitBig } from "./auth/ui.jsx";

// The signed-in areas are large and most visitors only ever use one of them (or none: the marketing pages),
// so each loads on demand instead of shipping inside the first download.
const AppRoutes = lazy(() => import("./dashboard/AppRoutes.jsx"));
const StudentRoutes = lazy(() => import("./student/StudentRoutes.jsx"));
const ParentPortal = lazy(() => import("./parent/ParentPortal.jsx"));
const TeamRoutes = lazy(() => import("./team/TeamRoutes.jsx"));

function AreaFallback() {
  return (
    <div className="dash-boot" role="status" aria-label="جارٍ التحميل">
      <OrbitBig />
    </div>
  );
}

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [pathname]);
  return null;
}

function AnimatedRoutes({ ready }) {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        {/* marketing */}
        <Route path="/" element={<Home ready={ready} />} />
        <Route path="/teachers" element={<Teachers />} />
        <Route path="/students" element={<Students />} />
        <Route path="/features" element={<Features />} />
        <Route path="/how-it-works" element={<HowItWorksPage />} />
        <Route path="/about" element={<About />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/terms" element={<Terms />} />

        {/* authentication */}
        <Route path="/auth" element={<AuthEntry />} />
        <Route path="/auth/all" element={<AuthGallery />} />
        <Route path="/auth/loading" element={<LoadingDemo />} />
        <Route path="/auth/logout" element={<LogoutConfirm />} />
        <Route path="/auth/teacher/login" element={<TeacherLogin />} />
        <Route path="/auth/teacher/signup" element={<TeacherSignup />} />
        <Route path="/auth/teacher/forgot" element={<TeacherForgot />} />
        <Route path="/auth/teacher/environments" element={<TeacherEnvSelect />} />
        <Route path="/auth/teacher/welcome" element={<TeacherWelcome />} />
        <Route path="/auth/student" element={<StudentLogin />} />
        <Route path="/auth/student/claim" element={<StudentClaim />} />
        <Route path="/auth/student/forgot" element={<StudentForgot />} />
        <Route path="/auth/student/environments" element={<StudentEnvSelect />} />
        <Route path="/auth/parent" element={<ParentLogin />} />
        {/* public self check-in (opened from the teacher's QR) */}
        <Route path="/checkin/:token" element={<CheckinPage />} />
        {/* public student self-registration (opened from the teacher's QR) */}
        <Route path="/register/:token" element={<RegisterPage />} />
        <Route path="/auth/team/login" element={<TeamLogin />} />
        <Route path="/auth/state/:key" element={<AuthStateScreen />} />

        <Route path="*" element={<Home ready={ready} />} />
      </Routes>
    </AnimatePresence>
  );
}

export default function App() {
  const location = useLocation();
  const isAuth = location.pathname.startsWith("/auth") || location.pathname.startsWith("/checkin/") || location.pathname.startsWith("/register/");
  const isApp = location.pathname.startsWith("/app");
  // NOT startsWith("/learn"): keep the match exact so no marketing path can collide with it.
  const isLearn = location.pathname === "/learn" || location.pathname.startsWith("/learn/");

  const isParent = location.pathname === "/parent";
  const isTeam = location.pathname === "/team" || location.pathname.startsWith("/team/");

  const prefersReduced =
    typeof window !== "undefined" &&
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const onLanding = typeof window !== "undefined" && window.location.pathname === "/";
  const [loading, setLoading] = useState(!prefersReduced && onLanding);
  const [ready, setReady] = useState(prefersReduced || !onLanding);

  useEffect(() => {
    if (prefersReduced || !onLanding) return;
    const r = setTimeout(() => setReady(true), 2500);
    const l = setTimeout(() => setLoading(false), 2700);
    return () => {
      clearTimeout(r);
      clearTimeout(l);
    };
  }, [prefersReduced, onLanding]);

  // /app has its own shell (topbar/sidebar) — no marketing Navbar/Footer or
  // page-transition AnimatePresence, which would otherwise remount the
  // dashboard shell (losing sidebar/drawer state) on every internal
  // navigation between dashboard sections.
  if (isApp) {
    return (
      <MotionConfig reducedMotion="user">
        <Suspense fallback={<AreaFallback />}>
          <AppRoutes />
        </Suspense>
      </MotionConfig>
    );
  }

  if (isTeam) {
    return (
      <MotionConfig reducedMotion="user">
        <Suspense fallback={<AreaFallback />}>
          <TeamRoutes />
        </Suspense>
      </MotionConfig>
    );
  }

  if (isParent) {
    return (
      <MotionConfig reducedMotion="user">
        <Suspense fallback={<AreaFallback />}>
          <ParentPortal />
        </Suspense>
      </MotionConfig>
    );
  }

  if (isLearn) {
    return (
      <MotionConfig reducedMotion="user">
        <Suspense fallback={<AreaFallback />}>
          <StudentRoutes />
        </Suspense>
      </MotionConfig>
    );
  }

  return (
    <MotionConfig reducedMotion="user">
      <AnimatePresence>{loading && <LogoLoader key="loader" />}</AnimatePresence>
      <ScrollToTop />
      {!isAuth && <Navbar />}
      <main>
        <AnimatedRoutes ready={ready} />
      </main>
      {!isAuth && <Footer />}
    </MotionConfig>
  );
}
