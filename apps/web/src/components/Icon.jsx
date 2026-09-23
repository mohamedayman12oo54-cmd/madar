import {
  Users, CalendarClock, ClipboardCheck, Wallet, Layers, Video,
  ListChecks, MessageSquareText, Bell, Lock, ShieldCheck, Waypoints,
} from "lucide-react";

const map = {
  students: Users, sessions: CalendarClock, attendance: ClipboardCheck,
  payments: Wallet, evaluation: Layers, content: Video, quiz: ListChecks,
  assistant: MessageSquareText, bell: Bell, isolation: Lock,
  security: ShieldCheck, state: Waypoints,
};

export default function Icon({ name, size = 20 }) {
  const C = map[name] || Layers;
  return <C size={size} />;
}
