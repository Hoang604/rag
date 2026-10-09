import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowUp, ChevronRight, Loader2 } from 'lucide-react';
import { api } from '../../services/api';
import { useI18n } from '../../i18n/I18nContext';
import { RoadBanner, SignRow } from '../art/TrafficArt';
import { AnswerProvider, AnswerResponse, SearchHit } from '../../types/api';

const EXAMPLES = [
  'Xe máy vượt đèn đỏ phạt bao nhiêu?',
  'Uống một lon bia rồi chạy xe máy có bị phạt không?',
  'Trẻ em dưới 10 tuổi ngồi ghế trước ô tô',
  'Bằng lái bị trừ hết điểm thì làm gì?',
];

const CITATION = /(\[#\d+\])/g;

const plain = (text: string) => text.replace(/\*\*/g, '');

const citedNumbers = (text: string): Set<number> =>
  new Set([...text.matchAll(/\[#(\d+)\]/g)].map((m) => Number(m[1])));

const INK = 'text-slate-100';
const MUTED = 'text-slate-400';

const SourceRow: React.FC<{
  index: number;
  hit: SearchHit;
  open: boolean;
  onToggle: () => void;
}> = ({ index, hit, open, onToggle }) => (
  <li data-testid="answer-source" id={`source-${index}`} className="border-t border-slate-800 first:border-t-0">
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="group flex w-full items-baseline gap-3 py-3 text-left transition-colors duration-200 hover:bg-slate-900/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
    >
      <span className="w-5 flex-none text-right text-xs font-semibold tabular-nums text-brand-400">{index}</span>
      <span className="min-w-0 flex-1">
        <span className={`block text-sm font-medium ${INK}`}>{hit.address}</span>
        <span className={`block text-xs ${MUTED}`}>{hit.doc_code}</span>
      </span>
      <ChevronRight
        className={`h-4 w-4 flex-none self-center text-slate-500 transition-transform duration-200 ${open ? 'rotate-90' : ''}`}
      />
    </button>
    {open && (
      <p className="mb-3 ml-8 max-w-prose whitespace-pre-wrap border-l-2 border-slate-800 pl-4 text-[13px] leading-6 text-slate-300">
        {hit.verbatim_text}
      </p>
    )}
  </li>
);

export const LlmAnswerPanel: React.FC = () => {
  const { t, lang } = useI18n();
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
    <div
      className={`h-full overflow-y-auto bg-slate-950 ${INK}`}
     
    >
      <div className="mx-auto max-w-5xl px-6 pt-8">
        <RoadBanner className="max-h-36" />
      </div>
      <div className="mx-auto grid min-h-full max-w-5xl grid-cols-1 gap-x-12 px-6 pb-16 pt-8 md:grid-cols-[13rem_minmax(0,1fr)] md:pt-10">
        <aside className="mb-8 md:mb-0">
          <h1 className="text-[2rem] font-semibold leading-[1.05] tracking-tight md:text-[2.4rem]">
            {t('answer.title').split('\n').map((line, i) => (
              <React.Fragment key={line}>
                {i > 0 && <br />}
                {line}
              </React.Fragment>
            ))}
          </h1>
          <p className={`mt-4 max-w-[15rem] text-sm leading-6 ${MUTED}`}>
            {t('answer.intro')}
          </p>
          {lang === 'en' && <p className={`mt-3 max-w-[15rem] text-xs leading-5 ${MUTED}`}>{t('answer.hintLang')}</p>}
          <label className={`mt-6 flex cursor-pointer items-start gap-2 text-xs leading-5 ${MUTED}`}>
            <input
              type="checkbox"
              checked={agentMode}
              onChange={(e) => setAgentMode(e.target.checked)}
              className="mt-0.5 accent-brand-500"
            />
            <span>{t('answer.deep')}</span>
          </label>
          <label className={`mt-4 block text-xs ${MUTED}`}>
            {t('answer.model')}
            <select
              data-testid="provider-select"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="mt-1 block w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-200 focus:border-brand-500 focus:outline-none"
            >
              {providers.map((p) => (
                <option key={p.name} value={p.name} disabled={!p.installed}>
                  {p.label}
                  {p.installed ? '' : t('answer.notInstalled')}
                </option>
              ))}
            </select>
          </label>
        </aside>

        <main className="min-w-0">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void ask(query);
            }}
            className="flex items-end gap-3 border-b-2 border-slate-100 pb-2 transition-colors duration-200 focus-within:border-brand-500"
          >
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('answer.placeholder')}
              aria-label={t('answer.question')}
              className="min-w-0 flex-1 bg-transparent py-1 text-xl tracking-tight text-slate-100 placeholder-slate-500 focus:outline-none md:text-2xl"
            />
            <button
              type="submit"
              data-testid="ask-button"
              disabled={loading || !query.trim()}
              aria-label={t('answer.ask')}
              className="mb-0.5 flex h-9 w-9 flex-none items-center justify-center rounded-full bg-brand-600 text-white transition duration-200 hover:bg-brand-700 active:scale-95 disabled:cursor-not-allowed disabled:bg-slate-700"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
            </button>
          </form>

          {loading && (
            <div className="mt-8 space-y-3" aria-live="polite">
              <p className={`text-sm ${MUTED}`}>
                {agentMode ? t('answer.loadingDeep') : t('answer.loadingQuick')}
              </p>
              <div className="h-4 w-11/12 animate-pulse rounded bg-slate-800" />
              <div className="h-4 w-3/4 animate-pulse rounded bg-slate-800" />
              <div className="h-4 w-2/3 animate-pulse rounded bg-slate-800" />
            </div>
          )}

          {!result && !loading && !error && (
            <div className="mt-8">
              <SignRow className="mb-6" />
              <p className={`text-xs uppercase tracking-wider ${MUTED}`}>{t('answer.try')}</p>
              <ul className="mt-2">
                {EXAMPLES.map((example) => (
                  <li key={example} className="border-t border-slate-800 first:border-t-0">
                    <button
                      type="button"
                      onClick={() => {
                        setQuery(example);
                        void ask(example);
                      }}
                      className="group flex w-full items-center justify-between gap-4 py-3 text-left text-[15px] text-slate-200 transition-colors duration-200 hover:text-brand-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-500"
                    >
                      {example}
                      <ChevronRight className="h-4 w-4 text-slate-500 transition-transform duration-200 group-hover:translate-x-1" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {error && (
            <div data-testid="answer-error" role="alert" className="mt-8 border-l-2 border-rose-500 pl-4 text-sm leading-6 text-rose-300">
              {t('answer.error')} {error}
            </div>
          )}

          {result && !loading && (
            <div className="mt-8">
              {result.abstained ? (
                <p data-testid="grounding-abstained" className="border-l-2 border-amber-500 pl-4 text-[15px] leading-7 text-amber-200">
                  {t('answer.abstained')}
                </p>
              ) : (
                <>
                  <p
                    data-testid="answer-text"
                    className="max-w-[62ch] whitespace-pre-wrap text-[1.2rem] leading-[1.7] tracking-[-0.005em] text-slate-100 [text-wrap:pretty]"
                  >
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
                            aria-label={t('answer.openSource', { n: number })}
                            onClick={() => {
                              setOpened((c) => new Set(c).add(number));
                              setShowAll(true);
                              document.getElementById(`source-${number}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            }}
                            className="mx-0.5 -translate-y-1 text-[0.7rem] font-semibold tabular-nums text-brand-400 underline decoration-brand-400/30 underline-offset-2 hover:decoration-brand-400"
                          >
                            {number}
                          </button>
                        );
                      })}
                  </p>
                  <p className={`mt-4 text-xs ${MUTED}`}>
                    {grounding?.ok ? (
                      <span data-testid="grounding-ok" className="text-emerald-400">
                        {t('answer.groundingOk')}
                      </span>
                    ) : (
                      <span data-testid="grounding-failed" className="text-rose-400">
                        {t('answer.groundingFail')} {ungrounded.join(' · ')}
                      </span>
                    )}
                    <span data-testid="answer-timing" title={`truy hồi ${result.retrieval_ms} ms · trả lời ${result.answer_ms} ms`}>
                      {' · '}
                      {result.provider}
                    </span>
                    {result.confidence !== 'high' && <span className="text-amber-400"> · {t('answer.confidence')} {result.confidence}</span>}
                  </p>
                </>
              )}

              {visible.length > 0 && (
                <section className="mt-10" aria-label={t('answer.sourcesLabel')}>
                  <h2 className={`text-xs font-medium uppercase tracking-wider ${MUTED}`}>{t('answer.sources')}</h2>
                  <ul className="mt-2">
                    {visible.map(({ hit, index }) => (
                      <SourceRow key={hit.path} index={index} hit={hit} open={opened.has(index)} onToggle={() => toggle(index)} />
                    ))}
                  </ul>
                  {hidden > 0 && !showAll && (
                    <button
                      type="button"
                      onClick={() => setShowAll(true)}
                      className={`mt-2 text-xs underline underline-offset-4 hover:text-brand-400 ${MUTED}`}
                    >
                      {t('answer.more', { n: hidden })}
                    </button>
                  )}
                </section>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
};
