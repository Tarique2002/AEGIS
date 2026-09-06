import React, { useState, useEffect } from 'react';
import {
  getHealthReady,
  getLearningStats,
  createTask,
} from '../api/client';
import type { SystemHealth, LearningStatsResponse, TaskResponse } from '../types/aegis';
import {
  Activity,
  Database,
  Server,
  Zap,
  CheckCircle2,
  XCircle,
  Clock,
  Play,
  RefreshCw,
  AlertTriangle,
  ArrowRight,
  Send,
  Key,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface MissionControlProps {
  onNavigateToTask: (taskId: string) => void;
}

export const MissionControl: React.FC<MissionControlProps> = ({ onNavigateToTask }) => {
  const { openConnectModal } = useAuth();
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [stats, setStats] = useState<LearningStatsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Quick Task Dispatcher state
  const [taskType, setTaskType] = useState<string>('generic_computation');
  const [tenantId, setTenantId] = useState<string>('tenant-production');
  const [taskInput, setTaskInput] = useState<string>('{\n  "query": "Evaluate policy rules and compute trajectory"\n}');
  const [taskDescription, setTaskDescription] = useState<string>('Production Mission Dispatch');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [createdTask, setCreatedTask] = useState<TaskResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const fetchDashboardData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [hRes, sRes] = await Promise.allSettled([
        getHealthReady(),
        getLearningStats(),
      ]);

      if (hRes.status === 'fulfilled') {
        setHealth(hRes.value);
      } else {
        setHealth({ status: 'degraded' });
      }

      if (sRes.status === 'fulfilled') {
        setStats(sRes.value);
      } else {
        // Learning stats might require auth or be empty on fresh db
        setStats(null);
      }
    } catch (err: unknown) {
      const e = err as Error;
      setError(e.message || 'Failed to fetch mission control data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const handleDispatchTask = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      let parsedInput: Record<string, unknown> = {};
      try {
        parsedInput = JSON.parse(taskInput);
      } catch {
        throw new Error('Task input must be valid JSON');
      }

      const res = await createTask({
        objective: taskDescription.trim() || 'Production Mission Dispatch',
        metadata: {
          task_type: taskType,
          tenant_id: tenantId,
          ...parsedInput,
        },
      });
      setCreatedTask(res);
    } catch (err: unknown) {
      const e = err as Error;
      setSubmitError(e.message || 'Failed to dispatch task');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-gray-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <Activity className="w-6 h-6 text-cyan-400" />
            Mission Control & Live Telemetry
          </h1>
          <p className="text-xs text-gray-400 mt-1">
            Real-time backend dependency health, learning telemetry counters, and mission dispatch.
          </p>
        </div>

        <button
          onClick={fetchDashboardData}
          disabled={loading}
          className="self-start sm:self-auto flex items-center space-x-2 rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-1.5 text-xs font-medium text-gray-200 hover:border-cyan-500 hover:text-cyan-400 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Telemetry</span>
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-4 text-xs text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Dependencies Grid */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3 flex items-center gap-2">
          <Server className="w-4 h-4 text-cyan-400" />
          Subsystem Dependencies (/health/ready)
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Database Card */}
          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400 font-medium">PostgreSQL Store</span>
              <Database className="w-4 h-4 text-blue-400" />
            </div>
            <div className="mt-2 flex items-baseline justify-between">
              <span className="text-base font-bold text-white">Primary DB</span>
              {health?.dependencies?.database === 'healthy' || health?.dependencies?.database === true ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950/80 px-2 py-0.5 text-[11px] font-medium text-emerald-400 border border-emerald-800">
                  <CheckCircle2 className="w-3 h-3" /> Healthy
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full bg-rose-950/80 px-2 py-0.5 text-[11px] font-medium text-rose-400 border border-rose-800">
                  <XCircle className="w-3 h-3" /> Offline
                </span>
              )}
            </div>
            <p className="mt-1 text-[11px] text-gray-500 font-mono">
              Status: {String(health?.dependencies?.database ?? 'Checking')}
            </p>
          </div>

          {/* Redis Card */}
          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400 font-medium">Redis Cluster</span>
              <Zap className="w-4 h-4 text-amber-400" />
            </div>
            <div className="mt-2 flex items-baseline justify-between">
              <span className="text-base font-bold text-white">Event Bus</span>
              {health?.dependencies?.redis === 'healthy' || health?.dependencies?.redis === true ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950/80 px-2 py-0.5 text-[11px] font-medium text-emerald-400 border border-emerald-800">
                  <CheckCircle2 className="w-3 h-3" /> Healthy
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full bg-rose-950/80 px-2 py-0.5 text-[11px] font-medium text-rose-400 border border-rose-800">
                  <XCircle className="w-3 h-3" /> Offline
                </span>
              )}
            </div>
            <p className="mt-1 text-[11px] text-gray-500 font-mono">
              Status: {String(health?.dependencies?.redis ?? 'Checking')}
            </p>
          </div>

          {/* Qdrant Card */}
          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400 font-medium">Qdrant Vector DB</span>
              <Database className="w-4 h-4 text-cyan-400" />
            </div>
            <div className="mt-2 flex items-baseline justify-between">
              <span className="text-base font-bold text-white">Embeddings</span>
              {health?.dependencies?.qdrant === 'healthy' || health?.dependencies?.qdrant === true ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950/80 px-2 py-0.5 text-[11px] font-medium text-emerald-400 border border-emerald-800">
                  <CheckCircle2 className="w-3 h-3" /> Healthy
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full bg-rose-950/80 px-2 py-0.5 text-[11px] font-medium text-rose-400 border border-rose-800">
                  <XCircle className="w-3 h-3" /> Offline
                </span>
              )}
            </div>
            <p className="mt-1 text-[11px] text-gray-500 font-mono">
              Status: {String(health?.dependencies?.qdrant ?? 'Checking')}
            </p>
          </div>

          {/* Engine Status Card */}
          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400 font-medium">Core Readiness</span>
              <Server className="w-4 h-4 text-purple-400" />
            </div>
            <div className="mt-2 flex items-baseline justify-between">
              <span className="text-base font-bold text-white">Engine Core</span>
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium border ${
                  health?.status === 'ready'
                    ? 'bg-emerald-950/80 text-emerald-400 border-emerald-800'
                    : 'bg-amber-950/80 text-amber-400 border-amber-800'
                }`}
              >
                {health?.status === 'ready' ? (
                  <>
                    <CheckCircle2 className="w-3 h-3" /> Ready
                  </>
                ) : (
                  health?.status || 'Unknown'
                )}
              </span>
            </div>
            <p className="mt-1 text-[11px] text-gray-500 font-mono">
              API: Render Deployed
            </p>
          </div>
        </div>
      </div>

      {/* Telemetry Metrics */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3 flex items-center gap-2">
          <Activity className="w-4 h-4 text-cyan-400" />
          Autonomous Learning Telemetry (/api/v1/learning/stats)
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4">
            <span className="text-xs text-gray-400">Total Trajectories</span>
            <div className="mt-2 text-2xl font-bold font-mono text-white">
              {stats?.total_trajectories ?? 0}
            </div>
            <div className="mt-1 flex items-center space-x-2 text-[11px]">
              <span className="text-emerald-400 font-mono">
                {stats?.successful_trajectories ?? 0} passed
              </span>
              <span className="text-gray-600">•</span>
              <span className="text-rose-400 font-mono">
                {stats?.failed_trajectories ?? 0} failed
              </span>
            </div>
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4">
            <span className="text-xs text-gray-400">Total Procedures</span>
            <div className="mt-2 text-2xl font-bold font-mono text-cyan-400">
              {stats?.total_procedures ?? 0}
            </div>
            <div className="mt-1 text-[11px] text-gray-400">
              Discovered from execution runs
            </div>
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4">
            <span className="text-xs text-gray-400">Promoted to Prod</span>
            <div className="mt-2 text-2xl font-bold font-mono text-emerald-400">
              {stats?.promoted_procedures ?? 0}
            </div>
            <div className="mt-1 text-[11px] text-gray-400">
              Passed Phase 12 validation gate
            </div>
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4">
            <span className="text-xs text-gray-400">Success Rate</span>
            <div className="mt-2 text-2xl font-bold font-mono text-purple-400">
              {stats && stats.total_trajectories > 0
                ? `${((stats.successful_trajectories / stats.total_trajectories) * 100).toFixed(1)}%`
                : '100%'}
            </div>
            <div className="mt-1 text-[11px] text-gray-400">
              Monitored execution pipeline
            </div>
          </div>
        </div>
      </div>

      {/* Task Dispatcher Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Dispatch Form */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
          <div className="flex items-center space-x-2 border-b border-gray-800 pb-3 mb-4">
            <Play className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">Live Task Dispatcher (POST /api/v1/tasks)</h3>
          </div>

          <form onSubmit={handleDispatchTask} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-400">Task Type</label>
                <input
                  type="text"
                  required
                  value={taskType}
                  onChange={(e) => setTaskType(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-100 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-400">Tenant ID</label>
                <input
                  type="text"
                  required
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-100 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-gray-400">Description</label>
              <input
                type="text"
                value={taskDescription}
                onChange={(e) => setTaskDescription(e.target.value)}
                className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-400">Input Data (JSON)</label>
              <textarea
                rows={4}
                required
                value={taskInput}
                onChange={(e) => setTaskInput(e.target.value)}
                className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-xs font-mono text-gray-200 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            {submitError && (
              <div className="rounded-lg border border-rose-500/30 bg-rose-950/30 p-3 text-xs text-rose-300 space-y-2">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-rose-200">
                      {submitError.includes('401') ? 'Authentication Required (401)' : 'Dispatch Error'}
                    </p>
                    <p className="text-[11px] text-rose-300/80 mt-0.5">
                      {submitError.includes('401')
                        ? 'Cluster Zero-Trust security requires a Bearer JWT to dispatch tasks and execute autonomous agent actions.'
                        : submitError}
                    </p>
                  </div>
                </div>
                {submitError.includes('401') && (
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={openConnectModal}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 text-xs font-medium border border-rose-500/40 transition-colors"
                    >
                      <Key className="w-3.5 h-3.5 text-rose-300" />
                      <span>Authenticate / Set Token</span>
                    </button>
                  </div>
                )}
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
                  <span>Dispatching...</span>
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" />
                  <span>Execute Task on Cluster</span>
                </>
              )}
            </button>
          </form>
        </div>

        {/* Task Result / Recent Execution Banner */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center space-x-2 border-b border-gray-800 pb-3 mb-4">
              <Clock className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-white">Latest Dispatched Task</h3>
            </div>

            {createdTask ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">Task ID:</span>
                  <span className="text-xs font-mono font-semibold text-cyan-400">
                    {createdTask.task_id}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">Status:</span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-cyan-950/80 px-2 py-0.5 text-xs font-medium text-cyan-400 border border-cyan-800">
                    {createdTask.status}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">Tenant:</span>
                  <span className="text-xs font-mono text-gray-300">{createdTask.tenant_id}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">Dispatched At:</span>
                  <span className="text-xs font-mono text-gray-400">
                    {new Date(createdTask.created_at).toLocaleTimeString()}
                  </span>
                </div>

                <div className="mt-4 rounded-lg bg-gray-950 p-3 text-xs font-mono text-gray-300 max-h-40 overflow-y-auto">
                  <pre>{JSON.stringify(createdTask, null, 2)}</pre>
                </div>
              </div>
            ) : (
              <div className="h-48 flex flex-col items-center justify-center text-center p-6 text-gray-500">
                <Send className="w-8 h-8 mb-2 opacity-30" />
                <p className="text-xs">No task dispatched in this session yet.</p>
                <p className="text-[11px] text-gray-600 mt-1">
                  Fill out the form on the left to trigger a real autonomous agent task.
                </p>
              </div>
            )}
          </div>

          {createdTask && (
            <button
              onClick={() => onNavigateToTask(createdTask.task_id)}
              className="mt-4 flex items-center justify-center space-x-2 rounded-lg border border-cyan-500/40 bg-cyan-950/30 px-3 py-2 text-xs font-medium text-cyan-400 hover:bg-cyan-950/60 transition-colors"
            >
              <span>Inspect in Execution Console</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
