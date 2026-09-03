import React, { useMemo, useState } from 'react';
import {
  Edit3,
  FileSearch,
  Search,
  Zap,
} from 'lucide-react';
import { StagingDocumentSession } from '../../types/staging';
import { DocumentTreeNode } from '../../types/tree';

interface DryRunSearchSimulatorProps {
  session: StagingDocumentSession;
  onEditChunk: (node: DocumentTreeNode) => void;
}

interface SearchMatch {
  path: string;
  verbatim_text: string;
  contextualized_text: string;
  effective_date: string;
  score: number;
  matchedTokens: string[];
}

export const DryRunSearchSimulator: React.FC<DryRunSearchSimulatorProps> = ({
  session,
  onEditChunk,
}) => {
  const [query, setQuery] = useState('');
  const [matchLimit, setMatchLimit] = useState(5);
  const [searchTarget, setSearchTarget] = useState<'both' | 'verbatim' | 'contextualized'>('both');

  const exampleQueries = [
    'vượt đèn đỏ',
    'nồng độ cồn',
    'chạy quá tốc độ',
    'không đội mũ bảo hiểm',
    'đi ngược chiều trên đường cao tốc',
    'ô tô không thắt dây an toàn',
  ];

  // Fast Client-Side Lexical + TF-IDF Simulator over current staging chunks
  const searchResults: SearchMatch[] = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];

    const tokens = q.split(/\s+/).filter((t) => t.length > 1);
    if (tokens.length === 0) return [];

    const results: SearchMatch[] = [];

    for (const chunk of session.chunks) {
      const verbLower = chunk.verbatim_text.toLowerCase();
      const ctxLower = chunk.contextualized_text.toLowerCase();

      let textToSearch = `${verbLower} ${ctxLower}`;
      if (searchTarget === 'verbatim') textToSearch = verbLower;
      if (searchTarget === 'contextualized') textToSearch = ctxLower;

      let score = 0;
      const matchedTokens: string[] = [];

      // Exact phrase bonus
      if (textToSearch.includes(q)) {
        score += 10.0;
      }

      // Token frequency score
      for (const tok of tokens) {
        if (textToSearch.includes(tok)) {
          matchedTokens.push(tok);
          const count = textToSearch.split(tok).length - 1;
          score += 1.5 + Math.min(count, 5) * 0.5;
        }
      }

      if (score > 0) {
        results.push({
          path: chunk.path,
          verbatim_text: chunk.verbatim_text,
          contextualized_text: chunk.contextualized_text,
          effective_date: chunk.effective_date,
          score: Math.round(score * 100) / 100,
          matchedTokens,
        });
      }
    }

    results.sort((a, b) => b.score - a.score);
    return results.slice(0, matchLimit);
  }, [session.chunks, query, matchLimit, searchTarget]);

  return (
    <div className="flex h-full w-full flex-col overflow-y-auto bg-slate-950 p-6">
      {/* Top Header */}
      <div className="mb-6 rounded-xl border border-slate-800 bg-slate-900/90 p-5 shadow">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-600/20 text-amber-400 border border-amber-500/30">
            <Zap className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100">
              Thử Nghiệm Truy Xuất Pháp Lý (Dry-Run Search Simulator)
            </h3>
            <p className="text-xs text-slate-400">
              Kiểm thử truy vấn thực tế trực tiếp trên dữ liệu Staging để kiểm chứng chất lượng bóc tách và ngữ cảnh
            </p>
          </div>
        </div>

        {/* Query Input Box */}
        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-3 h-4 w-4 text-slate-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Nhập tình huống vi phạm, câu hỏi luật, hoặc từ khóa..."
              className="w-full rounded-xl border border-slate-700 bg-slate-950 py-2.5 pl-10 pr-4 text-xs font-medium text-slate-100 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 shadow-inner"
            />
          </div>

          <div className="flex items-center gap-2">
            <select
              value={searchTarget}
              onChange={(e) => setSearchTarget(e.target.value as any)}
              className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 focus:border-amber-500 focus:outline-none"
            >
              <option value="both">Tìm trên Toàn Văn + Ngữ Cảnh</option>
              <option value="verbatim">Chỉ tìm trên Nguyên Văn</option>
              <option value="contextualized">Chỉ tìm trên Ngữ Cảnh CPHC</option>
            </select>

            <select
              value={matchLimit}
              onChange={(e) => setMatchLimit(Number(e.target.value))}
              className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 focus:border-amber-500 focus:outline-none"
            >
              <option value={3}>Top 3</option>
              <option value={5}>Top 5</option>
              <option value={10}>Top 10</option>
            </select>
          </div>
        </div>

        {/* Quick Example Chips */}
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-slate-400 font-medium mr-1">Gợi ý truy vấn mẫu:</span>
          {exampleQueries.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => setQuery(ex)}
              className="rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1 text-[11px] text-slate-300 hover:border-amber-500 hover:text-amber-300 transition"
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      {/* Results Section */}
      <div className="flex-1 space-y-4">
        <div className="flex items-center justify-between pb-2 border-b border-slate-800">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            Kết Quả Phù Hợp ({searchResults.length} điều khoản)
          </h4>
          {query.trim() && (
            <span className="font-mono text-[11px] text-slate-400">
              Query: &ldquo;{query}&rdquo;
            </span>
          )}
        </div>

        {!query.trim() ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-12 text-center text-xs text-slate-400">
            <FileSearch className="mx-auto h-8 w-8 text-slate-500 mb-2" />
            <p className="font-semibold text-slate-300">Nhập câu hỏi để thử nghiệm truy xuất</p>
            <p className="mt-1 text-[11px]">Hệ thống sẽ tính điểm tương đồng trên toàn bộ chunks đang thẩm định.</p>
          </div>
        ) : searchResults.length === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-12 text-center text-xs text-slate-400">
            Không tìm thấy điều khoản nào khớp với từ khóa &ldquo;{query}&rdquo; trong văn bản này.
          </div>
        ) : (
          <div className="space-y-3">
            {searchResults.map((hit, rank) => (
              <div
                key={hit.path}
                className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 shadow transition hover:border-slate-700"
              >
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-500/20 text-amber-300 font-mono text-[11px] font-bold">
                      #{rank + 1}
                    </span>
                    <span className="font-mono text-xs font-bold text-slate-100">
                      {hit.path}
                    </span>
                    <span className="rounded bg-slate-950 px-2 py-0.5 font-mono text-[10px] font-bold text-amber-400 border border-amber-800/80">
                      Score: {hit.score}
                    </span>
                  </div>

                  <button
                    type="button"
                    title="Chỉnh sửa điều khoản này"
                    onClick={() =>
                      onEditChunk({
                        path: hit.path,
                        label: hit.path,
                        node_type: 'CLAUSE',
                        verbatim_text: hit.verbatim_text,
                        contextualized_text: hit.contextualized_text,
                        lead_sentence: '',
                        metadata: {},
                        effective_date: hit.effective_date,
                        children: [],
                      })
                    }
                    className="flex items-center gap-1 rounded px-2 py-1 text-xs text-slate-400 hover:bg-slate-800 hover:text-white transition"
                  >
                    <Edit3 className="h-3.5 w-3.5" />
                    <span>Sửa</span>
                  </button>
                </div>

                {/* Verbatim Text */}
                <div className="font-mono text-xs text-slate-200 leading-relaxed bg-slate-950/80 p-3 rounded-lg border border-slate-800/80 whitespace-pre-wrap mb-2">
                  {hit.verbatim_text}
                </div>

                {/* Contextualized Text preview */}
                {hit.contextualized_text && hit.contextualized_text !== hit.verbatim_text && (
                  <details className="text-[11px] text-slate-400">
                    <summary className="cursor-pointer hover:text-slate-200 select-none font-medium text-amber-400/90">
                      Xem văn cảnh CPHC tổng hợp
                    </summary>
                    <div className="mt-1.5 rounded bg-slate-900/90 p-2.5 border border-slate-800 font-mono text-slate-300 whitespace-pre-wrap leading-relaxed">
                      {hit.contextualized_text}
                    </div>
                  </details>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
