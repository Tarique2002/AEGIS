import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Key, Globe, CheckCircle, XCircle, RefreshCw, X, Shield, Sparkles } from 'lucide-react';
import { issueAccessToken } from '../../api/client';

export const ConnectModal: React.FC = () => {
  const {
    token,
    baseUrl,
    isOnline,
    isChecking,
    isConnectModalOpen,
    closeConnectModal,
    updateToken,
    updateBaseUrl,
    refreshStatus,
  } = useAuth();

  const [inputUrl, setInputUrl] = useState(baseUrl);
  const [inputToken, setInputToken] = useState(token || '');
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateMsg, setGenerateMsg] = useState<{ text: string; isError: boolean } | null>(null);

  if (!isConnectModalOpen) return null;

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    updateBaseUrl(inputUrl);
    updateToken(inputToken.trim() || null);
    setSaveSuccess(true);
    setTimeout(() => {
      setSaveSuccess(false);
      closeConnectModal();
    }, 800);
  };

  const handleClearToken = () => {
    setInputToken('');
    updateToken(null);
    setGenerateMsg(null);
  };

  const handleResetUrl = () => {
    const defaultUrl = 'https://aegis-api-gzky.onrender.com';
    setInputUrl(defaultUrl);
    updateBaseUrl(defaultUrl);
  };

  const handleAutoGenerateToken = async () => {
    setIsGenerating(true);
    setGenerateMsg(null);
    try {
      const res = await issueAccessToken({
        email: 'operator@aegis.io',
        roles: ['ADMIN', 'OPERATOR'],
        scopes: ['*'],
      });
      setInputToken(res.access_token);
      updateToken(res.access_token);
      setGenerateMsg({ text: 'Operator token generated and applied successfully!', isError: false });
      setSaveSuccess(true);
      setTimeout(() => {
        setSaveSuccess(false);
        closeConnectModal();
      }, 1000);
    } catch (err: unknown) {
      const e = err as Error;
      setGenerateMsg({
        text: `Cluster token issuance endpoint unavailable: ${e.message}. You can paste an existing JWT token.`,
        isError: true,
      });
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4">
      <div className="w-full max-w-lg rounded-xl border border-gray-800 bg-[#0f172a] p-6 shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-800 pb-4">
          <div className="flex items-center space-x-2">
            <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">Connect to AEGIS API</h3>
              <p className="text-xs text-gray-400">Configure endpoint & production bearer credentials</p>
            </div>
          </div>
          <button
            onClick={closeConnectModal}
            className="rounded-lg p-1 text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSave} className="mt-5 space-y-4">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-medium uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-cyan-400" />
                API Endpoint Base URL
              </label>
              <button
                type="button"
                onClick={handleResetUrl}
                className="text-[11px] text-cyan-400 hover:underline"
              >
                Reset to Render Production
              </button>
            </div>
            <input
              type="url"
              required
              value={inputUrl}
              onChange={(e) => setInputUrl(e.target.value)}
              placeholder="https://aegis-api-gzky.onrender.com"
              className="w-full rounded-lg border border-gray-700 bg-gray-900/90 px-3.5 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 focus:outline-none font-mono"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs font-medium uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5 text-amber-400" />
                Bearer Authorization Token (JWT)
              </label>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleAutoGenerateToken}
                  disabled={isGenerating}
                  className="text-[11px] text-cyan-400 hover:text-cyan-300 hover:underline flex items-center gap-1 disabled:opacity-50"
                  title="Request signed operator token from cluster"
                >
                  <Sparkles className="w-3 h-3 text-cyan-400" />
                  {isGenerating ? 'Generating...' : 'Auto-Generate Token'}
                </button>
                {token && (
                  <>
                    <span className="text-gray-600">•</span>
                    <button
                      type="button"
                      onClick={handleClearToken}
                      className="text-[11px] text-red-400 hover:underline"
                    >
                      Clear
                    </button>
                  </>
                )}
              </div>
            </div>
            <textarea
              rows={3}
              value={inputToken}
              onChange={(e) => setInputToken(e.target.value)}
              placeholder="Paste Bearer JWT token from your identity provider or test principal..."
              className="w-full rounded-lg border border-gray-700 bg-gray-900/90 px-3.5 py-2 text-xs text-gray-100 placeholder-gray-500 focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none font-mono resize-none"
            />
            {generateMsg && (
              <p
                className={`mt-1.5 text-[11px] ${
                  generateMsg.isError ? 'text-amber-400' : 'text-emerald-400'
                }`}
              >
                {generateMsg.text}
              </p>
            )}
            <p className="mt-1 text-[11px] text-gray-400">
              Note: Read-only health probes are public. State-mutating APIs require an authenticated tenant JWT.
            </p>
          </div>

          <div className="rounded-lg border border-gray-800 bg-gray-950/60 p-3 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">Backend Live:</span>
                {isChecking ? (
                  <span className="flex items-center gap-1 text-xs text-amber-400">
                    <RefreshCw className="w-3 h-3 animate-spin" /> Checking
                  </span>
                ) : isOnline ? (
                  <span className="flex items-center gap-1 text-xs text-emerald-400 font-medium">
                    <CheckCircle className="w-3.5 h-3.5" /> Online (200 OK)
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs text-rose-400 font-medium">
                    <XCircle className="w-3.5 h-3.5" /> Unreachable
                  </span>
                )}
              </div>
            </div>

            <button
              type="button"
              onClick={() => refreshStatus()}
              disabled={isChecking}
              className="px-2.5 py-1 text-xs rounded border border-gray-700 hover:bg-gray-800 text-gray-300 transition-colors flex items-center gap-1"
            >
              <RefreshCw className={`w-3 h-3 ${isChecking ? 'animate-spin' : ''}`} />
              Ping
            </button>
          </div>

          <div className="flex items-center justify-end space-x-3 pt-3 border-t border-gray-800">
            <button
              type="button"
              onClick={closeConnectModal}
              className="px-4 py-2 text-xs font-medium text-gray-300 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 text-xs font-medium rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-colors flex items-center gap-1.5 shadow-lg shadow-cyan-900/20"
            >
              {saveSuccess ? (
                <>
                  <CheckCircle className="w-3.5 h-3.5" /> Saved!
                </>
              ) : (
                'Save Connection'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
