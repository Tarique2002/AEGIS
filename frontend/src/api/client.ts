import type {
  SystemHealth,
  SystemLiveInfo,
  TaskCreateRequest,
  TaskResponse,
  TaskEventsResponse,
  OrchestrationCreateRequest,
  OrchestrationResponse,
  OrchestrationWorkersResponse,
  OrchestrationResultsResponse,
  MemorySearchRequest,
  MemorySearchResponse,
  LearningStatsResponse,
  ProceduresListResponse,
  ProcedureValidateResponse,
  DriftReportResponse,
  PolicySimulationRequest,
  PolicySimulationResponse,
  AuditCheckpoint,
  AuditVerifyResponse,
  TokenIssueRequest,
  TokenIssueResponse,
} from '../types/aegis';

const DEFAULT_BASE_URL =
  (import.meta as unknown as { env?: { VITE_AEGIS_API_URL?: string } }).env?.VITE_AEGIS_API_URL ||
  'https://aegis-api-gzky.onrender.com';

export function getBaseUrl(): string {
  return localStorage.getItem('aegis_api_url') || DEFAULT_BASE_URL;
}

export function setBaseUrl(url: string): void {
  if (!url || !url.trim()) {
    localStorage.removeItem('aegis_api_url');
  } else {
    localStorage.setItem('aegis_api_url', url.trim().replace(/\/+$/, ''));
  }
}

export function getAuthToken(): string | null {
  return localStorage.getItem('aegis_bearer_token');
}

export function setAuthToken(token: string | null): void {
  if (!token || !token.trim()) {
    localStorage.removeItem('aegis_bearer_token');
  } else {
    localStorage.setItem('aegis_bearer_token', token.trim());
  }
}

export class AegisApiError extends Error {
  public statusCode: number;
  public details: unknown;

  constructor(statusCode: number, message: string, details?: unknown) {
    super(message);
    this.name = 'AegisApiError';
    this.statusCode = statusCode;
    this.details = details;
  }
}

async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  let baseUrl = getBaseUrl();

  // If running locally in a browser against the default Render cloud API,
  // route through Vite's local dev server proxy to bypass cross-origin browser CORS restrictions
  if (
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
    (baseUrl.includes('aegis-api-gzky.onrender.com') || baseUrl === '')
  ) {
    baseUrl = '';
  }

  const url = `${baseUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const token = getAuthToken();
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const res = await fetch(url, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let errorMsg = `HTTP ${res.status} ${res.statusText}`;
    let errBody: unknown = null;
    try {
      errBody = await res.json();
      if (errBody && typeof errBody === 'object') {
        const bodyObj = errBody as Record<string, unknown>;
        if (typeof bodyObj.detail === 'string') {
          errorMsg = bodyObj.detail;
        } else if (Array.isArray(bodyObj.detail)) {
          errorMsg = bodyObj.detail
            .map((item) => (typeof item === 'object' && item?.msg ? item.msg : JSON.stringify(item)))
            .join('; ');
        } else if (typeof bodyObj.message === 'string') {
          errorMsg = bodyObj.message;
        }
      }
    } catch {
      // Non-JSON response error
    }

    if (res.status === 401) {
      errorMsg = `Authentication required (401): ${errorMsg}`;
    }

    throw new AegisApiError(res.status, errorMsg, errBody);
  }

  // Handle 204 No Content
  if (res.status === 204) {
    return {} as T;
  }

  return (await res.json()) as T;
}

// ==========================================
// SYSTEM & HEALTH API
// ==========================================

export async function getHealthLive(): Promise<SystemLiveInfo> {
  return apiRequest<SystemLiveInfo>('/health/live');
}

export async function getHealthReady(): Promise<SystemHealth> {
  return apiRequest<SystemHealth>('/health/ready');
}

export async function issueAccessToken(params?: TokenIssueRequest): Promise<TokenIssueResponse> {
  return apiRequest<TokenIssueResponse>('/api/v1/auth/token', {
    method: 'POST',
    body: JSON.stringify(params || {}),
  });
}

// ==========================================
// TASK EXECUTION API
// ==========================================

export async function createTask(data: TaskCreateRequest): Promise<TaskResponse> {
  return apiRequest<TaskResponse>('/api/v1/tasks', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getTask(taskId: string): Promise<TaskResponse> {
  return apiRequest<TaskResponse>(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
}

export async function getTaskEvents(
  taskId: string,
  afterSeq?: number
): Promise<TaskEventsResponse> {
  const query = afterSeq !== undefined ? `?after_seq=${afterSeq}` : '';
  return apiRequest<TaskEventsResponse>(
    `/api/v1/tasks/${encodeURIComponent(taskId)}/events${query}`
  );
}

// ==========================================
// MULTI-AGENT ORCHESTRATION API
// ==========================================

export async function createOrchestration(
  data: OrchestrationCreateRequest
): Promise<OrchestrationResponse> {
  return apiRequest<OrchestrationResponse>('/api/v1/orchestrations', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getOrchestration(id: string): Promise<OrchestrationResponse> {
  return apiRequest<OrchestrationResponse>(
    `/api/v1/orchestrations/${encodeURIComponent(id)}`
  );
}

export async function getOrchestrationWorkers(
  id: string
): Promise<OrchestrationWorkersResponse> {
  return apiRequest<OrchestrationWorkersResponse>(
    `/api/v1/orchestrations/${encodeURIComponent(id)}/workers`
  );
}

export async function getOrchestrationResults(
  id: string
): Promise<OrchestrationResultsResponse> {
  return apiRequest<OrchestrationResultsResponse>(
    `/api/v1/orchestrations/${encodeURIComponent(id)}/results`
  );
}

// ==========================================
// MEMORY SYSTEM API
// ==========================================

export async function searchMemory(
  req: MemorySearchRequest
): Promise<MemorySearchResponse> {
  return apiRequest<MemorySearchResponse>('/api/v1/memory/search', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// ==========================================
// LEARNING & GOVERNANCE API
// ==========================================

export async function getLearningStats(): Promise<LearningStatsResponse> {
  return apiRequest<LearningStatsResponse>('/api/v1/learning/stats');
}

export async function getProcedures(
  tenantId?: string,
  status?: string
): Promise<ProceduresListResponse> {
  const params = new URLSearchParams();
  if (tenantId) params.set('tenant_id', tenantId);
  if (status) params.set('status', status);
  const q = params.toString() ? `?${params.toString()}` : '';
  return apiRequest<ProceduresListResponse>(
    `/api/v1/learning/governance/procedures${q}`
  );
}

export async function validateProcedure(
  procedureId: string,
  threshold?: number
): Promise<ProcedureValidateResponse> {
  return apiRequest<ProcedureValidateResponse>(
    '/api/v1/learning/governance/procedures/validate',
    {
      method: 'POST',
      body: JSON.stringify({
        procedure_id: procedureId,
        target_score_threshold: threshold,
      }),
    }
  );
}

export async function requestProcedurePromotion(
  procedureId: string,
  reason: string
): Promise<{ success: boolean; message?: string }> {
  return apiRequest<{ success: boolean; message?: string }>(
    '/api/v1/learning/governance/procedures/request-promotion',
    {
      method: 'POST',
      body: JSON.stringify({ procedure_id: procedureId, reason }),
    }
  );
}

export async function approveProcedurePromotion(
  procedureId: string,
  approverId: string,
  notes?: string
): Promise<{ success: boolean; message?: string }> {
  return apiRequest<{ success: boolean; message?: string }>(
    '/api/v1/learning/governance/procedures/approve',
    {
      method: 'POST',
      body: JSON.stringify({
        procedure_id: procedureId,
        approver_id: approverId,
        notes: notes || 'Approved via AEGIS Control Plane',
      }),
    }
  );
}

export async function promoteProcedure(
  procedureId: string
): Promise<{ success: boolean; message?: string }> {
  return apiRequest<{ success: boolean; message?: string }>(
    '/api/v1/learning/governance/procedures/promote',
    {
      method: 'POST',
      body: JSON.stringify({ procedure_id: procedureId }),
    }
  );
}

export async function disableProcedure(
  procedureId: string,
  reason: string
): Promise<{ success: boolean; message?: string }> {
  return apiRequest<{ success: boolean; message?: string }>(
    '/api/v1/learning/governance/procedures/disable',
    {
      method: 'POST',
      body: JSON.stringify({ procedure_id: procedureId, reason }),
    }
  );
}

export async function rollbackProcedure(
  procedureId: string,
  targetVersion?: number,
  reason?: string
): Promise<{ success: boolean; message?: string }> {
  return apiRequest<{ success: boolean; message?: string }>(
    '/api/v1/learning/governance/procedures/rollback',
    {
      method: 'POST',
      body: JSON.stringify({
        procedure_id: procedureId,
        target_version: targetVersion,
        reason: reason || 'Rollback triggered from AEGIS Control Plane',
      }),
    }
  );
}

export async function getDriftReport(): Promise<DriftReportResponse> {
  return apiRequest<DriftReportResponse>('/api/v1/learning/governance/drift');
}

// ==========================================
// SECURITY & AUDIT API
// ==========================================

export async function simulatePolicy(
  req: PolicySimulationRequest
): Promise<PolicySimulationResponse> {
  return apiRequest<PolicySimulationResponse>('/api/v1/policies/simulate', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getAuditCheckpoints(): Promise<AuditCheckpoint[]> {
  return apiRequest<AuditCheckpoint[]>('/api/v1/security/audit/checkpoints');
}

export async function createAuditCheckpoint(): Promise<AuditCheckpoint> {
  return apiRequest<AuditCheckpoint>('/api/v1/security/audit/checkpoints', {
    method: 'POST',
  });
}

export async function verifyAuditCheckpoint(
  checkpointId: string
): Promise<AuditVerifyResponse> {
  return apiRequest<AuditVerifyResponse>(
    `/api/v1/security/audit/checkpoints/${encodeURIComponent(checkpointId)}/verify`,
    {
      method: 'POST',
    }
  );
}
