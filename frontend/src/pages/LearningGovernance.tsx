import React, { useState, useEffect, useCallback } from 'react';
import {
  getProcedures,
  validateProcedure,
  requestProcedurePromotion,
  approveProcedurePromotion,
  promoteProcedure,
  disableProcedure,
  rollbackProcedure,
  getDriftReport,
} from '../api/client';
import type {
  LearnedProcedure,
  ProcedureStatus,
  DriftReportResponse,
  ProcedureValidateResponse,
} from '../types/aegis';
import {
  GraduationCap,
  ShieldCheck,
  RotateCcw,
  Activity,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  AlertCircle,
  RefreshCw,
  Sliders,
  Award,
  Ban,
  Clock,
  Send,
  Layers,
  FileCheck,
} from 'lucide-react';

export const LearningGovernance: React.FC = () => {
  const [procedures, setProcedures] = useState<LearnedProcedure[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [tenantFilter, setTenantFilter] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Selected procedure for inspection/action
  const [selectedProc, setSelectedProc] = useState<LearnedProcedure | null>(null);

  // Live drift state
  const [driftReport, setDriftReport] = useState<DriftReportResponse | null>(null);
  const [driftLoading, setDriftLoading] = useState<boolean>(false);

  // Action modals / state
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [actionFeedback, setActionFeedback] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  // Validation modal/state
  const [validationResult, setValidationResult] =
    useState<ProcedureValidateResponse | null>(null);
  const [valThreshold, setValThreshold] = useState<number>(0.85);

  // Human Approval modal state
  const [isApproveOpen, setIsApproveOpen] = useState<boolean>(false);
  const [approverId, setApproverId] = useState<string>('lead-governance-officer');
  const [approvalNotes, setApprovalNotes] = useState<string>(
    'Verified zero safety regressions across synthetic golden evaluation dataset.'
  );

  // Rollback modal state
  const [isRollbackOpen, setIsRollbackOpen] = useState<boolean>(false);
  const [rollbackVersion, setRollbackVersion] = useState<number>(1);
  const [rollbackReason, setRollbackReason] = useState<string>(
    'Automated rollback triggered due to policy divergence in candidate variant.'
  );

  const fetchProceduresList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getProcedures(
        tenantFilter.trim() || undefined,
        selectedStatus === 'all' ? undefined : selectedStatus
      );
      setProcedures(res.procedures || []);
      setTotal(res.total ?? res.procedures?.length ?? 0);
      if (res.procedures?.length > 0 && !selectedProc) {
        setSelectedProc(res.procedures[0]);
      }
    } catch (err: unknown) {
      const e = err as Error;
      setError(e.message || 'Failed to fetch governed procedures catalog');
    } finally {
      setLoading(false);
    }
  }, [tenantFilter, selectedStatus, selectedProc]);

  const fetchDrift = async () => {
    setDriftLoading(true);
    try {
      const report = await getDriftReport();
      setDriftReport(report);
    } catch {
      // Drift report is optional if no baseline established
    } finally {
      setDriftLoading(false);
    }
  };

  useEffect(() => {
    fetchProceduresList();
    fetchDrift();
  }, [fetchProceduresList]);

  // Action handlers
  const handleValidate = async () => {
    if (!selectedProc) return;
    setActionLoading(true);
    setActionFeedback(null);
    try {
      const res = await validateProcedure(selectedProc.procedure_id, valThreshold);
      setValidationResult(res);
      setActionFeedback({
        type: res.validation_passed ? 'success' : 'error',
        message: `Evaluation Gate complete: ${
          res.validation_passed ? 'PASSED' : 'FAILED'
        } with score ${(res.validation_score * 100).toFixed(1)}%`,
      });
      await fetchProceduresList();
    } catch (err: unknown) {
      const e = err as Error;
      setActionFeedback({ type: 'error', message: e.message || 'Validation request failed' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleRequestPromotion = async () => {
    if (!selectedProc) return;
    setActionLoading(true);
    setActionFeedback(null);
    try {
      await requestProcedurePromotion(
        selectedProc.procedure_id,
        'Passed synthetic simulation test bench'
      );
      setActionFeedback({
        type: 'success',
        message: 'Promotion request registered in governance queue',
      });
      await fetchProceduresList();
    } catch (err: unknown) {
      const e = err as Error;
      setActionFeedback({ type: 'error', message: e.message || 'Promotion request failed' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprove = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProc) return;
    setActionLoading(true);
    setActionFeedback(null);
    try {
      await approveProcedurePromotion(
        selectedProc.procedure_id,
        approverId,
        approvalNotes
      );
      setIsApproveOpen(false);
      setActionFeedback({
        type: 'success',
        message: `Procedure approved by ${approverId}`,
      });
      await fetchProceduresList();
    } catch (err: unknown) {
      const e = err as Error;
      setActionFeedback({ type: 'error', message: e.message || 'Approval failed' });
    } finally {
      setActionLoading(false);
    }
  };

  const handlePromote = async () => {
    if (!selectedProc) return;
    setActionLoading(true);
    setActionFeedback(null);
    try {
      await promoteProcedure(selectedProc.procedure_id);
      setActionFeedback({
        type: 'success',
        message: 'Procedure successfully promoted to production runtime',
      });
      await fetchProceduresList();
    } catch (err: unknown) {
      const e = err as Error;
      setActionFeedback({ type: 'error', message: e.message || 'Promotion execution failed' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDisable = async () => {
    if (!selectedProc) return;
    setActionLoading(true);
    setActionFeedback(null);
    try {
      await disableProcedure(
        selectedProc.procedure_id,
        'Manually quarantined via AEGIS Governance Console'
      );
      setActionFeedback({
        type: 'success',
        message: 'Procedure disabled and quarantined from execution selection',
      });
      await fetchProceduresList();
    } catch (err: unknown) {
      const e = err as Error;
      setActionFeedback({ type: 'error', message: e.message || 'Disable request failed' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleRollback = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProc) return;
    setActionLoading(true);
    setActionFeedback(null);
    try {
      await rollbackProcedure(
        selectedProc.procedure_id,
        rollbackVersion,
        rollbackReason
      );
      setIsRollbackOpen(false);
      setActionFeedback({
        type: 'success',
        message: `Procedure rolled back to v${rollbackVersion}`,
      });
      await fetchProceduresList();
    } catch (err: unknown) {
      const e = err as Error;
      setActionFeedback({ type: 'error', message: e.message || 'Rollback failed' });
    } finally {
      setActionLoading(false);
    }
  };

  const getStatusChip = (status: ProcedureStatus) => {
    switch (status) {
      case 'promoted':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950 px-2.5 py-0.5 text-xs font-semibold text-emerald-400 border border-emerald-800">
            <CheckCircle2 className="w-3 h-3" /> Promoted
          </span>
        );
      case 'validated':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-cyan-950 px-2.5 py-0.5 text-xs font-semibold text-cyan-400 border border-cyan-800">
            <FileCheck className="w-3 h-3" /> Validated
          </span>
        );
      case 'pending':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-950 px-2.5 py-0.5 text-xs font-semibold text-amber-400 border border-amber-800">
            <Clock className="w-3 h-3" /> Pending Review
          </span>
        );
      case 'candidate':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-950 px-2.5 py-0.5 text-xs font-semibold text-blue-400 border border-blue-800">
            <Layers className="w-3 h-3" /> Candidate
          </span>
        );
      case 'disabled':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-950 px-2.5 py-0.5 text-xs font-semibold text-rose-400 border border-rose-800">
            <Ban className="w-3 h-3" /> Disabled
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-gray-800 px-2.5 py-0.5 text-xs font-semibold text-gray-400 border border-gray-700">
            <XCircle className="w-3 h-3" /> Rejected
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-gray-800 px-2 py-0.5 text-xs font-semibold text-gray-300">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-gray-800 pb-5">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <GraduationCap className="w-6 h-6 text-cyan-400" />
              Learning Governance & Safe Evolution
            </h1>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-cyan-950 text-cyan-400 border border-cyan-700">
              Phase 12 Core
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Procedure lifecycle gates, synthetic evaluation benchmarks, human review gates, continuous drift detection, and automated rollback controls.
          </p>
        </div>

        <button
          onClick={() => {
            fetchProceduresList();
            fetchDrift();
          }}
          disabled={loading}
          className="flex items-center space-x-1.5 rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-1.5 text-xs font-medium text-gray-200 hover:border-cyan-500 hover:text-cyan-400 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Catalog</span>
        </button>
      </div>

      {/* Governed Lifecycle Progression Pipeline */}
      <div className="rounded-xl border border-gray-800 bg-gray-950/70 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-gray-300 flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-cyan-400" />
            Mandated Safe Evolution Lifecycle Pipeline
          </span>
          <span className="text-[11px] font-medium text-amber-400 border border-amber-800/80 bg-amber-950/40 px-2 py-0.5 rounded">
            Human-in-the-Loop Enforced
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2 text-center text-xs font-mono">
          <div className="p-2 rounded bg-gray-900 border border-gray-800">
            <span className="text-[10px] text-gray-500 block">STEP 1</span>
            <span className="text-blue-400 font-medium">Candidate</span>
          </div>
          <div className="p-2 rounded bg-gray-900 border border-gray-800">
            <span className="text-[10px] text-gray-500 block">STEP 2</span>
            <span className="text-cyan-400 font-medium">Validation Gate</span>
          </div>
          <div className="p-2 rounded bg-gray-900 border border-gray-800">
            <span className="text-[10px] text-gray-500 block">STEP 3</span>
            <span className="text-amber-400 font-medium">Promotion Req</span>
          </div>
          <div className="p-2 rounded bg-gray-900 border border-cyan-800/80 bg-cyan-950/20">
            <span className="text-[10px] text-cyan-400 block font-bold">STEP 4 (GATE)</span>
            <span className="text-white font-bold">Human Sign-off</span>
          </div>
          <div className="p-2 rounded bg-gray-900 border border-gray-800">
            <span className="text-[10px] text-gray-500 block">STEP 5</span>
            <span className="text-emerald-400 font-medium">Promoted</span>
          </div>
          <div className="p-2 rounded bg-gray-900 border border-gray-800">
            <span className="text-[10px] text-gray-500 block">STEP 6</span>
            <span className="text-purple-400 font-medium">Active Runtime</span>
          </div>
          <div className="p-2 rounded bg-gray-900 border border-gray-800">
            <span className="text-[10px] text-gray-500 block">STEP 7</span>
            <span className="text-amber-400 font-medium">Drift Monitor</span>
          </div>
          <div className="p-2 rounded bg-gray-900 border border-gray-800">
            <span className="text-[10px] text-gray-500 block">STEP 8</span>
            <span className="text-rose-400 font-medium">Safe Rollback</span>
          </div>
        </div>

        <p className="text-[11px] text-gray-400 pt-1">
          <span className="text-gray-300 font-semibold">Governance Invariant:</span> Autonomous agents never promote themselves. All candidate strategies require rigorous benchmark scoring and cryptographically attested human operator approval before execution traffic exposure.
        </p>
      </div>

      {/* Action Notification Banner */}
      {actionFeedback && (
        <div
          className={`rounded-xl p-3.5 text-xs flex items-center gap-2 border ${
            actionFeedback.type === 'success'
              ? 'border-emerald-500/30 bg-emerald-950/20 text-emerald-300'
              : 'border-rose-500/30 bg-rose-950/20 text-rose-300'
          }`}
        >
          {actionFeedback.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
          ) : (
            <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
          )}
          <span>{actionFeedback.message}</span>
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-4 text-xs text-rose-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Live Drift Monitor Card */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-5 space-y-3">
        <div className="flex items-center justify-between border-b border-gray-800 pb-3">
          <div className="flex items-center space-x-2">
            <Activity className="w-4 h-4 text-cyan-400" />
            <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-300">
              Continuous Drift Detection & Model Divergence (/api/v1/learning/governance/drift)
            </h2>
          </div>
          <button
            onClick={fetchDrift}
            disabled={driftLoading}
            className="text-xs text-gray-400 hover:text-white flex items-center gap-1"
          >
            <RefreshCw className={`w-3 h-3 ${driftLoading ? 'animate-spin' : ''}`} />
            Check Drift
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-1">
          <div className="p-3 rounded-lg bg-gray-950 border border-gray-800/80">
            <span className="text-[11px] text-gray-400">Drift Status:</span>
            <div className="mt-1 flex items-center gap-2">
              {driftReport?.drift_detected ? (
                <span className="text-xs font-semibold text-rose-400 flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5" /> Drift Detected
                </span>
              ) : (
                <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Stable Baseline
                </span>
              )}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-gray-950 border border-gray-800/80">
            <span className="text-[11px] text-gray-400">Divergence Score:</span>
            <div className="mt-1 text-sm font-bold font-mono text-cyan-400">
              {driftReport ? driftReport.drift_score.toFixed(4) : '0.0000'}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-gray-950 border border-gray-800/80">
            <span className="text-[11px] text-gray-400">Alert Classification:</span>
            <div className="mt-1 text-xs font-bold font-mono text-gray-200">
              {driftReport?.alert_level || 'NOMINAL'}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-gray-950 border border-gray-800/80">
            <span className="text-[11px] text-gray-400">Last Monitored:</span>
            <div className="mt-1 text-[11px] font-mono text-gray-400">
              {driftReport?.checked_at
                ? new Date(driftReport.checked_at).toLocaleTimeString()
                : 'Active Monitor'}
            </div>
          </div>
        </div>
      </div>

      {/* Main Governance Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Procedures Catalog Column */}
        <div className="lg:col-span-5 rounded-xl border border-gray-800 bg-gray-900/30 p-5 space-y-4">
          <div className="flex flex-col gap-3 border-b border-gray-800 pb-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">
                Learned Procedures ({total})
              </h3>
            </div>

            {/* Filter Bar */}
            <div className="flex items-center gap-2">
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="flex-1 rounded-lg border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-gray-300 focus:border-cyan-500 focus:outline-none font-mono"
              >
                <option value="all">All Statuses</option>
                <option value="candidate">Candidate</option>
                <option value="pending">Pending</option>
                <option value="validated">Validated</option>
                <option value="promoted">Promoted</option>
                <option value="disabled">Disabled</option>
              </select>

              <input
                type="text"
                placeholder="Filter tenant..."
                value={tenantFilter}
                onChange={(e) => setTenantFilter(e.target.value)}
                className="w-28 rounded-lg border border-gray-700 bg-gray-950 px-2 py-1 text-xs text-gray-300 placeholder-gray-600 focus:border-cyan-500 focus:outline-none font-mono"
              />
            </div>
          </div>

          {procedures.length === 0 ? (
            <div className="py-16 text-center text-gray-500 text-xs font-mono">
              No procedures found in the database.
            </div>
          ) : (
            <div className="space-y-2 max-h-[560px] overflow-y-auto pr-1">
              {procedures.map((proc) => {
                const isSelected = selectedProc?.procedure_id === proc.procedure_id;
                return (
                  <button
                    key={proc.procedure_id}
                    onClick={() => setSelectedProc(proc)}
                    className={`w-full text-left p-3 rounded-lg border transition-all space-y-2 ${
                      isSelected
                        ? 'border-cyan-500/50 bg-cyan-950/20'
                        : 'border-gray-800/80 bg-gray-950/40 hover:border-gray-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <span className="font-mono text-xs font-bold text-white">
                          {proc.procedure_id}
                        </span>
                        <span className="px-1.5 py-0.2 rounded bg-gray-800 text-[10px] font-mono text-cyan-400">
                          v{proc.version}
                        </span>
                      </div>
                      {getStatusChip(proc.status)}
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-gray-400 font-mono">
                      <span>Val: {(proc.validation_score * 100).toFixed(0)}%</span>
                      <span className="text-gray-500">|</span>
                      <span>Conf: {(proc.confidence * 100).toFixed(0)}%</span>
                      <span className="text-gray-500">|</span>
                      <span className="text-emerald-400">+{proc.success_count}</span>
                      <span className="text-rose-400">-{proc.failure_count}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected Procedure Lifecycle & Gate Controls Column */}
        <div className="lg:col-span-7 rounded-xl border border-gray-800 bg-gray-900/30 p-5 space-y-5">
          <div className="flex items-center justify-between border-b border-gray-800 pb-3">
            <div className="flex items-center space-x-2">
              <ShieldCheck className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-white">
                Procedure Inspector & Governance Gates
              </h3>
            </div>
            {selectedProc && getStatusChip(selectedProc.status)}
          </div>

          {selectedProc ? (
            <div className="space-y-4">
              {/* Metadata Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
                <div className="p-3 rounded-lg bg-gray-950 border border-gray-800">
                  <span className="text-gray-500 block text-[10px]">PROCEDURE ID</span>
                  <span className="text-cyan-400 font-bold truncate block">
                    {selectedProc.procedure_id}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-gray-950 border border-gray-800">
                  <span className="text-gray-500 block text-[10px]">VERSION</span>
                  <span className="text-white font-bold">v{selectedProc.version}</span>
                </div>
                <div className="p-3 rounded-lg bg-gray-950 border border-gray-800">
                  <span className="text-gray-500 block text-[10px]">VALIDATION SCORE</span>
                  <span className="text-emerald-400 font-bold">
                    {(selectedProc.validation_score * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-gray-950 border border-gray-800">
                  <span className="text-gray-500 block text-[10px]">CONFIDENCE</span>
                  <span className="text-purple-400 font-bold">
                    {(selectedProc.confidence * 100).toFixed(1)}%
                  </span>
                </div>
              </div>

              {/* Lineage & Provenance */}
              <div className="rounded-lg bg-gray-950 border border-gray-800 p-3 space-y-2 text-xs">
                <span className="text-xs font-semibold text-gray-300">
                  Provenance & Lineage Tracking:
                </span>
                <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-gray-400">
                  <div>
                    <span className="text-gray-500">Parent Version: </span>
                    {selectedProc.parent_procedure_id || 'Root v1 (Original)'}
                  </div>
                  <div>
                    <span className="text-gray-500">Tenant ID: </span>
                    {selectedProc.tenant_id}
                  </div>
                  <div>
                    <span className="text-gray-500">Source Trajectories: </span>
                    {selectedProc.source_trajectory_ids?.length || 0} runs
                  </div>
                  <div>
                    <span className="text-gray-500">Created: </span>
                    {new Date(selectedProc.created_at).toLocaleString()}
                  </div>
                </div>
              </div>

              {/* Validation Gate Section */}
              <div className="rounded-lg border border-gray-800 bg-gray-950/70 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-200 flex items-center gap-1.5">
                    <Sliders className="w-3.5 h-3.5 text-cyan-400" />
                    Automated Validation Gate Threshold:
                  </span>
                  <span className="text-xs font-mono text-cyan-400 font-bold">
                    {(valThreshold * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={0.5}
                    max={1.0}
                    step={0.05}
                    value={valThreshold}
                    onChange={(e) => setValThreshold(Number(e.target.value))}
                    className="flex-1 accent-cyan-500"
                  />
                  <button
                    onClick={handleValidate}
                    disabled={actionLoading}
                    className="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium transition-colors disabled:opacity-50 flex items-center gap-1.5"
                  >
                    {actionLoading ? (
                      <RefreshCw className="w-3 h-3 animate-spin" />
                    ) : (
                      <FileCheck className="w-3 h-3" />
                    )}
                    <span>Run Evaluation Gate</span>
                  </button>
                </div>

                {validationResult && (
                  <div className="mt-2 pt-2 border-t border-gray-800/80 flex items-center justify-between text-xs font-mono">
                    <span className="text-gray-400">Latest Validation Run:</span>
                    <span
                      className={`font-semibold ${
                        validationResult.validation_passed
                          ? 'text-emerald-400'
                          : 'text-rose-400'
                      }`}
                    >
                      {validationResult.validation_passed ? 'PASSED' : 'FAILED'} (Score: {(validationResult.validation_score * 100).toFixed(1)}%)
                    </span>
                  </div>
                )}
              </div>

              {/* Procedure Content / Strategy Body */}
              <div>
                <span className="text-xs font-semibold text-gray-400">
                  Procedure Strategy Definition / Action Graph:
                </span>
                <pre className="mt-1.5 rounded-lg bg-gray-950 border border-gray-800 p-3 text-xs font-mono text-gray-200 max-h-40 overflow-y-auto">
                  {JSON.stringify(selectedProc.content || {}, null, 2)}
                </pre>
              </div>

              {/* Action Buttons Row */}
              <div className="pt-2 border-t border-gray-800 flex flex-wrap gap-2">
                <button
                  onClick={handleRequestPromotion}
                  disabled={actionLoading}
                  className="px-3 py-1.5 rounded-lg border border-amber-500/40 bg-amber-950/20 hover:bg-amber-950/40 text-amber-300 text-xs font-medium transition-colors flex items-center gap-1.5"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>Request Promotion</span>
                </button>

                <button
                  onClick={() => setIsApproveOpen(true)}
                  disabled={actionLoading}
                  className="px-3 py-1.5 rounded-lg border border-cyan-500/40 bg-cyan-950/20 hover:bg-cyan-950/40 text-cyan-300 text-xs font-medium transition-colors flex items-center gap-1.5"
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>Human Approval Gate</span>
                </button>

                <button
                  onClick={handlePromote}
                  disabled={actionLoading}
                  className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition-colors flex items-center gap-1.5 shadow-lg shadow-emerald-950/40"
                >
                  <Award className="w-3.5 h-3.5" />
                  <span>Promote to Production</span>
                </button>

                <button
                  onClick={() => setIsRollbackOpen(true)}
                  disabled={actionLoading}
                  className="px-3 py-1.5 rounded-lg border border-purple-500/40 bg-purple-950/20 hover:bg-purple-950/40 text-purple-300 text-xs font-medium transition-colors flex items-center gap-1.5"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Rollback Version</span>
                </button>

                <button
                  onClick={handleDisable}
                  disabled={actionLoading}
                  className="px-3 py-1.5 rounded-lg border border-rose-500/40 bg-rose-950/20 hover:bg-rose-950/40 text-rose-300 text-xs font-medium transition-colors flex items-center gap-1.5 ml-auto"
                >
                  <Ban className="w-3.5 h-3.5" />
                  <span>Quarantine / Disable</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="py-24 text-center text-gray-500 text-xs">
              Select a procedure from the catalog to inspect lifecycle history and trigger gates.
            </div>
          )}
        </div>
      </div>

      {/* Human Approval Modal */}
      {isApproveOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-xl border border-gray-800 bg-[#0f172a] p-6 space-y-4">
            <div className="flex items-center space-x-2 border-b border-gray-800 pb-3">
              <ShieldCheck className="w-5 h-5 text-cyan-400" />
              <h3 className="text-base font-semibold text-white">Human Approval Gate</h3>
            </div>

            <form onSubmit={handleApprove} className="space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-400">Approver ID</label>
                <input
                  type="text"
                  required
                  value={approverId}
                  onChange={(e) => setApproverId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-100 focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-gray-400">Review Notes / Audit Log</label>
                <textarea
                  rows={3}
                  required
                  value={approvalNotes}
                  onChange={(e) => setApprovalNotes(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-xs text-gray-100 focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div className="flex justify-end space-x-3 pt-3">
                <button
                  type="button"
                  onClick={() => setIsApproveOpen(false)}
                  className="px-4 py-2 text-xs text-gray-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-4 py-2 text-xs font-medium rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-colors"
                >
                  Sign & Approve Promotion
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Rollback Modal */}
      {isRollbackOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-xl border border-gray-800 bg-[#0f172a] p-6 space-y-4">
            <div className="flex items-center space-x-2 border-b border-gray-800 pb-3">
              <RotateCcw className="w-5 h-5 text-purple-400" />
              <h3 className="text-base font-semibold text-white">Rollback Procedure Version</h3>
            </div>

            <form onSubmit={handleRollback} className="space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-400">Target Rollback Version</label>
                <input
                  type="number"
                  min={1}
                  required
                  value={rollbackVersion}
                  onChange={(e) => setRollbackVersion(Number(e.target.value))}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-1.5 text-xs text-gray-100 font-mono focus:border-purple-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-gray-400">Justification / Reason</label>
                <textarea
                  rows={3}
                  required
                  value={rollbackReason}
                  onChange={(e) => setRollbackReason(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-xs text-gray-100 focus:border-purple-500 focus:outline-none"
                />
              </div>

              <div className="flex justify-end space-x-3 pt-3">
                <button
                  type="button"
                  onClick={() => setIsRollbackOpen(false)}
                  className="px-4 py-2 text-xs text-gray-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-4 py-2 text-xs font-medium rounded-lg bg-purple-600 hover:bg-purple-500 text-white transition-colors"
                >
                  Execute Rollback
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
