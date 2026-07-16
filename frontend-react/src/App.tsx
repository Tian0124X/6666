import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useEffect } from "react";
import { Layout } from "./components/Layout";
import FeedbackPage from "./pages/FeedbackPage";
import KnowledgePage from "./pages/KnowledgePage";
import LoginPage from "./pages/LoginPage";
import RagPage from "./pages/RagPage";
import { useAuthStore } from "./stores/authStore";
import { useThemeStore } from "./stores/themeStore";

function ThemeInit() {
  const { theme } = useThemeStore();
  useEffect(() => { document.documentElement.classList.toggle("dark", theme === "dark"); }, [theme]);
  return null;
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isLoggedIn = useAuthStore((state) => state.isLoggedIn);
  const isRestoring = useAuthStore((state) => state.isRestoring);
  if (isRestoring) return <div className="h-screen grid place-items-center text-sm text-muted-foreground">正在加载…</div>;
  return isLoggedIn ? <>{children}</> : <Navigate to="/login" replace />;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((state) => state.user);
  return user?.role === "admin" ? <>{children}</> : <Navigate to="/" replace />;
}

export default function App() {
  const restore = useAuthStore((state) => state.restore);
  useEffect(() => { restore(); }, [restore]);
  return <BrowserRouter><ThemeInit /><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
      <Route index element={<RagPage />} />
      <Route path="knowledge" element={<KnowledgePage />} />
      <Route path="feedback" element={<AdminRoute><FeedbackPage /></AdminRoute>} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></BrowserRouter>;
}
