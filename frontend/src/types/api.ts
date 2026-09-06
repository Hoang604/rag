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

export interface SearchPayload {
  /** null follows the server default; true or false overrides it. */
  rerank?: boolean | null;
  query: string;
  limit?: number;
  violation_date?: string | null;
}

export interface SearchHit {
  rank: number;
  doc_code: string;
  doc_title: string;
  path: string;
  address: string;
  verbatim_text: string;
  contextualized_text: string;
  effective_date: string;
  expiration_date: string | null;
  score: number;
  vehicle_classes: string[];
  provision_role: string | null;
  dense_similarity: number;
  keyword_matched: boolean;
  /** Set when a cross-encoder decided the order; then it, not score, explains it. */
  rerank_score: number | null;
}

export interface SearchResponse {
  query: string;
  expanded_query: string;
  vehicle_class: string | null;
  provision_role: string | null;
  violation_date: string;
  elapsed_ms: number;
  confidence: 'high' | 'low' | 'none';
  hits: SearchHit[];
}
