import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../services/api';
import { AnswerProvider, AnswerResponse, SearchHit } from '../../types/api';

const EXAMPLES = [
  'Xe máy vượt đèn đỏ bị phạt bao nhiêu?',
  'Uống rượu bia rồi lái xe máy bị phạt thế nào?',
  'Tốc độ tối đa trên đường cao tốc là bao nhiêu?',
];

const CITATION = /(\[#\d+\])/g;

const ink = 'text-[#1d3b4a]';

const withoutBold = (text: string) => text.replace(/\*\*/g, '');

const citedNumbers = (text: string): Set<number> =>
  new Set([...text.matchAll(/\[#(\d+)\]/g)].map((m) => Number(m[1])));

const DOC_KIND = /^(Nghị định|Thông tư liên tịch|Thông tư|Luật|Bộ luật|Pháp lệnh|Quy chuẩn kỹ thuật quốc gia|Quy chuẩn)/i;

const documentLabel = (hit: SearchHit): string => {
  const kind = DOC_KIND.exec(hit.doc_title)?.[1];
  return kind ? `${kind} ${hit.doc_code}` : hit.doc_code;
};

const APPENDIX_PART: Record<string, (value: string) => string> = {
  app: (v) => `Phụ lục ${v.toUpperCase()}`,
  i: (v) => `mục ${v.replace(/_/g, '.')}`,
  p: (v) => `điểm ${v.replace(/_/g, '.')}`,
};

const readableAddress = (hit: SearchHit): string => {
  if (hit.address.includes('Điều')) {
    return hit.address.replace(/ (Khoản|Điểm)/g, ', $1');
  }
  const parts = hit.address.split('.').map((part) => {
    const [kind, ...rest] = part.split('_');
    return APPENDIX_PART[kind]?.(rest.join('_')) ?? part;
  });
  return parts.join(', ');
};

const dateVn = (iso: string): string => {
  const [y, m, d] = iso.split('-');
  return y && m && d ? `${d}/${m}/${y}` : iso;
};

const Source: React.FC<{
  number: number;
  hit: SearchHit;
  open: boolean;
  onToggle: () => void;
}> = ({ number, hit, open, onToggle }) => (
  <li data-testid="answer-source" id={`source-${number}`} className="border-t border-stone-200 py-3">
    <button type="button" onClick={onToggle} className="flex w-full items-baseline gap-3 text-left">
      <span className={`w-5 flex-none text-sm font-semibold ${ink}`}>{number}.</span>
      <span className="flex-1">
        <span className="block font-medium text-stone-900">{readableAddress(hit)}</span>
        <span className="block text-sm text-stone-500" title={hit.doc_title}>
          {documentLabel(hit)} · có hiệu lực từ {dateVn(hit.effective_date)}
        </span>
      </span>
      <span className="flex-none text-sm text-stone-500 underline">{open ? 'Thu gọn' : 'Xem nguyên văn'}</span>
    </button>
    {open && (
      <blockquote className="ml-8 mt-2 whitespace-pre-wrap border-l-2 border-stone-300 pl-4 text-[15px] leading-7 text-stone-700">
        {hit.verbatim_text}
      </blockquote>
    )}
  </li>
);

export const LlmAnswerPanel: React.FC = () => {
  const [query, setQuery] = useState('');
  const [providers, setProviders] = useState<AnswerProvider[]>([]);
  const [provider, setProvider] = useState('claude');
  const [careful, setCareful] = useState(true);
  const [result, setResult] = useState<AnswerResponse | null>(null);
  const [asked, setAsked] = useState('');
  const [answeredCarefully, setAnsweredCarefully] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [closed, setClosed] = useState<Set<number>>(new Set());
  const [showAll, setShowAll] = useState(false);

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
    async (text: string, forceCareful = false) => {
      const mode = careful || forceCareful ? 'agent' : 'retrieve';
      const trimmed = text.trim();
      if (!trimmed) return;
      setLoading(true);
      setError(null);
      setClosed(new Set());
      setShowAll(false);
      setAsked(trimmed);
      setAnsweredCarefully(mode === 'agent');
      try {
        setResult(await api.answer({ query: trimmed, provider, limit: 5, mode }));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Không kết nối được máy chủ.');
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    [provider, careful]
  );

  const toggle = (number: number) =>
    setClosed((current) => {
      const next = new Set(current);
      if (next.has(number)) next.delete(number);
      else next.add(number);
      return next;
    });

  const cited = useMemo(() => (result ? citedNumbers(result.answer) : new Set<number>()), [result]);
  const sources = result
    ? result.hits
        .map((hit, i) => ({ hit, number: i + 1 }))
        .filter(({ number }) => showAll || cited.size === 0 || cited.has(number))
    : [];
  const hiddenCount = result ? result.hits.length - sources.length : 0;

  const grounding = result?.grounding;
  const mismatched =
    grounding && !grounding.ok
      ? [...grounding.unsupported_articles.map((a) => `Điều ${a}`), ...grounding.unsupported_amounts]
      : [];

  return (
    <div className="h-full overflow-y-auto bg-[#faf8f4] text-stone-900">
      <div className="mx-auto max-w-3xl px-5 pb-16 pt-10">
        <h1 className="text-[28px] font-semibold leading-tight text-stone-900">Tra cứu luật giao thông đường bộ</h1>
        <p className="mt-2 text-[15px] leading-6 text-stone-600">
          Gõ câu hỏi bằng lời của bạn. Mỗi câu trả lời đều kèm điều luật gốc để bạn tự đối chiếu.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void ask(query);
          }}
          className="mt-6 flex gap-2"
        >
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ví dụ: xe máy chở 3 người bị phạt bao nhiêu?"
            className="min-w-0 flex-1 rounded-md border border-stone-300 bg-white px-4 py-3 text-base text-stone-900 placeholder-stone-400 focus:border-[#1d3b4a] focus:outline-none focus:ring-1 focus:ring-[#1d3b4a]"
          />
          <button
            type="submit"
            data-testid="ask-button"
            disabled={loading || !query.trim()}
            className="rounded-md bg-[#1d3b4a] px-6 py-3 text-base font-medium text-white hover:bg-[#16303c] disabled:cursor-not-allowed disabled:opacity-40"
          >
            Tra cứu
          </button>
        </form>

        {!result && !loading && !error && (
          <div className="mt-4 text-[15px] text-stone-600">
            <p className="mb-1">Thử hỏi:</p>
            <ul className="space-y-1">
              {EXAMPLES.map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    onClick={() => {
                      setQuery(example);
                      void ask(example);
                    }}
                    className={`text-left underline decoration-stone-300 underline-offset-4 hover:decoration-[#1d3b4a] ${ink}`}
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <details className="mt-5 text-sm text-stone-500">
          <summary className="cursor-pointer select-none hover:text-stone-700">Tuỳ chọn</summary>
          <div className="mt-2 space-y-2 rounded-md border border-stone-200 bg-white p-3">
            <label className="flex cursor-pointer items-start gap-2 text-stone-700">
              <input type="checkbox" className="mt-1" checked={careful} onChange={(e) => setCareful(e.target.checked)} />
              <span>
                Tra cứu kỹ
                <span className="block text-stone-500">
                  Tìm nhiều lần và đọc cả điều luật liên quan. Chính xác hơn nhưng mất khoảng một phút (chỉ dùng được với Claude).
                </span>
              </span>
            </label>
            <label className="flex items-center gap-2 text-stone-700">
              Công cụ soạn câu trả lời
              <select
                data-testid="provider-select"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="rounded border border-stone-300 bg-white px-2 py-1 text-stone-800"
              >
                {providers.map((p) => (
                  <option key={p.name} value={p.name} disabled={!p.installed}>
                    {p.label}
                    {p.installed ? '' : ' (chưa cài)'}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </details>

        {loading && (
          <p className="mt-8 text-[15px] text-stone-600" role="status">
            Đang tra cứu điều luật cho câu hỏi “{asked}”…{' '}
            <span className="text-stone-400">{careful ? 'Có thể mất tới một phút.' : 'Vài giây.'}</span>
          </p>
        )}

        {error && (
          <div data-testid="answer-error" className="mt-8 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-[15px] text-red-900">
            Chưa tra cứu được. {error}
          </div>
        )}

        {result && !loading && (
          <section className="mt-8">
            <p className="text-sm text-stone-500">Câu hỏi: {result.query}</p>

            {result.abstained ? (
              <p data-testid="grounding-abstained" className="mt-3 text-[17px] leading-8 text-stone-800">
                Không tìm thấy điều luật nào liên quan. Hãy thử diễn đạt khác, hoặc nói rõ loại xe và hành vi.
              </p>
            ) : (
              <>
                <p data-testid="answer-text" className="mt-3 whitespace-pre-wrap text-[18px] leading-8 text-stone-900">
                  {withoutBold(result.answer)
                    .split(CITATION)
                    .map((part, i) => {
                      const match = /^\[#(\d+)\]$/.exec(part);
                      if (!match) return <React.Fragment key={i}>{part}</React.Fragment>;
                      const number = Number(match[1]);
                      return (
                        <sup key={i}>
                          <a
                            href={`#source-${number}`}
                            onClick={(e) => {
                              e.preventDefault();
                              setClosed((c) => {
                                const next = new Set(c);
                                next.delete(number);
                                return next;
                              });
                              setShowAll(true);
                              document.getElementById(`source-${number}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            }}
                            className={`mx-0.5 font-semibold underline ${ink}`}
                          >
                            [{number}]
                          </a>
                        </sup>
                      );
                    })}
                </p>

                {!answeredCarefully && (
                  <button
                    type="button"
                    onClick={() => {
                      setCareful(true);
                      void ask(result.query, true);
                    }}
                    className="mt-3 text-[15px] text-stone-600 underline underline-offset-4 hover:text-stone-900"
                  >
                    Chưa đúng ý? Tra cứu lại kỹ hơn (mất khoảng một phút)
                  </button>
                )}

                {mismatched.length > 0 && (
                  <p data-testid="grounding-failed" className="mt-3 rounded-md border border-amber-300 bg-amber-50 px-4 py-2.5 text-[15px] text-amber-900">
                    Lưu ý: câu trả lời nhắc tới {mismatched.join(', ')} nhưng không có trong các điều luật tìm được. Hãy đối chiếu với
                    điều luật bên dưới, đừng chỉ dựa vào câu trả lời.
                  </p>
                )}
                {mismatched.length === 0 && result.confidence !== 'high' && (
                  <p className="mt-3 text-[15px] text-stone-600">
                    Câu hỏi có thể nằm ngoài các văn bản đang có (luật và nghị định về giao thông đường bộ). Hãy kiểm tra kỹ điều luật bên dưới.
                  </p>
                )}
                <span data-testid="grounding-ok" className="hidden" />
                <span data-testid="answer-timing" className="hidden">
                  {result.provider} · {result.retrieval_ms} ms · {result.answer_ms} ms
                </span>
              </>
            )}

            {sources.length > 0 && (
              <div className="mt-8">
                <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-stone-500">Căn cứ pháp lý</h2>
                <ul className="border-b border-stone-200">
                  {sources.map(({ hit, number }) => (
                    <Source key={hit.path} number={number} hit={hit} open={!closed.has(number)} onToggle={() => toggle(number)} />
                  ))}
                </ul>
                {hiddenCount > 0 && !showAll && (
                  <button type="button" onClick={() => setShowAll(true)} className="mt-2 text-sm text-stone-500 underline hover:text-stone-800">
                    Xem thêm {hiddenCount} điều luật khác đã tìm thấy
                  </button>
                )}
              </div>
            )}
          </section>
        )}

        <p className="mt-14 border-t border-stone-200 pt-4 text-sm leading-6 text-stone-500">
          Công cụ chỉ để tham khảo, không thay thế tư vấn pháp lý. Nội dung dựa trên các văn bản đã được nạp vào hệ thống.
        </p>
      </div>
    </div>
  );
};
