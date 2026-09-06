import React, { useState } from 'react';
import {
  createOrchestration,
  getOrchestration,
  getOrchestrationWorkers,
  getOrchestrationResults,
} from '../api/client';
import type {
  OrchestrationResponse,
  WorkerState,
  OrchestrationResultsResponse,
} from '../types/aegis';
import {
  Network,
  Users,
  GitBranch,
  Play,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Clock,
  Send,
  Search,
  Bot,
} from 'lucide-react';

export const OrchestrationViewer: React.FC = () => {
  const [orchestrationId, setOrchestrationId] = useState<string>('');
  const [orchestration, setOrchestration] = useState<OrchestrationResponse | null>(null);
  const [workers, setWorkers] = useState<WorkerState[]>([]);
  const [results, setResults] = useState<OrchestrationResultsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Dispatch form state
  const [goal, setGoal] = useState<string>(
    'Synthesize financial compliance report and verify cross-region data controls'
  );
  const [tenantId, setTenantId] = useState<string>('tenant-production');
  const [maxWorkers, setMaxWorkers] = useState<number>(4);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const fetchOrchestrationData = async (idToFetch?: string) => {
    const id = (idToFetch || orchestrationId).trim();
    if (!id) return;
    setLoading(true);
    setError(null);

    try {
      const [orchRes, workersRes, resultsRes] = await Promise.allSettled([
        getOrchestration(id),
        getOrchestrationWorkers(id),
        getOrchestrationResults(id),
      ]);

      if (orchRes.status === 'fulfilled') {
        setOrchestration(orchRes.value);
      } else {
        throw new Error('Orchestration not found or unreachable');
      }

      if (workersRes.status === 'fulfilled') {
        setWorkers(workersRes.value.workers || []);
      } else {
        setWorkers([]);
      }

      if (resultsRes.status === 'fulfilled') {
        setResults(resultsRes.value);
      } else {
        setResults(null);
      }
    } catch (err: unknown) {
      const e = err as Error;
      setError(e.message || 'Failed to fetch multi-agent orchestration');
    } finally {
      setLoading(false);
    }
  };

  const handleLaunchOrchestration = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const res = await createOrchestration({
        goal,
        tenant_id: tenantId,
        max_workers: Number(maxWorkers),
      });
      setOrchestrationId(res.orchestration_id);
      setOrchestration(res);
      await fetchOrchestrationData(res.orchestration_id);
    } catch (err: unknown) {
      const e = err as Error;
      setSubmitError(e.message || 'Failed to dispatch multi-agent orchestration');
    } finally {
      setIsSubmitting(false);
    }
  };

  const getWorkerStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case 'EXECUTING':
      case 'RUNNING':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-cyan-950 px-2 py-0.5 text-[10px] font-semibold text-cyan-400 border border-cyan-800 animate-pulse">
            <RefreshCw className="w-2.5 h-2.5 animate-spin" /> EXECUTING
          </span>
        );
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 border border-emerald-800">
            <CheckCircle2 className="w-2.5 h-2.5" /> COMPLETED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-gray-800 px-2 py-0.5 text-[10px] font-semibold text-gray-300 border border-gray-700">
            <Clock className="w-2.5 h-2.5" /> {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-gray-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <Network className="w-6 h-6 text-cyan-400" />
            Multi-Agent Orchestration & DAG Planner
          </h1>
          <p className="text-xs text-gray-400 mt-1">
            Dynamic DAG decomposition, specialized worker allocation, consensus verification, and conflict resolution.
          </p>
        </div>

        <button
          onClick={() => fetchOrchestrationData()}
          disabled={loading || !orchestrationId.trim()}
          className="flex items-center space-x-1.5 rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-1.5 text-xs font-medium text-gray-200 hover:border-cyan-500 hover:text-cyan-400 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh DAG</span>
        </button>
      </div>

      {/* Lookup & Creation Row */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Launch Form */}
        <div className="lg:col-span-6 rounded-xl border border-gray-800 bg-gray-900/50 p-5 space-y-4">
          <div className="flex items-center space-x-2 border-b border-gray-800 pb-3">
            <Play className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">
              Dispatch Multi-Agent Mission (POST /api/v1/orchestrations)
            </h3>
          </div>

          <form onSubmit={handleLaunchOrchestration} className="space-y-4">
            <div>
              <label className="text-xs font-medium text-gray-400">Mission Goal</label>
              <textarea
                rows={2}
                required
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-xs text-gray-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-400">Tenant ID</label>
                <input
                  type="text"
                  required
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs font-mono text-gray-100 focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-400">Max Worker Agents</label>
                <input
                  type="number"
                  min={1}
                  max={16}
                  value={maxWorkers}
                  onChange={(e) => setMaxWorkers(Number(e.target.value))}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs font-mono text-gray-100 focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>

            {submitError && (
              <div className="rounded-lg border border-rose-500/30 bg-rose-950/30 p-2.5 text-xs text-rose-300">
                {submitError}
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full flex items-center justify-center space-x-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 px-4 py-2 text-xs font-medium text-white transition-colors disabled:opacity-50"
            >
              {isSubmitting ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Planning DAG & Spawning Agents...</span>
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" />
                  <span>Decompose & Launch Orchestration</span>
                </>
              )}
            </button>
          </form>
        </div>

        {/* Existing Orchestration Search Bar */}
        <div className="lg:col-span-6 rounded-xl border border-gray-800 bg-gray-900/50 p-5 space-y-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center space-x-2 border-b border-gray-800 pb-3">
              <Search className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-white">Inspect Existing Orchestration</h3>
            </div>
            <p className="text-xs text-gray-400 mt-2">
              Query an active or historic orchestration DAG to view assigned agent workers and subtask outputs.
            </p>

            <div className="mt-4 flex gap-2">
              <input
                type="text"
                value={orchestrationId}
                onChange={(e) => setOrchestrationId(e.target.value)}
                placeholder="Orchestration ID (e.g., orch-8f19...)"
                className="flex-1 rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs font-mono text-gray-100 placeholder-gray-500 focus:border-cyan-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => fetchOrchestrationData()}
                className="rounded-lg bg-gray-800 hover:bg-gray-700 border border-gray-700 px-4 py-1.5 text-xs font-medium text-gray-200 transition-colors"
              >
                Inspect
              </button>
            </div>
          </div>

          {orchestration && (
            <div className="rounded-lg bg-gray-950/80 border border-gray-800 p-3 text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-gray-400">Status:</span>
                <span className="font-mono text-cyan-400 font-semibold">{orchestration.status}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Created:</span>
                <span className="font-mono text-gray-400">
                  {new Date(orchestration.created_at).toLocaleString()}
                </span>
              </div>
              <div className="text-gray-300 truncate">
                <span className="text-gray-500">Goal:</span> {orchestration.goal}
              </div>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-4 text-xs text-rose-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Workers and DAG Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Worker Agents Pool */}
        <div className="lg:col-span-5 rounded-xl border border-gray-800 bg-gray-900/30 p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-gray-800 pb-3">
            <div className="flex items-center space-x-2">
              <Users className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-white">
                Assigned Worker Agents ({workers.length})
              </h3>
            </div>
          </div>

          {workers.length === 0 ? (
            <div className="py-12 text-center text-gray-500 text-xs">
              No worker agents active for this orchestration instance.
            </div>
          ) : (
            <div className="space-y-3">
              {workers.map((worker) => (
                <div
                  key={worker.worker_id}
                  className="rounded-lg border border-gray-800 bg-gray-950/80 p-3.5 space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <Bot className="w-4 h-4 text-cyan-400" />
                      <span className="text-xs font-mono font-bold text-white">
                        {worker.worker_id}
                      </span>
                    </div>
                    {getWorkerStatusBadge(worker.status)}
                  </div>
                  <div className="text-xs text-gray-300">
                    <span className="text-gray-500">Role: </span>
                    <span className="font-semibold text-cyan-300">{worker.role}</span>
                  </div>
                  {worker.current_step && (
                    <div className="text-xs font-mono text-gray-400">
                      <span className="text-gray-600">Current Step: </span>
                      {worker.current_step}
                    </div>
                  )}
                  {worker.assigned_task_id && (
                    <div className="text-[11px] font-mono text-gray-500">
                      Task: {worker.assigned_task_id}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* DAG Plan & Outputs */}
        <div className="lg:col-span-7 rounded-xl border border-gray-800 bg-gray-900/30 p-5 space-y-4">
          <div className="flex items-center space-x-2 border-b border-gray-800 pb-3">
            <GitBranch className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">DAG Plan & Synthesis Output</h3>
          </div>

          {orchestration?.plan?.steps ? (
            <div className="space-y-3">
              <span className="text-xs font-medium text-gray-400">Decomposed DAG Plan Steps:</span>
              <div className="space-y-2">
                {orchestration.plan.steps.map((step, idx) => (
                  <div
                    key={step.step_id || idx}
                    className="p-3 rounded-lg border border-gray-800 bg-gray-950 text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <span className="px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 font-mono text-[11px] font-bold">
                          Step #{idx + 1}
                        </span>
                        <span className="text-white font-medium">{step.description}</span>
                      </div>
                      <span className="text-gray-400 font-mono text-[11px]">Role: {step.role}</span>
                    </div>
                    {step.dependencies && step.dependencies.length > 0 && (
                      <div className="text-[11px] font-mono text-gray-500">
                        Depends on: {step.dependencies.join(', ')}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="p-4 rounded-lg bg-gray-950 text-xs font-mono text-gray-400">
              {orchestration ? (
                <pre className="max-h-56 overflow-y-auto">
                  {JSON.stringify(orchestration.plan || { message: 'Direct execution without plan tree' }, null, 2)}
                </pre>
              ) : (
                'Select or launch an orchestration to inspect its plan DAG.'
              )}
            </div>
          )}

          {results && (
            <div className="mt-4 pt-4 border-t border-gray-800 space-y-2">
              <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> Final Synthesized Output:
              </span>
              <pre className="rounded-lg bg-gray-950 border border-gray-800 p-3 text-xs font-mono text-gray-200 max-h-48 overflow-y-auto">
                {JSON.stringify(results.final_output || results, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
