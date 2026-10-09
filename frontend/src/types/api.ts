export interface HealthResponse {
  status: string;
  database: string;
  timestamp: string;
}


export interface SearchPayload {
  /** null follows the server default; true or false overrides it. */
  rerank?: boolean | null;
  query: string;
  limit?: number;
  violation_date?: string | null;
  /** Empty means the whole corpus. Naming a document not in it returns nothing. */
  doc_codes?: string[];
  deep?: boolean;
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

export interface AmendmentNote {
  doc_code: string;
  label: string;
  title: string;
  effective_date: string;
  path: string;
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
  amended_by: AmendmentNote[];
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
