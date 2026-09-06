import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { Shield, Settings, AlertCircle, KeyRound, Globe } from 'lucide-react';

export const Navbar: React.FC = () => {
  const { baseUrl, isOnline, isChecking, token, openConnectModal, versionInfo } = useAuth();

  return (
    <header className="sticky top-0 z-40 flex h-16 w-full items-center justify-between border-b border-gray-800 bg-[#090d16]/90 px-6 backdrop-blur-md">
      {/* Brand & Version */}
      <div className="flex items-center space-x-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-600/20 border border-cyan-500/30 text-cyan-400 shadow-inner">
          <Shield className="h-5 w-5 drop-shadow-[0_0_8px_rgba(6,182,212,0.6)]" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-base font-bold tracking-wider text-white">AEGIS</span>
            <span className="rounded-full bg-cyan-950 px-2 py-0.5 text-[10px] font-semibold text-cyan-400 border border-cyan-800/60 uppercase tracking-wider">
              Phase 12 Control Plane
            </span>
          </div>
          <p className="text-[11px] text-gray-400 font-mono flex items-center gap-1.5">
            <span>Enterprise Agentic Core</span>
            {versionInfo && (
              <>
                <span className="text-gray-600">•</span>
                <span className="text-gray-300">v{versionInfo.version}</span>
              </>
            )}
          </p>
        </div>
      </div>

      {/* Connection & Auth Indicator Bar */}
      <div className="flex items-center space-x-4">
        {/* Backend Status Pill */}
        <div className="flex items-center space-x-2 rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-1.5 text-xs">
          {isChecking ? (
            <div className="flex items-center space-x-1.5 text-amber-400">
              <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
              <span>Polling...</span>
            </div>
          ) : isOnline ? (
            <div className="flex items-center space-x-1.5 text-emerald-400 font-medium">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span>API Online</span>
            </div>
          ) : (
            <div className="flex items-center space-x-1.5 text-rose-400 font-medium">
              <AlertCircle className="h-3.5 w-3.5" />
              <span>API Offline</span>
            </div>
          )}
        </div>

        {/* Target URL Pill */}
        <button
          onClick={openConnectModal}
          title="Click to configure API Base URL"
          className="hidden md:flex items-center space-x-1.5 rounded-lg border border-gray-800 bg-gray-900/40 px-3 py-1.5 text-xs text-gray-300 hover:border-gray-700 hover:text-white transition-colors font-mono"
        >
          <Globe className="h-3.5 w-3.5 text-cyan-400" />
          <span className="truncate max-w-[210px]">{baseUrl.replace(/^https?:\/\//, '')}</span>
        </button>

        {/* Auth Status Pill */}
        <button
          onClick={openConnectModal}
          className={`flex items-center space-x-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
            token
              ? 'border-emerald-500/30 bg-emerald-950/20 text-emerald-400 hover:bg-emerald-950/40'
              : 'border-amber-500/30 bg-amber-950/20 text-amber-400 hover:bg-amber-950/40'
          }`}
        >
          <KeyRound className="h-3.5 w-3.5" />
          <span>{token ? 'Authenticated (JWT)' : 'No Token'}</span>
        </button>

        {/* Connect / Settings Button */}
        <button
          onClick={openConnectModal}
          className="flex items-center space-x-1.5 rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-1.5 text-xs font-medium text-gray-200 hover:border-cyan-500 hover:text-cyan-400 hover:bg-gray-800 transition-colors"
        >
          <Settings className="h-4 w-4" />
          <span className="hidden sm:inline">Connect</span>
        </button>
      </div>
    </header>
  );
};
