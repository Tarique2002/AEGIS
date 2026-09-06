/**
 * AEGIS Core TypeScript Domain Models
 * Strictly aligned with AEGIS Production OpenAPI Specs
 */

export interface SystemLiveInfo {
  status: string;
  app_name?: string;
  version?: string;
  timestamp?: string;
}

export interface SystemHealth {
  status: string;
  dependencies?: {
    database?: string | boolean;
    redis?: string | boolean;
    qdrant?: string | boolean;
    [key: string]: unknown;
  };
  timestamp?: string;
}

export interface TaskCreateRequest {
  objective: string;
  user_id?: string;
  metadata?: Record<string, unknown>;
  task_type?: string;
  input_data?: Record<string, unknown>;
  tenant_id?: string;
  description?: string;
}

export interface TaskResponse {
  task_id: string;
  run_id?: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | string;
  objective?: string;
  task_type?: string;
  created_at: string;
  updated_at?: string;
  completed_at?: string | null;
  tenant_id?: string;
  result?: Record<string, unknown> | string | null;
  error?: string | null;
  description?: string;
}

export interface TaskEvent {
  event_id: string;
  task_id: string;
  sequence_number: number;
  event_type: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface TaskEventsResponse {
  task_id: string;
  events: TaskEvent[];
  count: number;
}

export interface OrchestrationCreateRequest {
  goal: string;
  tenant_id?: string;
  max_workers?: number;
}

export interface WorkerState {
  worker_id: string;
  orchestration_id: string;
  role: string;
  status: 'IDLE' | 'ASSIGNED' | 'EXECUTING' | 'COMPLETED' | 'FAILED' | string;
  current_step?: string;
  assigned_task_id?: string;
  metrics?: Record<string, unknown>;
}

export interface OrchestrationResponse {
  orchestration_id: string;
  goal: string;
  status: 'PLANNING' | 'EXECUTING' | 'COMPLETED' | 'FAILED' | string;
  tenant_id: string;
  created_at: string;
  updated_at?: string;
  plan?: {
    steps?: Array<{
      step_id: string;
      role: string;
      description: string;
      dependencies: string[];
      status?: string;
    }>;
    [key: string]: unknown;
  };
}

export interface OrchestrationWorkersResponse {
  orchestration_id: string;
  workers: WorkerState[];
}

export interface OrchestrationResultsResponse {
  orchestration_id: string;
  status: string;
  final_output?: Record<string, unknown>;
  worker_results?: Record<string, unknown>;
}

export interface MemorySearchRequest {
  query_text: string;
  memory_type?: string | null;
  limit?: number;
  score_threshold?: number;
}

export interface MemoryRecord {
  record_id: string;
  memory_type: 'episodic' | 'semantic' | 'procedural' | string;
  content: string;
  score: number;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface MemorySearchResponse {
  query: string;
  matches: MemoryRecord[];
  count: number;
}

export interface LearningStatsResponse {
  total_trajectories: number;
  successful_trajectories: number;
  failed_trajectories: number;
  total_procedures: number;
  promoted_procedures: number;
  candidate_procedures?: number;
  governance_state?: Record<string, unknown>;
}

export type ProcedureStatus =
  | 'candidate'
  | 'pending'
  | 'validated'
  | 'promoted'
  | 'rejected'
  | 'disabled';

export interface LearnedProcedure {
  procedure_id: string;
  tenant_id: string;
  status: ProcedureStatus;
  confidence: number;
  validation_score: number;
  version: number;
  parent_procedure_id?: string | null;
  source_trajectory_ids: string[];
  source_evaluation_ids: string[];
  success_count: number;
  failure_count: number;
  created_at: string;
  promoted_at?: string | null;
  last_used_at?: string | null;
  content?: Record<string, unknown>;
}

export interface ProceduresListResponse {
  procedures: LearnedProcedure[];
  total: number;
}

export interface ProcedureValidateRequest {
  procedure_id: string;
  target_score_threshold?: number;
}

export interface ProcedureValidateResponse {
  procedure_id: string;
  validation_passed: boolean;
  validation_score: number;
  details?: Record<string, unknown>;
}

export interface DriftReportResponse {
  drift_detected: boolean;
  drift_score: number;
  metrics: Record<string, unknown>;
  checked_at: string;
  alert_level?: 'INFO' | 'WARNING' | 'CRITICAL';
}

export interface PolicySimulationRequest {
  action: string;
  resource: string;
  principal?: Record<string, unknown>;
  context?: Record<string, unknown>;
}

export interface PolicySimulationResponse {
  allowed: boolean;
  matched_policies: string[];
  reason?: string;
  eval_duration_ms?: number;
  details?: Record<string, unknown>;
}

export interface AuditCheckpoint {
  checkpoint_id: string;
  root_hash: string;
  record_count: number;
  created_at: string;
  verified?: boolean;
}

export interface AuditVerifyResponse {
  checkpoint_id: string;
  verified: boolean;
  expected_hash?: string;
  computed_hash?: string;
  matched?: boolean;
  tampered_indices?: number[];
  details?: Record<string, unknown>;
}

export interface ApiErrorDetail {
  detail?: string | Array<{ loc: string[]; msg: string; type: string }>;
  message?: string;
  status_code?: number;
}

export interface TokenIssueRequest {
  user_id?: string;
  email?: string;
  roles?: string[];
  scopes?: string[];
  expires_in_seconds?: number;
}

export interface TokenIssueResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  email?: string;
  roles: string[];
  scopes: string[];
}
