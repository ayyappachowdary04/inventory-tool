'use client';
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';

type UserSession = {
  role: 'admin' | 'shopkeeper' | null;
  username?: string | null;
};

interface AuthContextType {
  session: UserSession;
  loginState: (role: 'admin' | 'shopkeeper', username?: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [session, setSession] = useState<UserSession>({ role: null });
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    // Check local storage on initial load
    const storedRole = localStorage.getItem('ws_role') as 'admin' | 'shopkeeper' | null;
    const storedUser = localStorage.getItem('ws_user');
    
    if (storedRole) {
      setSession({ role: storedRole, username: storedUser });
      
      // Auto redirect if on login page
      if (pathname === '/') {
        router.push(storedRole === 'admin' ? '/admin' : '/shopkeeper');
      }
    } else if (pathname !== '/') {
      // Not logged in and not on login page
      router.push('/');
    }
  }, [pathname, router]);

  const loginState = (role: 'admin' | 'shopkeeper', username?: string) => {
    localStorage.setItem('ws_role', role);
    if (username) localStorage.setItem('ws_user', username);
    setSession({ role, username });
    router.push(role === 'admin' ? '/admin' : '/shopkeeper');
  };

  const logout = () => {
    localStorage.removeItem('ws_role');
    localStorage.removeItem('ws_user');
    setSession({ role: null });
    router.push('/');
  };

  return (
    <AuthContext.Provider value={{ session, loginState, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
};
