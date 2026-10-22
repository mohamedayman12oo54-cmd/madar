import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "../components/ProtectedRoute.jsx";
import TeamLayout from "./TeamLayout.jsx";
import KnowledgePage from "./KnowledgePage.jsx";

/** The Madar team area (Content Maintainer). It is NOT tenant-scoped, so unlike the teacher and student
 *  areas it needs no active environment — only a signed-in account whose role is "team". */
export default function TeamRoutes() {
  return (
    <Routes>
      <Route element={<ProtectedRoute role="team" />}>
        <Route path="/team" element={<TeamLayout />}>
          <Route index element={<KnowledgePage />} />
          <Route path="*" element={<Navigate to="/team" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
