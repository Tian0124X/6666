import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useEffect } from "react";
import { Layout } from "./components/Layout";
import { useThemeStore } from "./stores/themeStore";
import { useAuthStore } from "./stores/authStore";
import ChatPage from "./pages/ChatPage";
import ToolsPage from "./pages/ToolsPage";
import KnowledgePage from "./pages/KnowledgePage";
import MonitoringPage from "./pages/MonitoringPage";
import EvalPage from "./pages/EvalPage";
import HistoryPage from "./pages/HistoryPage";
import SettingsPage from "./pages/SettingsPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import LoginPage from "./pages/LoginPage";

function ThemeInit() {
  const { theme } = useThemeStore();
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);
  return null;
}

function AuthInit() {
  const restore = useAuthStore((s) => s.restore);
  useEffect(() => { restore(); }, [restore]);
  return null;
}

/** 路由守卫: 未登录重定向到 /login */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);
  if (!isLoggedIn) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeInit />
      <AuthInit />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<ChatPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="tools" element={<ToolsPage />} />
          <Route path="knowledge" element={<KnowledgePage />} />
          <Route path="monitoring" element={<MonitoringPage />} />
          <Route path="eval" element={<EvalPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
