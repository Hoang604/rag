import React, { useCallback, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CalendarClock,
  Edit3,
  FileSearch,
  Loader2,
  Search,
  Zap,
} from 'lucide-react';
import { api } from '../../services/api';
import { SearchHit, SearchResponse } from '../../types/api';
import { StagingDocumentSession } from '../../types/staging';
import { DocumentTreeNode } from '../../types/tree';

interface DryRunSearchSimulatorProps {
  session: StagingDocumentSession;
  onEditChunk: (node: DocumentTreeNode) => void;
}

const VEHICLE_LABELS: Record<string, string> = {
  car: 'ô tô',
  motorcycle: 'xe mô tô',
  works_vehicle: 'xe máy chuyên dùng',
  bicycle: 'xe đạp, xe thô sơ',
  pedestrian: 'người đi bộ',
  draft_animal: 'xe vật nuôi kéo',
};

const ROLE_LABELS: Record<string, string> = {
  penalty: 'điều khoản có mức phạt',
  definition: 'giải thích từ ngữ',
};

const EXAMPLE_QUERIES = [
  'Xe máy vượt đèn đỏ phạt bao nhiêu?',
  'Ô tô vượt đèn đỏ phạt bao nhiêu?',
  'Nồng độ cồn chưa vượt quá 0,25 miligam với xe máy',
  'Tốc độ tối đa trên đường cao tốc là bao nhiêu?',
  'Thiết bị an toàn cho trẻ em là gì?',
  'Chở 3 người trên xe máy bị phạt thế nào?',
];

export const DryRunSearchSimulator: React.FC<DryRunSearchSimulatorProps> = ({
  session,
  onEditChunk,
}) => {
  const [query, setQuery] = useState('');
  const [matchLimit, setMatchLimit] = useState(5);
  const [violationDate, setViolationDate] = useState('');
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sessionPaths = useMemo(
    () => new Set(session.chunks.map((chunk) => chunk.path)),
    [session.chunks]
  );

  const runSearch = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setLoading(true);
      setError(null);
      try {
        const response = await api.search({
          query: trimmed,
          limit: matchLimit,
          violation_date: violationDate || null,
        });
        setResult(response);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Không gọi được API tìm kiếm.');
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    [matchLimit, violationDate]
  );

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    void runSearch(query);
  };

  const pickExample = (example: string) => {
    setQuery(example);
    void runSearch(example);
  };

  const hits: SearchHit[] = result?.hits ?? [];

  return (
    <div className="flex h-full w-full flex-col overflow-y-auto bg-slate-950 p-6">
      <div className="mb-6 rounded-xl border border-slate-800 bg-slate-900/90 p-5 shadow">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-amber-500/30 bg-amber-600/20 text-amber-400">
            <Zap className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100">Truy hồi thật trên corpus đã ban hành</h3>
            <p className="text-xs text-slate-400">
              Gọi thẳng <span className="font-mono text-amber-400/90">hybrid_search</span> — cùng đường mà agent MCP đi:
              vector + từ khoá, hợp nhất RRF, lọc thời hiệu và hai lớp facet.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-3 h-4 w-4 text-slate-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Nhập tình huống vi phạm hoặc câu hỏi luật..."
              className="w-full rounded-xl border border-slate-700 bg-slate-950 py-2.5 pl-10 pr-4 text-xs font-medium text-slate-100 shadow-inner focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
          </div>

          <div className="flex items-center gap-2">
            <label className="relative flex items-center" title="Ngày xảy ra hành vi vi phạm">
              <CalendarClock className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-slate-400" />
              <input
                type="date"
                value={violationDate}
                onChange={(e) => setViolationDate(e.target.value)}
                className="rounded-xl border border-slate-700 bg-slate-950 py-2 pl-8 pr-2 text-xs text-slate-200 focus:border-amber-500 focus:outline-none"
              />
            </label>

            <select
              value={matchLimit}
              onChange={(e) => setMatchLimit(Number(e.target.value))}
              className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 focus:border-amber-500 focus:outline-none"
            >
              <option value={3}>Top 3</option>
              <option value={5}>Top 5</option>
              <option value={10}>Top 10</option>
            </select>

            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="flex items-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-600/20 px-4 py-2 text-xs font-bold text-amber-300 transition hover:bg-amber-600/30 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
              <span>Tra cứu</span>
            </button>
          </div>
        </form>

        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[11px] font-medium text-slate-400">Câu hỏi mẫu:</span>
          {EXAMPLE_QUERIES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => pickExample(example)}
              className="rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1 text-[11px] text-slate-300 transition hover:border-amber-500 hover:text-amber-300"
            >
              {example}
            </button>
          ))}
        </div>

        {result && (
          <div className="mt-4 grid gap-2 border-t border-slate-800 pt-3 text-[11px] text-slate-400 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <span className="block font-semibold uppercase tracking-wider text-slate-500">Thời điểm vi phạm</span>
              <span className="font-mono text-slate-200">{result.violation_date}</span>
            </div>
            <div>
              <span className="block font-semibold uppercase tracking-wider text-slate-500">Facet loại xe</span>
              <span className="font-mono text-slate-200">
                {result.vehicle_class ? VEHICLE_LABELS[result.vehicle_class] ?? result.vehicle_class : '— không xác định'}
              </span>
            </div>
            <div>
              <span className="block font-semibold uppercase tracking-wider text-slate-500">Ý định câu hỏi</span>
              <span className="font-mono text-slate-200">
                {result.provision_role ? ROLE_LABELS[result.provision_role] ?? result.provision_role : '— không xác định'}
              </span>
            </div>
            <div>
              <span className="block font-semibold uppercase tracking-wider text-slate-500">Độ trễ</span>
              <span className="font-mono text-slate-200">{result.elapsed_ms} ms</span>
            </div>
            {result.expanded_query !== result.query && (
              <div className="sm:col-span-2 lg:col-span-4">
                <span className="block font-semibold uppercase tracking-wider text-slate-500">
                  Mở rộng truy vấn cho nhánh từ khoá
                </span>
                <span className="font-mono text-amber-300/80">
                  {result.expanded_query.slice(result.query.length).trim()}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            Kết quả ({hits.length} điều khoản)
          </h4>
          {result && (
            <span className="font-mono text-[11px] text-slate-400">&ldquo;{result.query}&rdquo;</span>
          )}
        </div>

        {error ? (
          <div className="flex items-start gap-2 rounded-xl border border-rose-900 bg-rose-950/40 p-4 text-xs text-rose-200">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" />
            <div>
              <p className="font-semibold">Không tra cứu được</p>
              <p className="mt-1 text-rose-300/80">{error}</p>
            </div>
          </div>
        ) : loading ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-12 text-center text-xs text-slate-400">
            <Loader2 className="mx-auto mb-2 h-8 w-8 animate-spin text-slate-500" />
            <p className="font-semibold text-slate-300">Đang truy hồi trên toàn corpus…</p>
          </div>
        ) : !result ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-12 text-center text-xs text-slate-400">
            <FileSearch className="mx-auto mb-2 h-8 w-8 text-slate-500" />
            <p className="font-semibold text-slate-300">Nhập câu hỏi để tra cứu</p>
            <p className="mt-1 text-[11px]">
              Đặt ngày vi phạm để xem hệ thống tự chuyển sang văn bản có hiệu lực tại thời điểm đó.
            </p>
          </div>
        ) : hits.length === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-12 text-center text-xs text-slate-400">
            Không có điều khoản nào còn hiệu lực khớp với câu hỏi này.
          </div>
        ) : (
          <div className="space-y-3">
            {hits.map((hit) => {
              const editable = sessionPaths.has(hit.path);
              return (
                <div
                  key={hit.path}
                  className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 shadow transition hover:border-slate-700"
                >
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-500/20 font-mono text-[11px] font-bold text-amber-300">
                        #{hit.rank}
                      </span>
                      <span className="rounded border border-slate-700 bg-slate-950 px-2 py-0.5 font-mono text-[10px] font-bold text-slate-200">
                        {hit.doc_code}
                      </span>
                      <span className="text-xs font-bold text-slate-100">{hit.address}</span>
                      <span className="rounded border border-amber-800/80 bg-slate-950 px-2 py-0.5 font-mono text-[10px] font-bold text-amber-400">
                        {hit.score.toFixed(4)}
                      </span>
                      {hit.vehicle_classes.map((vehicleClass) => (
                        <span
                          key={vehicleClass}
                          className="rounded border border-sky-800/80 bg-sky-950/60 px-2 py-0.5 text-[10px] font-semibold text-sky-300"
                        >
                          {VEHICLE_LABELS[vehicleClass] ?? vehicleClass}
                        </span>
                      ))}
                      {hit.provision_role && (
                        <span className="rounded border border-emerald-800/80 bg-emerald-950/60 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                          {ROLE_LABELS[hit.provision_role] ?? hit.provision_role}
                        </span>
                      )}
                    </div>

                    {editable && (
                      <button
                        type="button"
                        title="Chỉnh sửa điều khoản này"
                        onClick={() =>
                          onEditChunk({
                            path: hit.path,
                            label: hit.address,
                            node_type: 'CLAUSE',
                            verbatim_text: hit.verbatim_text,
                            contextualized_text: hit.contextualized_text,
                            lead_sentence: '',
                            metadata: {},
                            effective_date: hit.effective_date,
                            children: [],
                          })
                        }
                        className="flex items-center gap-1 rounded px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-white"
                      >
                        <Edit3 className="h-3.5 w-3.5" />
                        <span>Sửa</span>
                      </button>
                    )}
                  </div>

                  <p className="mb-2 font-mono text-[10px] text-slate-500">
                    {hit.path} · hiệu lực {hit.effective_date}
                    {hit.expiration_date ? ` · hết hiệu lực ${hit.expiration_date}` : ''}
                  </p>

                  <div className="mb-2 whitespace-pre-wrap rounded-lg border border-slate-800/80 bg-slate-950/80 p-3 font-mono text-xs leading-relaxed text-slate-200">
                    {hit.verbatim_text}
                  </div>

                  {hit.contextualized_text && hit.contextualized_text !== hit.verbatim_text && (
                    <details className="text-[11px] text-slate-400">
                      <summary className="cursor-pointer select-none font-medium text-amber-400/90 hover:text-slate-200">
                        Xem văn cảnh CPHC tổng hợp
                      </summary>
                      <div className="mt-1.5 whitespace-pre-wrap rounded border border-slate-800 bg-slate-900/90 p-2.5 font-mono leading-relaxed text-slate-300">
                        {hit.contextualized_text}
                      </div>
                    </details>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
