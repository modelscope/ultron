import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useLocale } from '../contexts/LocaleContext';
import AuthOverlay from '../components/AuthOverlay';
import LocaleToggle from '../components/LocaleToggle';

const linkClass = ({ isActive }: { isActive: boolean }) =>
  isActive
    ? 'font-bold text-primary underline decoration-2 underline-offset-4'
    : 'hover:text-primary transition-colors';

const GITHUB_REPO_URL = 'https://github.com/modelscope/ultron';

export default function MainLayout() {
  const { user, logout } = useAuth();
  const { t } = useLocale();

  return (
    <>
      <AuthOverlay />
      <div className="h-screen flex flex-col bg-bg-page text-ink">
        <nav className="flex justify-between items-center px-5 py-3 border-b border-border bg-bg-page">
          <div className="flex items-center gap-8 translate-y-[2px]">
            <div className="font-bold text-2xl tracking-tighter font-serif leading-none">ULTRON</div>
            <div className="flex gap-4 text-sm leading-tight">
              <NavLink to="/dashboard" className={linkClass}>{t('nav.memories')}</NavLink>
              <NavLink to="/skills" className={linkClass}>{t('nav.skills')}</NavLink>
              <NavLink to="/leaderboard" className={linkClass}>{t('nav.leaderboard')}</NavLink>
              <NavLink to="/quickstart" className={linkClass}>{t('nav.quickstart')}</NavLink>
              <NavLink to="/harness" className={linkClass}>{t('nav.harness')}</NavLink>
            </div>
          </div>
          <div className="flex items-center gap-4 translate-y-[2px]">
            {user ? (
              <>
                <span className="text-xs text-muted">
                  {t('auth.signedInAs')} <span className="font-semibold text-ink">{user.username}</span>
                </span>
                <button type="button" className="btn-outline text-xs" onClick={logout}>{t('auth.signOut')}</button>
              </>
            ) : (
              <NavLink to="/harness" className="btn-outline text-xs">
                {t('auth.signIn')}
              </NavLink>
            )}
            <a
              href={GITHUB_REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted hover:text-ink transition-colors p-1 rounded-sm -m-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              aria-label={t('nav.github')}
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
              </svg>
            </a>
            <LocaleToggle />
          </div>
        </nav>
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </>
  );
}
