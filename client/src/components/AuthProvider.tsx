import { useEffect, type ReactNode } from 'react';
import { useAuthStore } from '../stores/auth';

interface AuthProviderProps {
  children: ReactNode;
}

/**
 * AuthProvider - Fetches the current user on app load
 *
 * Wraps the app and automatically fetches the authenticated user
 * from the server when the app first loads.
 */
function AuthProvider({ children }: AuthProviderProps) {
  const fetchUser = useAuthStore((s) => s.fetchUser);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  return <>{children}</>;
}

export default AuthProvider;
