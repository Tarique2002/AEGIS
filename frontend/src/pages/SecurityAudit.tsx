import React, { useState, useEffect } from 'react';
import {
  simulatePolicy,
  getAuditCheckpoints,
  createAuditCheckpoint,
  verifyAuditCheckpoint,
} from '../api/client';
import type {
  AuditCheckpoint,
  AuditVerifyResponse,
  PolicySimulationResponse,
} from '../types/aegis';
import {
  ShieldCheck,
  Lock,
  FileCheck2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Plus,
  Play,
  Hash,
} from 'lucide-react';

export const SecurityAudit: React.FC = () => {
  // Policy Simulator state
  const [action, setAction] = useState<string>('task:execute');
  const [resource, setResource] = useState<string>('arn:aegis:tasks:generic_computation');
  const [principalJson, setPrincipalJson] = useState<string>(
    '{\n  "role": "agent_operator",\n  "tenant_id": "tenant-production"\n}'
  );
  const [contextJson, setContextJson] = useState<string>('{\n  "ip_verified": true\n}');
  const [simResult, setSimResult] = useState<PolicySimulationResponse | null>(null);
  const [simLoading, setSimLoading] = useState<boolean>(false);
  const [simError, setSimError] = useState<string | null>(null);

  // Checkpoints state
  const [checkpoints, setCheckpoints] = useState<AuditCheckpoint[]>([]);
  const [checkpointsLoading, setCheckpointsLoading] = useState<boolean>(false);
  const [verificationMap, setVerificationMap] = useState<
    Record<string, AuditVerifyResponse>
  >({});
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [checkpointError, setCheckpointError] = useState<string | null>(null);

  const fetchCheckpoints = async () => {
    setCheckpointsLoading(true);
    setCheckpointError(null);
    try {
      const res = await getAuditCheckpoints();
      setCheckpoints(Array.isArray(res) ? res : []);
    } catch (err: unknown) {
      const e = err as Error;
      setCheckpointError(e.message || 'Failed to fetch audit checkpoints');
    } finally {
      setCheckpointsLoading(false);
    }
  };

  useEffect(() => {
    fetchCheckpoints();
  }, []);

  const handleCreateCheckpoint = async () => {
    setCheckpointsLoading(true);
    setCheckpointError(null);
    try {
      await createAuditCheckpoint();
      await fetchCheckpoints();
    } catch (err: unknown) {
      const e = err as Error;
      setCheckpointError(e.message || 'Failed to create audit checkpoint');
    } finally {
      setCheckpointsLoading(false);
    }
  };

  const handleVerifyCheckpoint = async (id: string) => {
    setVerifyingId(id);
    try {
      const res = await verifyAuditCheckpoint(id);
      setVerificationMap((prev) => ({ ...prev, [id]: res }));
    } catch (err: unknown) {
      const e = err as Error;
      setCheckpointError(e.message || `Failed to verify checkpoint ${id}`);
    } finally {
      setVerifyingId(null);
    }
  };

  const handleSimulate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSimLoading(true);
    setSimError(null);
    try {
      let parsedPrincipal: Record<string, unknown> = {};
      let parsedContext: Record<string, unknown> = {};
      try {
        parsedPrincipal = JSON.parse(principalJson);
      } catch {
        throw new Error('Principal must be valid JSON');
      }
      try {
        parsedContext = JSON.parse(contextJson);
      } catch {
        throw new Error('Context must be valid JSON');
      }

      const res = await simulatePolicy({
        action,
        resource,
        principal: parsedPrincipal,
        context: parsedContext,
      });
      setSimResult(res);
    } catch (err: unknown) {
      const e = err as Error;
      setSimError(e.message || 'Policy simulation evaluation failed');
    } finally {
      setSimLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="border-b border-gray-800 pb-5">
        <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
          <ShieldCheck className="w-6 h-6 text-cyan-400" />
          Security Governance, RBAC & Merkle Audit
        </h1>
        <p className="text-xs text-gray-400 mt-1">
          Cryptographic Merkle tree verification of immutable log checkpoints and real-time RBAC policy simulation.
        </p>
      </div>

      {/* Split Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Policy Simulator */}
        <div className="lg:col-span-6 rounded-xl border border-gray-800 bg-gray-900/40 p-5 space-y-4">
          <div className="flex items-center space-x-2 border-b border-gray-800 pb-3">
            <Lock className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-semibold text-white">
              RBAC Policy Simulator (POST /api/v1/policies/simulate)
            </h2>
          </div>

          <form onSubmit={handleSimulate} className="space-y-3">
            <div>
              <label className="text-xs font-medium text-gray-400">Action Name</label>
              <input
                type="text"
                required
                value={action}
                onChange={(e) => setAction(e.target.value)}
                placeholder="e.g. task:execute, memory:write"
                className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs font-mono text-gray-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-400">Target Resource ARN</label>
              <input
                type="text"
                required
                value={resource}
                onChange={(e) => setResource(e.target.value)}
                placeholder="e.g. arn:aegis:tasks:*"
                className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs font-mono text-gray-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-400">Principal (JSON)</label>
                <textarea
                  rows={4}
                  value={principalJson}
                  onChange={(e) => setPrincipalJson(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs font-mono text-gray-100 focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-400">Context (JSON)</label>
                <textarea
                  rows={4}
                  value={contextJson}
                  onChange={(e) => setContextJson(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs font-mono text-gray-100 focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>

            {simError && (
              <div className="rounded-lg border border-rose-500/30 bg-rose-950/30 p-2 text-xs text-rose-300">
                {simError}
              </div>
            )}

            <button
              type="submit"
              disabled={simLoading}
              className="w-full flex items-center justify-center space-x-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 px-4 py-2 text-xs font-medium text-white transition-colors disabled:opacity-50"
            >
              {simLoading ? (
                <>
                  <RefreshCw className="w-3 h-3 animate-spin" />
                  <span>Evaluating Policy Engine...</span>
                </>
              ) : (
                <>
                  <Play className="w-3 h-3" />
                  <span>Simulate Policy Evaluation</span>
                </>
              )}
            </button>
          </form>

          {/* Simulation Output Card */}
          {simResult && (
            <div className="pt-3 border-t border-gray-800 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-400">Simulated Outcome:</span>
                {simResult.allowed ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950 px-2.5 py-0.5 text-xs font-bold text-emerald-400 border border-emerald-800">
                    <CheckCircle2 className="w-3.5 h-3.5" /> ALLOWED (200 OK)
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-rose-950 px-2.5 py-0.5 text-xs font-bold text-rose-400 border border-rose-800">
                    <XCircle className="w-3.5 h-3.5" /> DENIED (403 FORBIDDEN)
                  </span>
                )}
              </div>

              {simResult.matched_policies && simResult.matched_policies.length > 0 && (
                <div className="text-xs text-gray-300">
                  <span className="text-gray-500">Matched Rules: </span>
                  <span className="font-mono text-cyan-400">
                    {simResult.matched_policies.join(', ')}
                  </span>
                </div>
              )}

              {simResult.reason && (
                <div className="text-xs text-gray-400">
                  <span className="text-gray-500">Reason: </span>
                  {simResult.reason}
                </div>
              )}

              {simResult.eval_duration_ms !== undefined && (
                <div className="text-[11px] font-mono text-gray-500">
                  Latency: {simResult.eval_duration_ms.toFixed(2)}ms
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right: Merkle Checkpoints & Cryptographic Verification */}
        <div className="lg:col-span-6 rounded-xl border border-gray-800 bg-gray-900/40 p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-gray-800 pb-3">
            <div className="flex items-center space-x-2">
              <FileCheck2 className="w-4 h-4 text-cyan-400" />
              <h2 className="text-sm font-semibold text-white">
                Cryptographic Audit Checkpoints ({checkpoints.length})
              </h2>
            </div>

            <button
              onClick={handleCreateCheckpoint}
              disabled={checkpointsLoading}
              className="flex items-center space-x-1.5 rounded-lg border border-cyan-500/40 bg-cyan-950/30 hover:bg-cyan-950/60 px-3 py-1.5 text-xs font-medium text-cyan-400 transition-colors disabled:opacity-50"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Create Checkpoint</span>
            </button>
          </div>

          {checkpointError && (
            <div className="rounded-lg border border-rose-500/30 bg-rose-950/30 p-2.5 text-xs text-rose-300">
              {checkpointError}
            </div>
          )}

          {checkpoints.length === 0 ? (
            <div className="py-16 text-center text-gray-500 text-xs">
              <Hash className="w-8 h-8 mx-auto mb-2 opacity-30 text-cyan-400" />
              <p>No audit checkpoints recorded yet.</p>
              <p className="text-[11px] text-gray-600 mt-1">
                Click "Create Checkpoint" above to compute a Merkle root over the tamper-evident audit log.
              </p>
            </div>
          ) : (
            <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
              {checkpoints.map((cp) => {
                const verifyResult = verificationMap[cp.checkpoint_id];
                const isVerifying = verifyingId === cp.checkpoint_id;
                return (
                  <div
                    key={cp.checkpoint_id}
                    className="rounded-lg border border-gray-800 bg-gray-950 p-3.5 space-y-2.5"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <span className="font-mono text-xs font-bold text-white">
                          {cp.checkpoint_id}
                        </span>
                        <span className="px-1.5 py-0.2 rounded bg-gray-800 text-[10px] font-mono text-gray-400">
                          {cp.record_count} events
                        </span>
                      </div>

                      <button
                        onClick={() => handleVerifyCheckpoint(cp.checkpoint_id)}
                        disabled={isVerifying}
                        className="px-2.5 py-1 rounded-md bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-medium transition-colors flex items-center gap-1"
                      >
                        <RefreshCw className={`w-3 h-3 ${isVerifying ? 'animate-spin' : ''}`} />
                        <span>Verify Merkle Root</span>
                      </button>
                    </div>

                    <div className="text-[11px] font-mono text-gray-400 break-all bg-gray-900/70 p-2 rounded border border-gray-800">
                      <span className="text-gray-500 block text-[10px]">MERKLE ROOT HASH:</span>
                      <span className="text-cyan-400">{cp.root_hash}</span>
                    </div>

                    {/* Verification Result Banner */}
                    {verifyResult && (
                      <div
                        className={`p-2 rounded text-xs flex items-center justify-between border ${
                          verifyResult.verified
                            ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
                            : 'bg-rose-950/40 border-rose-800 text-rose-300'
                        }`}
                      >
                        <div className="flex items-center space-x-1.5">
                          {verifyResult.verified ? (
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                          )}
                          <span className="font-semibold">
                            {verifyResult.verified
                              ? 'Cryptographic Verification Passed (Zero Tampering)'
                              : 'Tampering Detected in Merkle Chain!'}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
