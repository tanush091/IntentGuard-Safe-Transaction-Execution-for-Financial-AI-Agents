import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { refreshSession, setAccessToken, setOnAuthLost } from '../api/client.js';
import api from '../api/endpoints.js';

const AuthCtx = createContext(null);

/**
 * Session state. On load, a silent refresh (HttpOnly cookie) restores the session without storing
 * any token in localStorage/sessionStorage (docs/SECURITY.md 3.4). Access tokens live 15 minutes and
 * are refreshed shortly before they expire.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [expiresIn, setExpiresIn] = useState(null);

  const adopt = useCallback((payload) => {
    setAccessToken(payload.access_token);
    setUser(payload.user);
    setExpiresIn(payload.expires_in);
  }, []);

  useEffect(() => {
    setOnAuthLost(() => setUser(null));
    refreshSession().then((p) => {
      if (p) adopt(p);
      setReady(true);
    });
  }, [adopt]);

  useEffect(() => {
    if (!user || !expiresIn) return undefined;
    const t = setTimeout(async () => {
      const p = await refreshSession();
      if (p) adopt(p);
      else setUser(null);
    }, Math.max(30, expiresIn - 60) * 1000);
    return () => clearTimeout(t);
  }, [user, expiresIn, adopt]);

  const login = useCallback(async (email, password) => {
    adopt(await api.login(email, password));
  }, [adopt]);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  return <AuthCtx.Provider value={{ user, ready, login, logout }}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  return useContext(AuthCtx);
}
