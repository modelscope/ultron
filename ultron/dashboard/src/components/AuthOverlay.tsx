import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useLocale } from '../contexts/LocaleContext';
import LocaleToggle from './LocaleToggle';

/** Login is required only on HarnessHub; other routes are usable without an account. */
function isHarnessPath(pathname: string) {
  return pathname === '/harness' || pathname.startsWith('/harness/');
}

export default function AuthOverlay() {
  const { pathname } = useLocation();
  const needsHarnessAuth = isHarnessPath(pathname);
  const { t } = useLocale();
  const { user, loading, login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (!needsHarnessAuth) return null;

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-page">
        <div className="absolute top-4 right-4">
          <LocaleToggle />
        </div>
        <div className="text-muted text-sm">{t('auth.loading')}</div>
      </div>
    );
  }

  if (user) return null;

  const handleSubmit = async () => {
    if (!username || !password) { setError(t('auth.fillFields')); return; }
    if (mode === 'register' && username.length < 3) { setError(t('auth.usernameMin')); return; }
    if (mode === 'register' && password.length < 6) { setError(t('auth.passwordMin')); return; }
    setBusy(true);
    setError('');
    const err = mode === 'login'
      ? await login(username, password)
      : await register(username, password);
    if (err) setError(err);
    setBusy(false);
  };

  const onKey = (e: React.KeyboardEvent) => { if (e.key === 'Enter') handleSubmit(); };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-page">
      <div className="absolute top-4 right-4 z-10">
        <LocaleToggle />
      </div>
      <div className="card-panel p-8 w-full max-w-[380px] shadow-soft animate-slide-up">
        <h2 className="text-2xl font-bold font-serif text-center mb-1">ULTRON</h2>
        <p className="text-muted text-sm text-center mb-2">
          {mode === 'login' ? t('auth.signInTitle') : t('auth.createAccountTitle')}
        </p>
        <p className="text-center mb-6">
          <Link to="/dashboard" className="text-primary text-sm underline underline-offset-2">
            {t('auth.backWithoutSignIn')}
          </Link>
        </p>

        {error && <div className="text-danger text-sm text-center mb-3">{error}</div>}

        <div className="space-y-3">
          <input
            type="text"
            placeholder={t('auth.username')}
            value={username}
            onChange={e => setUsername(e.target.value)}
            onKeyDown={onKey}
            className="w-full"
            autoComplete="username"
          />
          <input
            type="password"
            placeholder={t('auth.password')}
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={onKey}
            className="w-full"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />
          <button className="btn-primary w-full" disabled={busy} onClick={handleSubmit}>
            {mode === 'login' ? t('auth.signIn') : t('auth.createAccount')}
          </button>
        </div>

        <p className="text-muted text-sm text-center mt-5">
          {mode === 'login' ? (
            <>{t('auth.noAccount')} <button type="button" className="text-primary underline bg-transparent border-none p-0 text-sm" onClick={() => { setMode('register'); setError(''); }}>{t('auth.createOne')}</button></>
          ) : (
            <>{t('auth.haveAccount')} <button type="button" className="text-primary underline bg-transparent border-none p-0 text-sm" onClick={() => { setMode('login'); setError(''); }}>{t('auth.signInLink')}</button></>
          )}
        </p>
      </div>
    </div>
  );
}
