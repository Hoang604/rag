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
  metadata: Record<string, unknown>;
  effective_date?: string | null;
  expiration_date?: string | null;
  children: DocumentTreeNode[];
}

export interface DocumentTreeResponse {
  doc_code: string;
  title: string;
  total_nodes: number;
  root: DocumentTreeNode;
}
