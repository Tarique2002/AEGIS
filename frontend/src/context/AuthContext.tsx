import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  getAuthToken,
  setAuthToken,
  getBaseUrl,
  setBaseUrl as setClientBaseUrl,
  getHealthLive,
} from '../api/client';
import type { SystemLiveInfo } from '../types/aegis';

interface AuthContextType {
  token: string | null;
  baseUrl: string;
  isOnline: boolean;
  isChecking: boolean;
  versionInfo: SystemLiveInfo | null;
  isConnectModalOpen: boolean;
  updateToken: (token: string | null) => void;
  updateBaseUrl: (url: string) => void;
  openConnectModal: () => void;
  closeConnectModal: () => void;
  refreshStatus: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setTokenState] = useState<string | null>(getAuthToken());
  const [baseUrl, setBaseUrlState] = useState<string>(getBaseUrl());
  const [isOnline, setIsOnline] = useState<boolean>(false);
  const [isChecking, setIsChecking] = useState<boolean>(true);
  const [versionInfo, setVersionInfo] = useState<SystemLiveInfo | null>(null);
  const [isConnectModalOpen, setIsConnectModalOpen] = useState<boolean>(false);

  const refreshStatus = useCallback(async () => {
    setIsChecking(true);
    try {
      const live = await getHealthLive();
      if (
        live &&
        (live.status === 'live' ||
          live.status === 'ok' ||
          live.status === 'healthy' ||
          live.status === 'ready')
      ) {
        setIsOnline(true);
        setVersionInfo(live);
      } else {
        setIsOnline(false);
      }
    } catch {
      setIsOnline(false);
    } finally {
      setIsChecking(false);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    const interval = setInterval(refreshStatus, 30000); // 30s heartbeat
    return () => clearInterval(interval);
  }, [refreshStatus, baseUrl]);

  const updateToken = (newToken: string | null) => {
    setAuthToken(newToken);
    setTokenState(newToken);
    refreshStatus();
  };

  const updateBaseUrl = (newUrl: string) => {
    setClientBaseUrl(newUrl);
    setBaseUrlState(getBaseUrl());
    refreshStatus();
  };

  return (
    <AuthContext.Provider
      value={{
        token,
        baseUrl,
        isOnline,
        isChecking,
        versionInfo,
        isConnectModalOpen,
        updateToken,
        updateBaseUrl,
        openConnectModal: () => setIsConnectModalOpen(true),
        closeConnectModal: () => setIsConnectModalOpen(false),
        refreshStatus,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
