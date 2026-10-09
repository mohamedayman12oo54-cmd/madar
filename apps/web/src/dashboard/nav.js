// Single source of truth for the dashboard sidebar (Phase 1 shell). Phase 2+
// sections plug their real pages in at these same paths — adding a working
// page later needs no change here.
import {
  LayoutDashboard, Users, UsersRound, CalendarClock, ClipboardCheck,
  GraduationCap, Wallet, BookOpen, Bell, Settings, ScanLine,
} from "lucide-react";

export const dashboardNav = [
  { to: "/app", label: "نظرة عامة", icon: LayoutDashboard, end: true },
  { to: "/app/students", label: "الطلاب", icon: Users },
  { to: "/app/groups", label: "المجموعات والمواعيد", icon: UsersRound },
  { to: "/app/sessions", label: "الجلسات", icon: CalendarClock },
  { to: "/app/attendance", label: "الحضور والتسميع", icon: ClipboardCheck },
  { to: "/app/scan", label: "مسح رمز الطالب", icon: ScanLine },
  { to: "/app/evaluation", label: "التقييم", icon: GraduationCap },
  { to: "/app/financials", label: "المدفوعات", icon: Wallet },
  { to: "/app/content", label: "المحتوى التعليمي", icon: BookOpen },
  { to: "/app/notifications", label: "الإشعارات", icon: Bell },
  { to: "/app/settings", label: "الإعدادات", icon: Settings },
];
