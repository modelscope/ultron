import { Navigate, RouterProvider, createBrowserRouter } from 'react-router-dom';
import MainLayout from './layouts/MainLayout';
import DashboardPage from './pages/DashboardPage';
import SkillsPage from './pages/SkillsPage';
import LeaderboardPage from './pages/LeaderboardPage';
import QuickstartPage from './pages/QuickstartPage';
import HarnessPage from './pages/HarnessPage';
import { AuthProvider } from './hooks/useAuth';
import { LocaleProvider } from './contexts/LocaleContext';

const router = createBrowserRouter([
  {
    path: '/',
    element: <MainLayout />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'skills', element: <SkillsPage /> },
      { path: 'leaderboard', element: <LeaderboardPage /> },
      { path: 'quickstart', element: <QuickstartPage /> },
      { path: 'harness', element: <HarnessPage /> },
    ],
  },
]);

export default function App() {
  return (
    <AuthProvider>
      <LocaleProvider>
        <RouterProvider router={router} />
      </LocaleProvider>
    </AuthProvider>
  );
}
