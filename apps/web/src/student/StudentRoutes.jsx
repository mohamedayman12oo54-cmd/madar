import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "../components/ProtectedRoute.jsx";
import StudentLayout from "./StudentLayout.jsx";
import HomePage from "./HomePage.jsx";
import RecordsPage from "./RecordsPage.jsx";
import VideosPage from "./VideosPage.jsx";
import VideoDetailPage from "./VideoDetailPage.jsx";
import { QuizzesPage, QuizPage } from "./QuizPages.jsx";
import NotificationsPage from "./NotificationsPage.jsx";
import SettingsPage from "./SettingsPage.jsx";
import AssistantPage from "./AssistantPage.jsx";

export default function StudentRoutes() {
  return (
    <Routes>
      <Route element={<ProtectedRoute role="student" requireEnvironment />}>
        <Route path="/learn" element={<StudentLayout />}>
          <Route index element={<HomePage />} />
          <Route path="records" element={<RecordsPage />} />
          <Route path="videos" element={<VideosPage />} />
          <Route path="videos/:id" element={<VideoDetailPage />} />
          <Route path="quizzes" element={<QuizzesPage />} />
          <Route path="quizzes/:id" element={<QuizPage />} />
          <Route path="assistant" element={<AssistantPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/learn" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
