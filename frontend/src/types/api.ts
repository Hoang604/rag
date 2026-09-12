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
  /** Empty means the whole corpus. Naming a document not in it returns nothing. */
  doc_codes?: string[];
}

/** One promoted document, for scoping a query. */
export interface CorpusDocument {
  doc_code: string;
  title: string;
  effective_date: string;
  expiration_date: string | null;
  in_force: boolean;
  chunk_count: number;
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
  /** A table window. Its text is rows, so it reads as broken prose without
   * the summary and the sibling windows beside it. */
  is_table: boolean;
  /** The sentence written at ingestion that made the table findable. */
  table_summary: string | null;
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

/** One agent CLI installed on the machine that can compose an answer. */
export interface AnswerProvider {
  name: string;
  label: string;
  installed: boolean;
}

export interface AnswerPayload {
  query: string;
  limit?: number;
  violation_date?: string | null;
  rerank?: boolean | null;
  doc_codes?: string[];
  provider: string;
}

/** Where the answer went outside the provisions it was given. */
export interface Grounding {
  ok: boolean;
  unsupported_articles: string[];
  unsupported_amounts: string[];
}

export interface AnswerResponse {
  query: string;
  provider: string;
  answer: string;
  /** True when retrieval found nothing and no model was called at all. */
  abstained: boolean;
  grounding: Grounding;
  confidence: 'high' | 'low' | 'none';
  retrieval_ms: number;
  answer_ms: number;
  hits: SearchHit[];
}
