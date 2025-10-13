import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authApi } from '@/api/endpoints';
import type { User, LoginCredentials, RegisterData } from '@/types';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isVendor: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isVendor, setIsVendor] = useState(false);

  // Check if user is already logged in on mount
  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('access_token');
      
      if (token) {
        try {
          const response = await authApi.getProfile();
          setUser(response.data);
          setIsVendor(response.data.has_vendor_account);
        } catch (error) {
          // Token is invalid, clear storage
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
        }
      }
      
      setIsLoading(false);
    };

    initAuth();
  }, []);

  const login = async (credentials: LoginCredentials) => {
    try {
      const response = await authApi.login(credentials);
      const { user, tokens, is_vendor } = response.data;

      // Store tokens
      localStorage.setItem('access_token', tokens.access);
      localStorage.setItem('refresh_token', tokens.refresh);

      // Update state
      setUser(user);
      setIsVendor(is_vendor);
    } catch (error) {
      throw error;
    }
  };

  const register = async (data: RegisterData) => {
    try {
      const response = await authApi.register(data);
      const { user, tokens, is_vendor } = response.data;

      // Store tokens
      localStorage.setItem('access_token', tokens.access);
      localStorage.setItem('refresh_token', tokens.refresh);

      // Update state
      setUser(user);
      setIsVendor(is_vendor);
    } catch (error) {
      throw error;
    }
  };

  const logout = () => {
    const refreshToken = localStorage.getItem('refresh_token');
    
    // Call logout endpoint (don't await, just fire and forget)
    if (refreshToken) {
      authApi.logout(refreshToken).catch(() => {
        // Ignore errors
      });
    }

    // Clear local storage
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');

    // Clear state
    setUser(null);
    setIsVendor(false);
  };

  const refreshUser = async () => {
    try {
      const response = await authApi.getProfile();
      setUser(response.data);
      setIsVendor(response.data.has_vendor_account);
    } catch (error) {
      console.error('Failed to refresh user:', error);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        isVendor,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}