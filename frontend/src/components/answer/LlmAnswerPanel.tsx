import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ChevronDown, Loader2, ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react';
import { api } from '../../services/api';
import { AnswerProvider, AnswerResponse, SearchHit } from '../../types/api';

const EXAMPLES = [
  'Xe máy vượt đèn đỏ phạt bao nhiêu?',
  'Nồng độ cồn chưa vượt quá 0,25 miligam với xe máy',
  'Tốc độ khai thác tối đa cho phép trên đường cao tốc',
];

const CITATION = /(\[#\d+\])/g;

const plain = (text: string) => text.replace(/\*\*/g, '');

const citedNumbers = (text: string): Set<number> =>
  new Set([...text.matchAll(/\[#(\d+)\]/g)].map((m) => Number(m[1])));

const SourceRow: React.FC<{
  index: number;
  hit: SearchHit;
  open: boolean;
  onToggle: () => void;
}> = ({ index, hit, open, onToggle }) => (
  <div data-testid="answer-source" id={`source-${index}`} className="rounded-lg border border-slate-800 bg-slate-950/60">
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs"
    >
      <span className="rounded bg-violet-500/20 px-1.5 py-0.5 font-mono font-bold text-violet-300">
        {index}
      </span>
      <span className="font-mono text-slate-400">{hit.doc_code}</span>
      <span className="flex-1 font-medium text-slate-100">{hit.address}</span>
      <ChevronDown className={`h-3.5 w-3.5 text-slate-500 transition ${open ? 'rotate-180' : ''}`} />
    </button>
    {open && (
      <p className="whitespace-pre-wrap border-t border-slate-800 px-3 py-2 font-mono text-[11px] leading-relaxed text-slate-300">
        {hit.verbatim_text}
      </p>
    )}
  </div>
);

export const LlmAnswerPanel: React.FC = () => {
  const [query, setQuery] = useState('');
  const [providers, setProviders] = useState<AnswerProvider[]>([]);
  const [provider, setProvider] = useState('claude');
  const [result, setResult] = useState<AnswerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [opened, setOpened] = useState<Set<number>>(new Set());
  const [showAll, setShowAll] = useState(false);
  const [agentMode, setAgentMode] = useState(true);

  useEffect(() => {
    api
      .answerProviders()
      .then((list) => {
        setProviders(list);
        const installed = list.find((p) => p.installed);
        if (installed) setProvider(installed.name);
      })
      .catch(() => setProviders([]));
  }, []);

  const ask = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setLoading(true);
      setError(null);
      setOpened(new Set());
      setShowAll(false);
      try {
        setResult(await api.answer({ query: trimmed, provider, limit: 5, mode: agentMode ? 'agent' : 'retrieve' }));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Không gọi được API.');
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    [provider, agentMode]
  );

  const toggle = (index: number) =>
    setOpened((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });

  const cited = useMemo(() => (result ? citedNumbers(result.answer) : new Set<number>()), [result]);
  const visible = result
    ? result.hits.map((hit, i) => ({ hit, index: i + 1 })).filter(({ index }) => showAll || cited.has(index) || cited.size === 0)
    : [];
  const hidden = result ? result.hits.length - visible.length : 0;

  const grounding = result?.grounding;
  const ungrounded =
    grounding && !grounding.ok
      ? [...grounding.unsupported_articles.map((a) => `Điều ${a}`), ...grounding.unsupported_amounts]
      : [];

  return (
    <div className="mx-auto h-full max-w-3xl overflow-y-auto p-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask(query);
        }}
        className="flex gap-2"
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Hỏi về luật giao thông..."
          className="flex-1 rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:border-violet-500 focus:outline-none"
        />
        <select
          data-testid="provider-select"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          className="rounded-xl border border-slate-700 bg-slate-950 px-2 py-2.5 text-xs text-slate-300 focus:border-violet-500 focus:outline-none"
        >
          {providers.map((p) => (
            <option key={p.name} value={p.name} disabled={!p.installed}>
              {p.label}
              {p.installed ? '' : ' — chưa cài'}
            </option>
          ))}
        </select>
        <button
          type="submit"
          data-testid="ask-button"
          disabled={loading || !query.trim()}
          className="flex items-center justify-center rounded-xl bg-violet-600 px-4 text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Hỏi"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
        </button>
      </form>

      <div className="mt-2 flex items-center gap-3 text-[11px] text-slate-500">
        <label className="flex cursor-pointer items-center gap-1.5">
          <input type="checkbox" checked={agentMode} onChange={(e) => setAgentMode(e.target.checked)} />
          Agent tự tra cứu nhiều lần (chính xác hơn, chậm hơn)
        </label>
        {loading && <span className="text-violet-300">{agentMode ? 'Đang tra cứu, thường 30–60 giây…' : 'Đang trả lời…'}</span>}
      </div>

      {!result && !loading && !error && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => {
                setQuery(example);
                void ask(example);
              }}
              className="rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1 text-[11px] text-slate-400 transition hover:border-violet-500 hover:text-violet-300"
            >
              {example}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div
          data-testid="answer-error"
          className="mt-4 flex items-start gap-2 rounded-xl border border-rose-900 bg-rose-950/40 p-3 text-xs text-rose-200"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div className="mt-5 space-y-4">
          {result.abstained ? (
            <div
              data-testid="grounding-abstained"
              className="flex items-center gap-2 rounded-xl border border-amber-800 bg-amber-950/30 px-3 py-2.5 text-xs text-amber-200"
            >
              <ShieldAlert className="h-4 w-4 flex-none" />
              <span>Không tìm thấy điều khoản liên quan nên không trả lời.</span>
            </div>
          ) : (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
              <p data-testid="answer-text" className="whitespace-pre-wrap text-[15px] leading-relaxed text-slate-100">
                {plain(result.answer)
                  .split(CITATION)
                  .map((part, i) => {
                    const match = /^\[#(\d+)\]$/.exec(part);
                    if (!match) return <React.Fragment key={i}>{part}</React.Fragment>;
                    const number = Number(match[1]);
                    return (
                      <button
                        key={i}
                        type="button"
                        onClick={() => {
                          setOpened((c) => new Set(c).add(number));
                          setShowAll(true);
                          document.getElementById(`source-${number}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }}
                        className="mx-0.5 rounded bg-violet-500/20 px-1 align-baseline font-mono text-[11px] font-bold text-violet-300 hover:bg-violet-500/40"
                      >
                        {number}
                      </button>
                    );
                  })}
              </p>
              <div className="mt-3 flex items-center gap-2 text-[11px] text-slate-500">
                {grounding?.ok ? (
                  <span data-testid="grounding-ok" className="flex items-center gap-1 text-emerald-400">
                    <ShieldCheck className="h-3.5 w-3.5" /> Số liệu khớp điều khoản
                  </span>
                ) : (
                  <span data-testid="grounding-failed" className="flex items-center gap-1 text-rose-400">
                    <ShieldAlert className="h-3.5 w-3.5" /> Không có trong điều khoản: {ungrounded.join(' · ')}
                  </span>
                )}
                <span className="font-mono" data-testid="answer-timing" title={`truy hồi ${result.retrieval_ms} ms · trả lời ${result.answer_ms} ms`}>
                  {result.provider}
                </span>
                {result.confidence !== 'high' && <span className="text-amber-400">độ tin cậy {result.confidence}</span>}
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            {visible.map(({ hit, index }) => (
              <SourceRow key={hit.path} index={index} hit={hit} open={opened.has(index)} onToggle={() => toggle(index)} />
            ))}
            {hidden > 0 && !showAll && (
              <button type="button" onClick={() => setShowAll(true)} className="text-[11px] text-slate-500 hover:text-slate-300">
                Xem thêm {hidden} điều khoản đã tìm thấy
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
