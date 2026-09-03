import {
  BatchPatchPayload,
  BatchPatchResponse,
  CreateEdgePayload,
  CreateSessionPayload,
  DeleteEdgePayload,
  GenericSuccessResponse,
  HealthResponse,
  PromoteSessionPayload,
  PromotionResultResponse,
  RawTextResponse,
  StatusTransitionPayload,
} from '../types/api';
import { SessionDiffResponse } from '../types/diff';
import { PreFlightValidationResponse } from '../types/preflight';
import {
  StagingDocumentSession,
  StagingEdge,
  StagingSessionSummary,
  StagingStatus,
} from '../types/staging';
import { DocumentTreeResponse } from '../types/tree';

const API_BASE = '/api';

class ApiClient {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...options.headers,
    };

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorMessage = `API Error ${response.status}: ${response.statusText}`;
      try {
        const errorJson = (await response.json()) as {
          error?: { message?: string; code?: number };
          detail?: string | { message?: string };
        };
        if (errorJson.error?.message) {
          errorMessage = errorJson.error.message;
        } else if (typeof errorJson.detail === 'string') {
          errorMessage = errorJson.detail;
        } else if (
          typeof errorJson.detail === 'object' &&
          errorJson.detail?.message
        ) {
          errorMessage = errorJson.detail.message;
        }
      } catch {
        // Fallback to response.statusText
      }
      throw new Error(errorMessage);
    }

    return response.json() as Promise<T>;
  }

  // 1. Health Probe
  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/health');
  }

  // 2. Session Listing & Creation
  async listSessions(): Promise<StagingSessionSummary[]> {
    return this.request<StagingSessionSummary[]>('/staging');
  }

  async getSession(docCode: string): Promise<StagingDocumentSession> {
    return this.request<StagingDocumentSession>(
      `/staging/${encodeURIComponent(docCode)}`
    );
  }

  async createSessionRaw(
    payload: CreateSessionPayload
  ): Promise<StagingDocumentSession> {
    return this.request<StagingDocumentSession>('/staging/raw', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async deleteSession(docCode: string): Promise<GenericSuccessResponse> {
    return this.request<GenericSuccessResponse>(
      `/staging/${encodeURIComponent(docCode)}`,
      {
        method: 'DELETE',
      }
    );
  }

  // 3. Document Hierarchy Tree
  async getDocumentTree(docCode: string): Promise<DocumentTreeResponse> {
    return this.request<DocumentTreeResponse>(
      `/staging/${encodeURIComponent(docCode)}/tree`
    );
  }

  // 4. Surgical Chunk Patching
  async patchChunks(
    docCode: string,
    payload: BatchPatchPayload
  ): Promise<BatchPatchResponse> {
    return this.request<BatchPatchResponse>(
      `/staging/${encodeURIComponent(docCode)}/patch`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  // 5. Relational Graph Edges
  async listEdges(docCode: string): Promise<StagingEdge[]> {
    return this.request<StagingEdge[]>(
      `/staging/${encodeURIComponent(docCode)}/edges`
    );
  }

  async addEdges(
    docCode: string,
    edges: CreateEdgePayload[]
  ): Promise<StagingDocumentSession> {
    return this.request<StagingDocumentSession>(
      `/staging/${encodeURIComponent(docCode)}/edges`,
      {
        method: 'POST',
        body: JSON.stringify(edges),
      }
    );
  }

  async deleteEdge(
    docCode: string,
    payload: DeleteEdgePayload
  ): Promise<StagingDocumentSession> {
    return this.request<StagingDocumentSession>(
      `/staging/${encodeURIComponent(docCode)}/edges`,
      {
        method: 'DELETE',
        body: JSON.stringify(payload),
      }
    );
  }

  // 6. Status Transition & Version Diff
  async updateSessionStatus(
    docCode: string,
    status: StagingStatus,
    actor = 'HUMAN:reviewer',
    description = ''
  ): Promise<StagingDocumentSession> {
    const payload: StatusTransitionPayload = {
      status,
      actor,
      description,
    };
    return this.request<StagingDocumentSession>(
      `/staging/${encodeURIComponent(docCode)}/status`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  async getSessionDiff(docCode: string): Promise<SessionDiffResponse> {
    return this.request<SessionDiffResponse>(
      `/staging/${encodeURIComponent(docCode)}/diff`
    );
  }

  async getRawText(docCode: string): Promise<RawTextResponse> {
    return this.request<RawTextResponse>(
      `/staging/${encodeURIComponent(docCode)}/raw`
    );
  }

  // 7. Pre-Flight Validation & Human Promotion
  async validateSession(docCode: string): Promise<PreFlightValidationResponse> {
    return this.request<PreFlightValidationResponse>(
      `/staging/${encodeURIComponent(docCode)}/validate`
    );
  }

  async promoteSession(
    docCode: string,
    payload: PromoteSessionPayload = { compute_embeddings: true }
  ): Promise<PromotionResultResponse> {
    return this.request<PromotionResultResponse>(
      `/staging/${encodeURIComponent(docCode)}/promote`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }
}

export const api = new ApiClient();
