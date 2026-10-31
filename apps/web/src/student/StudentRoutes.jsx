import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "../components/ProtectedRoute.jsx";
import StudentLayout from "./StudentLayout.jsx";
import HomePage from "./HomePage.jsx";
import RecordsPage from "./RecordsPage.jsx";
import VideosPage from "./VideosPage.jsx";
import VideoDetailPage from "./VideoDetailPage.jsx";
import MaterialPage from "./MaterialPage.jsx";
import { QuizzesPage, QuizPage } from "./QuizPages.jsx";
import NotificationsPage from "./NotificationsPage.jsx";
import SettingsPage from "./SettingsPage.jsx";
import AssistantPage from "./AssistantPage.jsx";
import { ExamsPage, ExamRunPage } from "./ExamPages.jsx";

export default function StudentRoutes() {
  return (
    <Routes>
      <Route element={<ProtectedRoute role="student" requireEnvironment />}>
        {/* Taking an exam is a focus mode WITHOUT the app's header and tabs: nothing to tap that leads away. */}
        <Route path="/learn/exams/:id" element={<ExamRunPage />} />
        <Route path="/learn" element={<StudentLayout />}>
          <Route index element={<HomePage />} />
          <Route path="records" element={<RecordsPage />} />
          <Route path="videos" element={<VideosPage />} />
          <Route path="videos/:id" element={<VideoDetailPage />} />
          <Route path="materials/:id" element={<MaterialPage />} />
          <Route path="quizzes" element={<QuizzesPage />} />
          <Route path="quizzes/:id" element={<QuizPage />} />
          <Route path="exams" element={<ExamsPage />} />
          <Route path="assistant" element={<AssistantPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/learn" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
