import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { checkAuth, login as apiLogin, register as apiRegister } from '../api/client';

interface User { username: string }

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (u: string, p: string) => Promise<string | null>;
  register: (u: string, p: string) => Promise<string | null>;
  logout: () => void;
}

const AuthContext = createContext<AuthCtx>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth().then(u => { setUser(u); setLoading(false); }).catch(() => setLoading(false));
    const onLogout = () => { setUser(null); };
    window.addEventListener('ultron-logout', onLogout);
    return () => window.removeEventListener('ultron-logout', onLogout);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const j = await apiLogin(username, password);
    if (!j.success) return j.detail || 'Login failed';
    localStorage.setItem('ultron-auth-token', j.data.token);
    localStorage.setItem('ultron-auth-user', JSON.stringify({ username: j.data.username }));
    setUser({ username: j.data.username });
    return null;
  }, []);

  const register = useCallback(async (username: string, password: string) => {
    const j = await apiRegister(username, password);
    if (!j.success) return j.detail || 'Registration failed';
    localStorage.setItem('ultron-auth-token', j.data.token);
    localStorage.setItem('ultron-auth-user', JSON.stringify({ username: j.data.username }));
    setUser({ username: j.data.username });
    return null;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('ultron-auth-token');
    localStorage.removeItem('ultron-auth-user');
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
