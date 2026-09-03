export type StagingStatus = 'DRAFT' | 'AGENT_COMMITTED' | 'APPROVED' | 'PROMOTED';

export interface StagingChunk {
  path: string;
  verbatim_text: string;
  contextualized_text: string;
  lead_sentence?: string;
  metadata?: Record<string, unknown>;
  effective_date: string;
  expiration_date?: string | null;
}

export interface StagingEdge {
  source_path: string;
  target_path?: string | null;
  target_external_ref?: string | null;
  relation_type: string;
  citation_text?: string | null;
  metadata?: Record<string, unknown>;
}

export interface StagingMutationRecord {
  actor: string;
  action_type: string;
  description: string;
  timestamp: string;
  diff_payload?: Record<string, unknown>;
}

export interface StagingSessionSummary {
  doc_code: string;
  title: string;
  status: StagingStatus;
  total_chunks: number;
  total_edges: number;
  effective_date: string;
  expiration_date?: string | null;
  created_at: string;
  updated_at: string;
  committed_at?: string | null;
  promoted_at?: string | null;
}

export interface StagingDocumentSession {
  doc_code: string;
  title: string;
  status: StagingStatus;
  effective_date: string;
  expiration_date?: string | null;
  created_at: string;
  updated_at: string;
  committed_at?: string | null;
  promoted_at?: string | null;
  raw_text?: string | null;
  doc_metadata?: Record<string, unknown>;
  chunks: StagingChunk[];
  edges: StagingEdge[];
  raw_ast_snapshot?: Record<string, unknown>[] | null;
  mutation_history: StagingMutationRecord[];
}
