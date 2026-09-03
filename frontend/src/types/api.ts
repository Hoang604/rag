import { StagingChunk } from './staging';

export interface CreateSessionPayload {
  doc_code: string;
  title: string;
  raw_text: string;
  effective_date: string;
  expiration_date?: string | null;
  metadata?: Record<string, unknown>;
}

export interface BatchPatchPayload {
  updated_chunks: StagingChunk[];
  removed_paths: string[];
}

export interface BatchPatchResponse {
  status: string;
  doc_code: string;
  updated_count: number;
  removed_count: number;
  total_chunks: number;
}

export interface CreateEdgePayload {
  source_path: string;
  target_path?: string | null;
  target_external_ref?: string | null;
  relation_type: string;
  citation_text?: string | null;
  metadata?: Record<string, unknown>;
}

export interface DeleteEdgePayload {
  source_path: string;
  target_path?: string | null;
  relation_type: string;
}

export interface StatusTransitionPayload {
  status: string;
  actor?: string;
  description?: string;
}

export interface PromoteSessionPayload {
  reviewer_notes?: string | null;
  compute_embeddings?: boolean;
}

export interface PromotionResultResponse {
  status: 'SUCCESS' | 'FAILED';
  doc_code: string;
  document_id: string;
  chunks_promoted: number;
  edges_promoted: number;
  promoted_at: string;
  message: string;
}

export interface RawTextResponse {
  doc_code: string;
  title: string;
  raw_text: string;
  chunks_count: number;
}

export interface HealthResponse {
  status: string;
  database: string;
  timestamp: string;
}

export interface GenericSuccessResponse {
  status: string;
  message: string;
  doc_code?: string | null;
}

export interface ApiErrorResponse {
  error: {
    code: number;
    message: string;
    data?: unknown;
  };
}
