import {
  StatutoryChunk,
  UnresolvedReference,
} from './staging';

export interface CreateSessionPayload {
  doc_code: string;
  title: string;
  raw_text: string;
  effective_date: string;
  expiration_date?: string | null;
  metadata?: Record<string, unknown>;
}

export interface StagingChunkDelta {
  path: string;
  verbatim_text?: string | null;
  contextualized_text?: string | null;
  start_line?: number | null;
  end_line?: number | null;
  metadata?: Record<string, unknown> | null;
  effective_date?: string | null;
  expiration_date?: string | null;
  review_status?: string | null;
  finalization_state?: string | null;
  dangling_dependencies?: UnresolvedReference[] | null;
}

export interface ChunkFinalizeStatus {
  path: string;
  review_status: string;
  finalization_state: string;
}

export interface BatchPatchPayload {
  updated_chunks: (StagingChunkDelta | StatutoryChunk)[];
  removed_paths: string[];
}

export interface BatchPatchResult {
  status: string;
  doc_code: string;
  updated_count: number;
  removed_count: number;
  cascaded_count: number;
  total_chunks: number;
  fields_modified: string[];
}

export interface FinalizeChunksPayload {
  paths: string[];
}

export interface FinalizeChunksResult {
  status: string;
  doc_code: string;
  finalized_count: number;
  pending_remaining: number;
  paths: string[];
  results: ChunkFinalizeStatus[];
}

export interface ReparentSubtreePayload {
  old_path_prefix: string;
  new_path_prefix: string;
  dry_run?: boolean;
  actor?: string;
}

export interface ReparentPathMapping {
  old_path: string;
  new_path: string;
}

export interface ReparentSubtreeResult {
  status: string;
  doc_code: string;
  dry_run: boolean;
  affected_chunks_count: number;
  affected_edges_count: number;
  old_path_prefix: string;
  new_path_prefix: string;
  total_chunks: number;
  sample_mappings: ReparentPathMapping[];
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

export interface RawTextResult {
  doc_code: string;
  title: string;
  raw_text: string;
  start_line?: number;
  end_line?: number;
  total_lines?: number;
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
  dense_similarity: number;
  keyword_matched: boolean;
  rerank_score: number | null;
  is_table: boolean;
  table_summary: string | null;
}

export interface SearchResponse {
  query: string;
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
  mode?: 'agent' | 'retrieve';
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

export interface StagingGrepPayload {
  pattern: string;
  is_regex?: boolean;
  case_sensitive?: boolean;
  search_in?: 'ALL' | 'VERBATIM' | 'CONTEXT' | 'PATH' | 'METADATA';
  limit?: number;
}

export interface GrepResult {
  pattern: string;
  is_regex: boolean;
  total_matches: number;
  returned: number;
  truncated: boolean;
  doc_code?: string | null;
  matches: SearchHit[];
}

export interface UnresolvedBacklogResult {
  doc_code?: string | null;
  total_unresolved: number;
  items: UnresolvedReference[];
}

export interface GraphTraversePayload {
  source_path: string;
  nav_direction?: 'OUTGOING' | 'INCOMING' | 'BOTH';
  depth_limit?: number;
  filter_relations?: string[];
}

export interface GraphTraversalStep {
  edge_id: string;
  source_chunk_id: string;
  target_chunk_id?: string | null;
  relation_type: string;
  depth: number;
  target_path: string;
  target_text?: string | null;
}

export interface GraphTraverseResult {
  source_path: string;
  total_paths: number;
  paths: GraphTraversalStep[];
}
