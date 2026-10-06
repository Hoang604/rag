import {
  AnswerPayload,
  AnswerProvider,
  AnswerResponse,
  BatchPatchPayload,
  BatchPatchResult,
  CorpusDocument,
  CreateSessionPayload,
  FinalizeChunksResult,
  GenericSuccessResponse,
  GraphTraversePayload,
  GraphTraverseResult,
  GrepResult,
  HealthResponse,
  PromoteSessionPayload,
  PromotionResultResponse,
  RawTextResult,
  ReparentSubtreePayload,
  ReparentSubtreeResult,
  SearchPayload,
  SearchResponse,
  StagingGrepPayload,
  StatusTransitionPayload,
} from '../types/api';
import { PreFlightValidationResponse } from '../types/preflight';
import {
  RelationEdge,
  RelationEdgeFilter,
  StagingDocumentSession,
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
  ): Promise<BatchPatchResult> {
    return this.request<BatchPatchResult>(
      `/staging/${encodeURIComponent(docCode)}/patch`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  async finalizeChunks(
    docCode: string,
    paths: string[]
  ): Promise<FinalizeChunksResult> {
    return this.request<FinalizeChunksResult>(
      `/staging/${encodeURIComponent(docCode)}/finalize`,
      {
        method: 'POST',
        body: JSON.stringify({ paths }),
      }
    );
  }

  async reparentSubtree(
    docCode: string,
    payload: ReparentSubtreePayload
  ): Promise<ReparentSubtreeResult> {
    return this.request<ReparentSubtreeResult>(
      `/staging/${encodeURIComponent(docCode)}/reparent`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  // 5. Relational Graph Edges
  async listEdges(docCode: string): Promise<RelationEdge[]> {
    return this.request<RelationEdge[]>(
      `/staging/${encodeURIComponent(docCode)}/edges`
    );
  }

  async addEdges(
    docCode: string,
    edges: RelationEdge[]
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
    payload: RelationEdgeFilter
  ): Promise<StagingDocumentSession> {
    return this.request<StagingDocumentSession>(
      `/staging/${encodeURIComponent(docCode)}/edges`,
      {
        method: 'DELETE',
        body: JSON.stringify(payload),
      }
    );
  }

  // 6. Status Transition
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



  async getRawText(
    docCode: string,
    startLine = 1,
    endLine?: number
  ): Promise<RawTextResult> {
    const params = new URLSearchParams({ start_line: String(startLine) });
    if (endLine !== undefined) params.set('end_line', String(endLine));
    return this.request<RawTextResult>(
      `/staging/${encodeURIComponent(docCode)}/raw?${params.toString()}`
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

  // 8. Retrieval against the promoted corpus
  async search(payload: SearchPayload): Promise<SearchResponse> {
    return this.request<SearchResponse>('/search', {
      method: 'POST',
      body: JSON.stringify({ limit: 5, violation_date: null, ...payload }),
    });
  }

  // 9. The promoted corpus, for the retrieval scope selector
  async documents(): Promise<CorpusDocument[]> {
    return this.request<CorpusDocument[]>('/documents');
  }

  // 10. Which agent CLIs this machine has
  async answerProviders(): Promise<AnswerProvider[]> {
    return this.request<AnswerProvider[]>('/answer/providers');
  }

  // 11. Retrieve, then have a local agent CLI write the answer
  async answer(payload: AnswerPayload): Promise<AnswerResponse> {
    return this.request<AnswerResponse>('/answer', {
      method: 'POST',
      body: JSON.stringify({ limit: 5, violation_date: null, ...payload }),
    });
  }

  // 12. In-Memory Grep
  async grepSession(
    docCode: string,
    payload: StagingGrepPayload
  ): Promise<GrepResult> {
    return this.request<GrepResult>(
      `/staging/${encodeURIComponent(docCode)}/grep`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  // 14. Graph Traversal
  async traverseGraph(
    docCode: string,
    payload: GraphTraversePayload
  ): Promise<GraphTraverseResult> {
    return this.request<GraphTraverseResult>(
      `/staging/${encodeURIComponent(docCode)}/graph/traverse`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }
}

export const api = new ApiClient();
