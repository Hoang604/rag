import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Gauge,
  HardHat,
  IdCard,
  Loader2,
  Search,
  TrafficCone,
  Users,
  Wine,
  type LucideIcon,
} from 'lucide-react';
import { api } from '../../services/api';
import { AnswerProvider, AnswerResponse, SearchHit } from '../../types/api';

const TEAL = '#0f4c4f';

const TOPICS: { icon: LucideIcon; title: string; question: string }[] = [
  { icon: TrafficCone, title: 'Đèn tín hiệu', question: 'Xe máy vượt đèn đỏ bị phạt bao nhiêu?' },
  { icon: Wine, title: 'Nồng độ cồn', question: 'Uống rượu bia rồi lái xe máy bị phạt thế nào?' },
  { icon: Gauge, title: 'Tốc độ', question: 'Tốc độ tối đa trên đường cao tốc là bao nhiêu?' },
  { icon: HardHat, title: 'Mũ bảo hiểm', question: 'Không đội mũ bảo hiểm khi đi xe máy bị phạt bao nhiêu?' },
  { icon: Users, title: 'Chở người', question: 'Xe máy chở ba người bị phạt bao nhiêu?' },
  { icon: IdCard, title: 'Giấy phép lái xe', question: 'Còn dùng được bằng lái xe máy bằng giấy cũ không?' },
];

const CITATION = /(\[#\d+\])/g;
const MONEY = /(\d{1,3}(?:\.\d{3})+(?:\s*đồng)?(?:\s*(?:đến|-|–)\s*\d{1,3}(?:\.\d{3})+\s*đồng)?)/g;

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

const addressParts = (hit: SearchHit): string[] => {
  if (hit.address.includes('Điều')) {
    return hit.address.split(/ (?=Khoản|Điểm)/);
  }
  return hit.address.split('.').map((part) => {
    const [kind, ...rest] = part.split('_');
    return APPENDIX_PART[kind]?.(rest.join('_')) ?? part;
  });
};

const dateVn = (iso: string): string => {
  const [y, m, d] = iso.split('-');
  return y && m && d ? `${d}/${m}/${y}` : iso;
};

const RoadStrip: React.FC = () => (
  <div aria-hidden className="relative h-3 w-full bg-stone-800">
    <div
      className="absolute inset-x-0 top-1/2 h-[3px] -translate-y-1/2"
      style={{
        backgroundImage: 'repeating-linear-gradient(90deg, #e9a820 0 28px, transparent 28px 52px)',
      }}
    />
  </div>
);

const Source: React.FC<{
  number: number;
  hit: SearchHit;
  open: boolean;
  focused: boolean;
  onToggle: () => void;
}> = ({ number, hit, open, focused, onToggle }) => (
  <li
    data-testid="answer-source"
    id={`source-${number}`}
    className={`rounded-lg border bg-white p-4 transition ${focused ? 'border-[#0f4c4f] ring-2 ring-[#0f4c4f]/25' : 'border-stone-200'}`}
  >
    <button type="button" onClick={onToggle} className="flex w-full items-start gap-3 text-left">
      <span
        className="mt-0.5 flex h-7 w-7 flex-none items-center justify-center rounded-full text-sm font-bold text-white"
        style={{ background: TEAL }}
      >
        {number}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap gap-1.5">
          {addressParts(hit).map((part) => (
            <span key={part} className="rounded bg-stone-100 px-2 py-0.5 text-sm font-semibold text-stone-800">
              {part}
            </span>
          ))}
        </span>
        <span className="mt-1.5 block text-sm text-stone-500" title={hit.doc_title}>
          {documentLabel(hit)}
          <span className="text-stone-400"> · hiệu lực từ {dateVn(hit.effective_date)}</span>
        </span>
      </span>
    </button>
    {open && (
      <blockquote className="mt-3 whitespace-pre-wrap border-l-4 border-amber-400/70 bg-amber-50/40 py-2 pl-4 pr-2 text-[15px] leading-7 text-stone-800">
        {hit.verbatim_text}
      </blockquote>
    )}
    <button type="button" onClick={onToggle} className="mt-2 text-sm text-stone-500 underline underline-offset-4 hover:text-stone-800">
      {open ? 'Thu gọn' : 'Xem nguyên văn điều luật'}
    </button>
  </li>
);

const renderAnswer = (text: string, onCite: (n: number) => void): React.ReactNode =>
  withoutBold(text)
    .split(CITATION)
    .map((part, i) => {
      const match = /^\[#(\d+)\]$/.exec(part);
      if (match) {
        const number = Number(match[1]);
        return (
          <sup key={i}>
            <a
              href={`#source-${number}`}
              onClick={(e) => {
                e.preventDefault();
                onCite(number);
              }}
              className="mx-0.5 rounded px-1 text-xs font-bold text-white"
              style={{ background: TEAL }}
            >
              {number}
            </a>
          </sup>
        );
      }
      return (
        <React.Fragment key={i}>
          {part.split(MONEY).map((piece, j) =>
            j % 2 === 1 ? (
              <mark key={j} className="rounded bg-amber-200/70 px-1 font-semibold text-stone-900">
                {piece}
              </mark>
            ) : (
              <React.Fragment key={j}>{piece}</React.Fragment>
            )
          )}
        </React.Fragment>
      );
    });

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
  const [focused, setFocused] = useState<number | null>(null);
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
      setFocused(null);
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

  const jumpTo = (number: number) => {
    setClosed((c) => {
      const next = new Set(c);
      next.delete(number);
      return next;
    });
    setShowAll(true);
    setFocused(number);
    document.getElementById(`source-${number}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

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

  const started = loading || result !== null || error !== null;

  const searchBox = (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void ask(query);
      }}
      className="flex gap-2 rounded-xl border border-stone-300 bg-white p-2 shadow-sm focus-within:border-[#0f4c4f] focus-within:ring-2 focus-within:ring-[#0f4c4f]/20"
    >
      <Search className="my-auto ml-2 h-5 w-5 flex-none text-stone-400" />
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Ví dụ: xe máy chở 3 người bị phạt bao nhiêu?"
        className="min-w-0 flex-1 bg-transparent px-1 py-2 text-base text-stone-900 placeholder-stone-400 focus:outline-none"
      />
      <button
        type="submit"
        data-testid="ask-button"
        disabled={loading || !query.trim()}
        className="rounded-lg px-6 py-2 text-base font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-40"
        style={{ background: TEAL }}
      >
        Tra cứu
      </button>
    </form>
  );

  const options = (
    <details className="mt-3 text-sm text-stone-500">
      <summary className="cursor-pointer select-none hover:text-stone-800">Tuỳ chọn</summary>
      <div className="mt-2 space-y-3 rounded-lg border border-stone-200 bg-white p-4">
        <label className="flex cursor-pointer items-start gap-2 text-stone-800">
          <input type="checkbox" className="mt-1" checked={careful} onChange={(e) => setCareful(e.target.checked)} />
          <span>
            Tra cứu kỹ
            <span className="block text-stone-500">
              Tìm nhiều lần và đọc cả điều luật liên quan. Chính xác hơn nhưng mất khoảng một phút (chỉ dùng được với Claude).
            </span>
          </span>
        </label>
        <label className="flex flex-wrap items-center gap-2 text-stone-800">
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
  );

  return (
    <div className="h-full overflow-y-auto bg-[#f6f1e7] text-stone-900">
      <section style={{ background: '#efe7d6' }} className="border-b border-stone-300/70">
        <div className="mx-auto max-w-5xl px-5 pb-8 pt-10">
          {!started && (
            <>
              <h1 className="max-w-2xl text-[34px] font-bold leading-tight tracking-tight text-stone-900">
                Hỏi về luật giao thông, nhận câu trả lời kèm điều luật dẫn chứng
              </h1>
              <p className="mt-3 max-w-2xl text-base leading-7 text-stone-700">
                Gõ câu hỏi như bạn vẫn nói hằng ngày. Mức phạt, điều kiện, giấy tờ đều được đối chiếu với nghị định, thông tư và luật
                hiện hành.
              </p>
            </>
          )}
          <div className={started ? '' : 'mt-6'}>
            <div className="max-w-3xl">{searchBox}</div>
            <div className="max-w-3xl">{options}</div>
          </div>
        </div>
        <RoadStrip />
      </section>

      <div className="mx-auto max-w-5xl px-5 pb-16 pt-8">
        {!started && (
          <div>
            <h2 className="mb-3 text-xl font-bold text-stone-900">Thường được hỏi</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {TOPICS.map(({ icon: Icon, title, question }) => (
                <button
                  key={title}
                  type="button"
                  onClick={() => {
                    setQuery(question);
                    void ask(question);
                  }}
                  className="group flex items-start gap-3 rounded-xl border border-stone-300/80 bg-white p-4 text-left transition hover:-translate-y-0.5 hover:border-[#0f4c4f] hover:shadow-md"
                >
                  <span
                    className="flex h-10 w-10 flex-none items-center justify-center rounded-lg text-white"
                    style={{ background: TEAL }}
                  >
                    <Icon className="h-5 w-5" />
                  </span>
                  <span>
                    <span className="block font-semibold text-stone-900">{title}</span>
                    <span className="mt-0.5 block text-sm leading-5 text-stone-600">{question}</span>
                  </span>
                </button>
              ))}
            </div>
            <p className="mt-10 border-t border-stone-300/70 pt-4 text-sm leading-6 text-stone-500">
              Công cụ chỉ để tham khảo, không thay thế tư vấn pháp lý. Nội dung dựa trên các văn bản đã được nạp vào hệ thống.
            </p>
          </div>
        )}

        {loading && (
          <div className="flex items-center gap-3 rounded-xl border border-stone-300/80 bg-white p-5 text-stone-700" role="status">
            <Loader2 className="h-5 w-5 flex-none animate-spin" style={{ color: TEAL }} />
            <span>
              Đang tra cứu điều luật cho câu hỏi <strong className="font-semibold">“{asked}”</strong>…{' '}
              <span className="text-stone-500">{careful ? 'Có thể mất tới một phút.' : 'Chỉ vài giây.'}</span>
            </span>
          </div>
        )}

        {error && (
          <div data-testid="answer-error" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-900">
            Chưa tra cứu được. {error}
          </div>
        )}

        {result && !loading && (
          <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_380px]">
            <section>
              <p className="text-sm font-semibold uppercase tracking-wide text-stone-500">Câu hỏi</p>
              <p className="mt-1 text-xl font-bold text-stone-900">{result.query}</p>

              {result.abstained ? (
                <div data-testid="grounding-abstained" className="mt-5 rounded-xl border border-stone-300 bg-white p-5 text-[17px] leading-8">
                  Không tìm thấy điều luật nào liên quan. Hãy thử diễn đạt khác, hoặc nói rõ loại xe và hành vi.
                </div>
              ) : (
                <>
                  <div className="mt-5 rounded-xl border border-stone-300/80 border-l-[6px] bg-white p-5 shadow-sm" style={{ borderLeftColor: TEAL }}>
                    <p className="text-sm font-semibold uppercase tracking-wide text-stone-500">Trả lời</p>
                    <p data-testid="answer-text" className="mt-2 whitespace-pre-wrap text-[18px] leading-8 text-stone-900">
                      {renderAnswer(result.answer, jumpTo)}
                    </p>
                  </div>

                  {!answeredCarefully && (
                    <button
                      type="button"
                      onClick={() => {
                        setCareful(true);
                        void ask(result.query, true);
                      }}
                      className="mt-3 rounded-lg border border-stone-300 bg-white px-4 py-2 text-[15px] text-stone-700 hover:border-[#0f4c4f] hover:text-stone-900"
                    >
                      Chưa đúng ý? Tra cứu lại kỹ hơn (mất khoảng một phút)
                    </button>
                  )}

                  {mismatched.length > 0 && (
                    <p data-testid="grounding-failed" className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-[15px] leading-6 text-amber-900">
                      Lưu ý: câu trả lời nhắc tới {mismatched.join(', ')} nhưng không có trong các điều luật tìm được. Hãy đối chiếu với
                      điều luật bên cạnh, đừng chỉ dựa vào câu trả lời.
                    </p>
                  )}
                  {mismatched.length === 0 && result.confidence !== 'high' && (
                    <p className="mt-4 text-[15px] leading-6 text-stone-600">
                      Câu hỏi có thể nằm ngoài các văn bản đang có (luật và nghị định về giao thông đường bộ). Hãy kiểm tra kỹ điều luật bên cạnh.
                    </p>
                  )}
                  <span data-testid="grounding-ok" className="hidden" />
                  <span data-testid="answer-timing" className="hidden">
                    {result.provider} · {result.retrieval_ms} ms · {result.answer_ms} ms
                  </span>
                </>
              )}

              <button
                type="button"
                onClick={() => {
                  setResult(null);
                  setQuery('');
                }}
                className="mt-6 text-sm text-stone-500 underline underline-offset-4 hover:text-stone-800"
              >
                Hỏi câu khác
              </button>
              <p className="mt-8 border-t border-stone-300/70 pt-4 text-sm leading-6 text-stone-500">
                Công cụ chỉ để tham khảo, không thay thế tư vấn pháp lý.
              </p>
            </section>

            {sources.length > 0 && (
              <aside className="lg:sticky lg:top-4 lg:self-start">
                <h2 className="mb-3 text-xl font-bold text-stone-900">Căn cứ pháp lý</h2>
                <ul className="space-y-3">
                  {sources.map(({ hit, number }) => (
                    <Source
                      key={hit.path}
                      number={number}
                      hit={hit}
                      open={!closed.has(number)}
                      focused={focused === number}
                      onToggle={() => toggle(number)}
                    />
                  ))}
                </ul>
                {hiddenCount > 0 && !showAll && (
                  <button type="button" onClick={() => setShowAll(true)} className="mt-3 text-sm text-stone-500 underline underline-offset-4 hover:text-stone-800">
                    Xem thêm {hiddenCount} điều luật khác đã tìm thấy
                  </button>
                )}
              </aside>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

