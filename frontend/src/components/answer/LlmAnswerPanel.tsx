import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Loader2,
  MessagesSquare,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { api } from '../../services/api';
import { AnswerProvider, AnswerResponse } from '../../types/api';

/* An answer written by a model, next to the provisions it was written from.
 *
 * The evidence is not an appendix here. Everywhere else in this app the
 * reviewer reads statute text directly; this is the one screen where prose is
 * generated, so the provisions stay on the page beside it and the grounding
 * verdict is stated before the answer, not after. A reader who trusts the
 * paragraph and never scrolls is the failure this layout exists to prevent.
 */

const EXAMPLES = [
  'Xe máy vượt đèn đỏ phạt bao nhiêu?',
  'Ô tô gây tai nạn giao thông bị xử phạt hành chính thế nào?',
  'Nồng độ cồn chưa vượt quá 0,25 miligam với xe máy',
  'Tốc độ khai thác tối đa cho phép trên đường cao tốc',
];

export const LlmAnswerPanel: React.FC = () => {
  const [query, setQuery] = useState('');
  const [providers, setProviders] = useState<AnswerProvider[]>([]);
  const [provider, setProvider] = useState('claude');
  const [result, setResult] = useState<AnswerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      try {
        setResult(await api.answer({ query: trimmed, provider, limit: 5 }));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Không gọi được API.');
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    [provider]
  );

  const grounding = result?.grounding;
  const ungrounded =
    grounding && !grounding.ok
      ? [
          ...grounding.unsupported_articles.map((a) => `Điều ${a}`),
          ...grounding.unsupported_amounts,
        ]
      : [];

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="mb-3 flex items-start gap-3">
          <span className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-violet-500/15">
            <MessagesSquare className="h-5 w-5 text-violet-300" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-slate-100">
              Trả lời bằng agent CLI trên máy
            </h2>
            <p className="text-[11px] text-slate-400">
              Truy hồi trước, rồi đưa <em>chỉ</em> các điều khoản tìm được cho
              model. Model không thấy corpus và không được dùng kiến thức ngoài.
            </p>
          </div>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void ask(query);
          }}
          className="flex flex-col gap-2 sm:flex-row"
        >
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Nhập câu hỏi luật giao thông..."
            className="flex-1 rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:border-violet-500 focus:outline-none"
          />
          <select
            data-testid="provider-select"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-200 focus:border-violet-500 focus:outline-none"
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
            className="flex items-center justify-center gap-1.5 rounded-xl bg-violet-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            <span>Hỏi</span>
          </button>
        </form>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => {
                setQuery(example);
                void ask(example);
              }}
              className="rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1 text-[11px] text-slate-300 transition hover:border-violet-500 hover:text-violet-300"
            >
              {example}
            </button>
          ))}
        </div>

        {loading && (
          <p className="mt-3 text-[11px] text-slate-400">
            Đang truy hồi rồi gọi {provider}. Trên CPU thường mất 5–15 giây.
          </p>
        )}
      </div>

      {error && (
        <div
          data-testid="answer-error"
          className="mt-4 flex items-start gap-2 rounded-xl border border-rose-900 bg-rose-950/40 p-4 text-xs text-rose-200"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" />
          <div>
            <p className="font-semibold">Không trả lời được</p>
            <p className="mt-1 opacity-80">{error}</p>
          </div>
        </div>
      )}

      {result && (
        <div className="mt-4 space-y-4">
          {/* The verdict comes before the prose, deliberately. */}
          {result.abstained ? (
            <div
              data-testid="grounding-abstained"
              className="flex items-start gap-2 rounded-xl border border-amber-800 bg-amber-950/30 p-4 text-xs text-amber-200"
            >
              <ShieldAlert className="mt-0.5 h-4 w-4 flex-none" />
              <div>
                <p className="font-semibold">Không gọi model</p>
                <p className="mt-1 opacity-80">
                  Truy hồi không tìm được điều khoản nào liên quan, nên câu hỏi
                  không được gửi đi. Trả lời khi không có căn cứ là cách sinh ra
                  nội dung bịa.
                </p>
              </div>
            </div>
          ) : grounding?.ok ? (
            <div
              data-testid="grounding-ok"
              className="flex items-center gap-2 rounded-xl border border-emerald-900 bg-emerald-950/30 px-4 py-2.5 text-xs text-emerald-200"
            >
              <ShieldCheck className="h-4 w-4 flex-none" />
              <span>
                Mọi số hiệu điều khoản và mọi con số tiền trong câu trả lời đều
                khớp với các điều khoản đã truy hồi.
              </span>
            </div>
          ) : (
            <div
              data-testid="grounding-failed"
              className="flex items-start gap-2 rounded-xl border border-rose-900 bg-rose-950/40 p-4 text-xs text-rose-200"
            >
              <ShieldAlert className="mt-0.5 h-4 w-4 flex-none" />
              <div>
                <p className="font-semibold">
                  Câu trả lời nêu thứ không có trong điều khoản đã truy hồi
                </p>
                <p className="mt-1 font-mono opacity-90">
                  {ungrounded.join(' · ')}
                </p>
                <p className="mt-1 opacity-80">
                  Đừng trích dẫn phần này. Đọc trực tiếp các điều khoản bên dưới.
                </p>
              </div>
            </div>
          )}

          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
              <span className="rounded border border-violet-800 bg-violet-950/60 px-2 py-0.5 font-mono text-violet-300">
                {result.provider}
              </span>
              <span data-testid="answer-timing" className="font-mono">
                truy hồi {result.retrieval_ms} ms · trả lời {result.answer_ms} ms
              </span>
              <span className="font-mono">độ tin cậy: {result.confidence}</span>
            </div>
            <p
              data-testid="answer-text"
              className="whitespace-pre-wrap text-sm leading-relaxed text-slate-100"
            >
              {result.answer}
            </p>
          </div>

          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Điều khoản model đã đọc ({result.hits.length})
            </h3>
            <div className="space-y-2">
              {result.hits.map((hit, index) => (
                <div
                  key={hit.path}
                  data-testid="answer-source"
                  className="rounded-xl border border-slate-800 bg-slate-950/60 p-3"
                >
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px]">
                    <span className="rounded bg-violet-500/20 px-1.5 py-0.5 font-mono font-bold text-violet-300">
                      #{index + 1}
                    </span>
                    <span className="rounded border border-slate-700 bg-slate-950 px-2 py-0.5 font-mono font-bold text-slate-200">
                      {hit.doc_code}
                    </span>
                    <span className="font-semibold text-slate-100">
                      {hit.address}
                    </span>
                    <span className="font-mono text-slate-500">
                      hiệu lực {hit.effective_date}
                    </span>
                  </div>
                  <p className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-slate-300">
                    {hit.verbatim_text}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
