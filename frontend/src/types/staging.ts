export type StagingStatus = 'DRAFT' | 'AGENT_COMMITTED' | 'APPROVED' | 'PROMOTED' | 'AMENDMENT';

export interface UnresolvedReference {
  source_path: string;
  dependency_text: string;
  dependency_type: string;
  reason?: string;
}

export interface UnresolvedReferenceDelta {
  dependency_text: string;
  dependency_type?: string;
  reason?: string;
}

export interface StatutoryChunk {
  path: string;
  verbatim_text: string;
  contextualized_text: string;
  start_line: number;
  end_line: number;
  metadata?: Record<string, unknown>;
  effective_date: string;
  expiration_date?: string | null;
  review_status?: 'PENDING' | 'REVIEWED';
  finalization_state?: string;
  dangling_dependencies?: UnresolvedReference[];
}

export interface RelationEdge {
  source_path: string;
  target_path: string;
  relation_type: string;
  citation_text?: string | null;
}

export interface RelationEdgeFilter {
  source_path: string;
  target_path?: string | null;
  relation_type?: string | null;
  clear_all_targets?: boolean;
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
  raw_text: string;
  doc_metadata: Record<string, unknown>;
  chunks: StatutoryChunk[];
  edges: RelationEdge[];
  raw_ast_snapshot?: Record<string, unknown>[] | null;
  mutation_history: StagingMutationRecord[];
}
