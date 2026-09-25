export type NodeType =
  | 'DOCUMENT'
  | 'CHAPTER'
  | 'SECTION'
  | 'ARTICLE'
  | 'CLAUSE'
  | 'POINT'
  | 'APPENDIX';

export interface DocumentTreeNode {
  path: string;
  label: string;
  node_type: NodeType | string;
  verbatim_text: string;
  contextualized_text: string;
  lead_sentence: string;
  start_line: number;
  end_line: number;
  metadata: Record<string, unknown>;
  effective_date?: string | null;
  expiration_date?: string | null;
  review_status?: 'PENDING' | 'REVIEWED' | string;
  children: DocumentTreeNode[];
}

export interface DocumentTreeResponse {
  doc_code: string;
  title: string;
  total_nodes: number;
  total_finalized?: number;
  total_pending?: number;
  progress_percent?: number;
  root: DocumentTreeNode;
}
