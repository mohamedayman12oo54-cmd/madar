// Single source of truth for the dashboard navigation. The sidebar draws the GROUPS (related pages together, with a
// small heading), the mobile bottom bar draws `mobileTabs`, and the top bar's "create" menu draws `quickActions`.
// Every path is a real route in AppRoutes; adding a working page needs no change anywhere else.
import {
  LayoutDashboard,
  Users,
  UsersRound,
  CalendarClock,
  ClipboardCheck,
  GraduationCap,
  Wallet,
  BookOpen,
  Bell,
  Settings,
  ScanLine,
  CreditCard,
  LifeBuoy,
  UserPlus,
  CalendarPlus,
  Send,
} from "lucide-react";

export const dashboardNavGroups = [
  {
    title: "",
    items: [{ to: "/app", label: "نظرة عامة", icon: LayoutDashboard, end: true }],
  },
  {
    title: "التدريس اليومي",
    items: [
      { to: "/app/sessions", label: "الجلسات", icon: CalendarClock },
      { to: "/app/attendance", label: "الحضور والتسميع", icon: ClipboardCheck },
      { to: "/app/scan", label: "مسح رمز الطالب", icon: ScanLine },
      // groups first: a student is added INTO a group, so the group has to exist before the student
      { to: "/app/groups", label: "المجموعات والمواعيد", icon: UsersRound },
      { to: "/app/students", label: "الطلاب", icon: Users },
    ],
  },
  {
    title: "المتابعة والمحتوى",
    items: [
      { to: "/app/evaluation", label: "التقييم", icon: GraduationCap },
      { to: "/app/content", label: "المحتوى التعليمي", icon: BookOpen },
      { to: "/app/financials", label: "المدفوعات", icon: Wallet },
      { to: "/app/notifications", label: "الإشعارات", icon: Bell },
    ],
  },
  {
    title: "حسابي",
    items: [
      { to: "/app/billing", label: "الاشتراك والباقات", icon: CreditCard },
      { to: "/app/support", label: "الدعم والمساعدة", icon: LifeBuoy },
      { to: "/app/settings", label: "الإعدادات", icon: Settings },
    ],
  },
];

/** The same entries as one flat list (page-title lookup, tests). */
export const dashboardNav = dashboardNavGroups.flatMap((g) => g.items);

/** The four tabs most used during a lesson; everything else is under "المزيد" (the drawer). */
export const mobileTabs = ["/app", "/app/sessions", "/app/attendance", "/app/students"].map((to) => dashboardNav.find((n) => n.to === to));

/** "+ جديد" menu in the top bar: the things a teacher starts most often. */
export const quickActions = [
  { to: "/app/sessions", label: "جلسة جديدة", hint: "افتح أو جدول جلسة", icon: CalendarPlus },
  { to: "/app/groups", label: "مجموعة جديدة", hint: "أنشئ مجموعة ومواعيدها", icon: UsersRound },
  { to: "/app/students", label: "إضافة طالب", hint: "سجّل طالبًا في مجموعتك", icon: UserPlus },
  { to: "/app/scan", label: "مسح رمز طالب", hint: "حضور سريع بالكاميرا", icon: ScanLine },
  { to: "/app/notifications", label: "رسالة لطلابك", hint: "أرسل إشعارًا", icon: Send },
];
