import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import Layout from './Layout';
import Dashboard from './pages/Dashboard';
import Logs from './pages/Logs';
import LlmConfig from './pages/LlmConfig';
import Papers from './pages/Papers';
import SchedulePage from './pages/Schedule';
import SmtpConfigPage from './pages/SmtpConfig';
import Subscribers from './pages/Subscribers';
import { ToastProvider } from './ui';
import { getToken, redirectToLogin } from './api';

/** 无 token 时直接回到登录页（登录页是独立静态 index.html） */
function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!getToken()) {
    redirectToLogin();
    return null;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <ToastProvider>
      <HashRouter>
        <RequireAuth>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="subscribers" element={<Subscribers />} />
              <Route path="papers" element={<Papers />} />
              <Route path="llm" element={<LlmConfig />} />
              <Route path="smtp" element={<SmtpConfigPage />} />
              <Route path="schedule" element={<SchedulePage />} />
              <Route path="logs" element={<Logs />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </RequireAuth>
      </HashRouter>
    </ToastProvider>
  );
}
