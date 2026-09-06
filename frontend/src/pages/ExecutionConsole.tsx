import React, { useState, useEffect, useRef, useCallback } from 'react';
import { getTask, getTaskEvents } from '../api/client';
import type { TaskResponse, TaskEvent } from '../types/aegis';
import {
  Terminal,
  Play,
  Pause,
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Search,
  ChevronRight,
  Filter,
} from 'lucide-react';

interface ExecutionConsoleProps {
  initialTaskId?: string | null;
}

export const ExecutionConsole: React.FC<ExecutionConsoleProps> = ({ initialTaskId }) => {
  const [taskId, setTaskId] = useState<string>(initialTaskId || '');
  const [task, setTask] = useState<TaskResponse | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [autoPoll, setAutoPoll] = useState<boolean>(false);
  const [eventFilter, setEventFilter] = useState<string>('all');
  const [selectedEvent, setSelectedEvent] = useState<TaskEvent | null>(null);

  const timerRef = useRef<number | null>(null);

  const fetchTaskAndEvents = useCallback(async (quiet = false) => {
    if (!taskId.trim()) return;
    if (!quiet) setLoading(true);
    setError(null);

    try {
      const [tRes, eRes] = await Promise.all([
        getTask(taskId.trim()),
        getTaskEvents(taskId.trim()),
      ]);
      setTask(tRes);
      // Sort events strictly by sequence_number
      const sortedEvents = (eRes.events || []).sort(
        (a, b) => a.sequence_number - b.sequence_number
      );
      setEvents(sortedEvents);
      if (sortedEvents.length > 0 && !selectedEvent) {
        setSelectedEvent(sortedEvents[sortedEvents.length - 1]);
      }
    } catch (err: unknown) {
      const e = err as Error;
      setError(e.message || 'Failed to fetch task execution details');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [taskId, selectedEvent]);

  // Load when initialTaskId changes
  useEffect(() => {
    if (initialTaskId) {
      setTaskId(initialTaskId);
    }
  }, [initialTaskId]);

  useEffect(() => {
    if (taskId.trim()) {
      fetchTaskAndEvents();
    }
  }, [taskId, fetchTaskAndEvents]);

  // Auto-poll loop
  useEffect(() => {
    if (autoPoll && taskId.trim()) {
      timerRef.current = window.setInterval(() => {
        fetchTaskAndEvents(true);
      }, 2500);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [autoPoll, taskId, fetchTaskAndEvents]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchTaskAndEvents();
  };

  const filteredEvents = events.filter((ev) => {
    if (eventFilter === 'all') return true;
    return ev.event_type.toLowerCase().includes(eventFilter.toLowerCase());
  });

  const getStatusBadge = (status?: string) => {
    switch (status?.toUpperCase()) {
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950/80 px-2.5 py-0.5 text-xs font-semibold text-emerald-400 border border-emerald-800">
            <CheckCircle2 className="w-3.5 h-3.5" /> COMPLETED
          </span>
        );
      case 'RUNNING':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-cyan-950/80 px-2.5 py-0.5 text-xs font-semibold text-cyan-400 border border-cyan-800 animate-pulse">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" /> RUNNING
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-950/80 px-2.5 py-0.5 text-xs font-semibold text-rose-400 border border-rose-800">
            <XCircle className="w-3.5 h-3.5" /> FAILED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-gray-800 px-2.5 py-0.5 text-xs font-semibold text-gray-300 border border-gray-700">
            <Clock className="w-3.5 h-3.5" /> {status || 'PENDING'}
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
            <Terminal className="w-6 h-6 text-cyan-400" />
            Execution Console & Monotonic Event Timeline
          </h1>
          <p className="text-xs text-gray-400 mt-1">
            Real-time inspection of task life cycle, state transitions, and append-only ordered event logs.
          </p>
        </div>

        {/* Polling & Search Controls */}
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setAutoPoll(!autoPoll)}
            className={`flex items-center space-x-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
              autoPoll
                ? 'border-cyan-500 bg-cyan-950/40 text-cyan-300'
                : 'border-gray-700 bg-gray-800/80 text-gray-300 hover:text-white'
            }`}
          >
            {autoPoll ? (
              <>
                <Pause className="w-3.5 h-3.5" />
                <span>Live Polling (2.5s)</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                <span>Start Polling</span>
              </>
            )}
          </button>

          <button
            onClick={() => fetchTaskAndEvents()}
            disabled={loading}
            className="flex items-center space-x-1.5 rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-1.5 text-xs font-medium text-gray-200 hover:border-cyan-500 hover:text-cyan-400 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Task Lookup Bar */}
      <form onSubmit={handleSearch} className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-2.5 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={taskId}
            onChange={(e) => setTaskId(e.target.value)}
            placeholder="Enter Task ID (e.g., task-7b94998d-d790-4107-88eb-...)"
            className="w-full rounded-xl border border-gray-800 bg-gray-900/90 pl-10 pr-4 py-2 text-xs font-mono text-gray-100 placeholder-gray-500 focus:border-cyan-500 focus:outline-none"
          />
        </div>
        <button
          type="submit"
          className="rounded-xl bg-cyan-600 hover:bg-cyan-500 px-5 py-2 text-xs font-medium text-white transition-colors flex items-center gap-1.5"
        >
          <Search className="w-3.5 h-3.5" />
          <span>Inspect Task</span>
        </button>
      </form>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-4 text-xs text-rose-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Task Overview Card */}
      {task && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-800 pb-3">
            <div className="space-y-1">
              <div className="flex items-center gap-3">
                <span className="text-base font-bold text-white font-mono">{task.task_id}</span>
                {getStatusBadge(task.status)}
              </div>
              <p className="text-xs text-gray-400">
                Type: <span className="font-mono text-cyan-400">{task.task_type}</span> • Tenant:{' '}
                <span className="font-mono text-gray-300">{task.tenant_id}</span>
              </p>
            </div>
            <div className="text-right text-xs font-mono text-gray-500">
              <div>Created: {new Date(task.created_at).toLocaleString()}</div>
              {task.updated_at && (
                <div>Updated: {new Date(task.updated_at).toLocaleString()}</div>
              )}
            </div>
          </div>

          {task.error && (
            <div className="rounded-lg border border-rose-500/30 bg-rose-950/40 p-3 text-xs text-rose-300 font-mono">
              <span className="font-bold text-rose-400">Execution Error: </span>
              {task.error}
            </div>
          )}

          {task.result && (
            <div>
              <span className="text-xs font-semibold text-gray-400">Execution Output / Payload:</span>
              <pre className="mt-1.5 rounded-lg bg-gray-950 border border-gray-800/80 p-3 text-xs font-mono text-cyan-300 max-h-48 overflow-y-auto">
                {JSON.stringify(task.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Events Timeline & Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Timeline Column */}
        <div className="lg:col-span-7 rounded-xl border border-gray-800 bg-gray-900/30 p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-gray-800 pb-3">
            <div className="flex items-center space-x-2">
              <Clock className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-white">
                Monotonic Events Stream ({filteredEvents.length})
              </h3>
            </div>

            {/* Filter */}
            <div className="flex items-center space-x-2">
              <Filter className="w-3.5 h-3.5 text-gray-400" />
              <select
                value={eventFilter}
                onChange={(e) => setEventFilter(e.target.value)}
                className="rounded-lg border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-gray-300 focus:border-cyan-500 focus:outline-none font-mono"
              >
                <option value="all">All Events</option>
                <option value="state_change">State Changes</option>
                <option value="tool">Tool Calls</option>
                <option value="error">Errors</option>
              </select>
            </div>
          </div>

          {filteredEvents.length === 0 ? (
            <div className="py-12 text-center text-gray-500 text-xs font-mono">
              {taskId ? 'No matching events recorded for this task.' : 'Enter a Task ID above to inspect events.'}
            </div>
          ) : (
            <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
              {filteredEvents.map((ev) => {
                const isSelected = selectedEvent?.event_id === ev.event_id;
                return (
                  <button
                    key={ev.event_id || `${ev.task_id}-${ev.sequence_number}`}
                    onClick={() => setSelectedEvent(ev)}
                    className={`w-full text-left p-3 rounded-lg border transition-all flex items-center justify-between ${
                      isSelected
                        ? 'border-cyan-500/50 bg-cyan-950/20 text-white'
                        : 'border-gray-800/80 bg-gray-950/50 text-gray-400 hover:border-gray-700 hover:text-gray-200'
                    }`}
                  >
                    <div className="flex items-center space-x-3">
                      <span className="font-mono text-xs px-2 py-0.5 rounded bg-gray-900 border border-gray-800 text-cyan-400 font-semibold">
                        #{ev.sequence_number}
                      </span>
                      <div>
                        <div className="text-xs font-medium font-mono text-white">
                          {ev.event_type}
                        </div>
                        <div className="text-[11px] text-gray-500 font-mono mt-0.5">
                          {new Date(ev.timestamp).toLocaleTimeString()}
                        </div>
                      </div>
                    </div>
                    <ChevronRight
                      className={`w-4 h-4 ${isSelected ? 'text-cyan-400' : 'text-gray-600'}`}
                    />
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected Event Details Inspector */}
        <div className="lg:col-span-5 rounded-xl border border-gray-800 bg-gray-900/30 p-5 space-y-4">
          <div className="flex items-center space-x-2 border-b border-gray-800 pb-3">
            <Terminal className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">Event Payload Inspector</h3>
          </div>

          {selectedEvent ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                <div className="p-2 rounded bg-gray-950 border border-gray-800">
                  <span className="text-gray-500 block text-[10px]">SEQUENCE:</span>
                  <span className="text-cyan-400 font-bold">#{selectedEvent.sequence_number}</span>
                </div>
                <div className="p-2 rounded bg-gray-950 border border-gray-800">
                  <span className="text-gray-500 block text-[10px]">EVENT TYPE:</span>
                  <span className="text-emerald-400 font-bold">{selectedEvent.event_type}</span>
                </div>
              </div>

              <div className="p-2 rounded bg-gray-950 border border-gray-800 text-xs font-mono">
                <span className="text-gray-500 block text-[10px]">TIMESTAMP:</span>
                <span className="text-gray-300">{new Date(selectedEvent.timestamp).toISOString()}</span>
              </div>

              <div>
                <span className="text-xs font-medium text-gray-400">Payload Object:</span>
                <pre className="mt-1.5 rounded-lg bg-gray-950 border border-gray-800 p-3 text-xs font-mono text-gray-200 max-h-[340px] overflow-y-auto">
                  {JSON.stringify(selectedEvent.payload, null, 2)}
                </pre>
              </div>
            </div>
          ) : (
            <div className="py-16 text-center text-gray-500 text-xs">
              Select an event from the timeline to inspect its full payload.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
