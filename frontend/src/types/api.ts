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

/** One ingested document, for scoping a query. */
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
  /** Can answer in agent mode, searching with the MCP tools itself. */
  agent: boolean;
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

export type EvalSplit = 'dev' | 'holdout';
export type EvalFoundIn = 'both' | 'semantic_only' | 'verbatim_only' | 'missed';

/** One question, the agent's first search call for it, and the provisions that answer it. */
export interface EvalCase {
  id: string;
  split: EvalSplit;
  question: string;
  query: string;
  pattern: string;
  is_regex: boolean;
  /** null: the question names no violation date, so search uses today. */
  temporal_violation_date: string | null;
  doc_codes: string[];
  /** Any of these paths, or a provision under one, answers the question. */
  expected: string[];
  /** null: nothing about the label needs a reviewer's attention. */
  note: string | null;
}

export interface EvalOutcome {
  id: string;
  split: EvalSplit;
  found_in: EvalFoundIn;
  position: number | null;
  matched_path: string | null;
}

export interface ProvisionMatch {
  path: string;
  address: string;
  text: string;
  /** Line span of `text` in the document's raw text. */
  start_line: number;
  end_line: number;
  amended_by?: AmendmentNote[];
  doc_code: string;
  context: string;
}

export interface LegalSearchResult {
  query: string;
  pattern: string;
  violation_date: string;
  both: ProvisionMatch[];
  semantic_only: ProvisionMatch[];
  verbatim_only: ProvisionMatch[];
  verbatim_total: number;
  verbatim_truncated: boolean;
}

export interface EvalCaseRun {
  outcome: EvalOutcome;
  result: LegalSearchResult;
}

export interface EvalSplitSummary {
  split: EvalSplit;
  total: number;
  both: number;
  semantic_only: number;
  verbatim_only: number;
  missed: number;
}

export interface EvalRun {
  outcomes: EvalOutcome[];
  summaries: EvalSplitSummary[];
}
