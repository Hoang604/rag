import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ChevronDown, Loader2, Search } from 'lucide-react';
import { api } from '../../services/api';
import { useI18n } from '../../i18n/I18nContext';
import { RoadBanner, SignRow } from '../art/TrafficArt';
import { AmendmentNotice } from '../common/AmendmentNotice';
import { CorpusDocument, SearchHit, SearchResponse } from '../../types/api';

const EXAMPLE_QUERIES = [
  'Xe máy vượt đèn đỏ phạt bao nhiêu?',
  'Nồng độ cồn chưa vượt quá 0,25 miligam với xe máy',
  'Tốc độ tối đa trên đường cao tốc là bao nhiêu?',
  'Chở 3 người trên xe máy bị phạt thế nào?',
];

export const DryRunSearchSimulator: React.FC = () => {
  const { t } = useI18n();
  const [query, setQuery] = useState('');
  const [violationDate, setViolationDate] = useState('');
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [docs, setDocs] = useState<CorpusDocument[]>([]);
  const [scope, setScope] = useState<string[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [deep, setDeep] = useState(true);

  useEffect(() => {
    api
      .documents()
      .then(setDocs)
      .catch(() => setDocs([]));
  }, []);

  const runSearch = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setLoading(true);
      setError(null);
      try {
        setResult(
          await api.search({
            query: trimmed,
            limit: 5,
            violation_date: violationDate || null,
            rerank: false,
            doc_codes: scope,
            deep,
          })
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : t('search.errorTitle'));
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    [violationDate, scope, deep, t]
  );

  const hits: SearchHit[] = result?.hits ?? [];
  const confidence = result?.confidence;
  const note =
    confidence === 'none'
      ? { title: t('search.confNoneTitle'), body: t('search.confNoneBody'), tone: 'border-rose-500 text-rose-300' }
      : confidence === 'low'
        ? { title: t('search.confLowTitle'), body: t('search.confLowBody'), tone: 'border-amber-500 text-amber-300' }
        : null;

  const filterCount = scope.length + (violationDate ? 1 : 0);

  return (
    <div className="h-full overflow-y-auto bg-slate-950">
      <div className="mx-auto max-w-3xl px-6 pb-16 pt-8">
        <RoadBanner className="mb-8 max-h-36" />
        <h1 className="text-[2rem] font-semibold leading-tight tracking-tight text-slate-100">{t('search.title')}</h1>
        <p className="mt-3 max-w-prose text-sm leading-6 text-slate-400">{t('search.intro')}</p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void runSearch(query);
          }}
          className="mt-8 flex items-end gap-3 border-b-2 border-slate-100 pb-2 transition-colors duration-200 focus-within:border-brand-500"
        >
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('search.placeholder')}
            aria-label={t('search.placeholder')}
            className="min-w-0 flex-1 bg-transparent py-1 text-xl tracking-tight text-slate-100 placeholder-slate-500 focus:outline-none md:text-2xl"
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            aria-label={t('search.button')}
            className="mb-0.5 flex h-9 flex-none items-center gap-1.5 rounded-full bg-brand-600 px-4 text-sm font-medium text-white transition duration-200 hover:bg-brand-700 active:scale-95 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            <span className="hidden sm:inline">{t('search.button')}</span>
          </button>
        </form>

        <label className="mt-4 flex cursor-pointer items-start gap-2 text-xs leading-5 text-slate-400">
          <input
            type="checkbox"
            data-testid="deep-toggle"
            checked={deep}
            onChange={(e) => setDeep(e.target.checked)}
            className="mt-0.5 accent-brand-500"
          />
          <span>{t('search.deep')}</span>
        </label>

        <button
          type="button"
          data-testid="scope-toggle"
          onClick={() => setFiltersOpen((open) => !open)}
          aria-expanded={filtersOpen}
          className="mt-3 flex items-center gap-1.5 text-xs text-slate-400 transition-colors duration-200 hover:text-slate-100"
        >
          <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-200 ${filtersOpen ? 'rotate-180' : ''}`} />
          <span data-testid="scope-summary">
            {t('search.filters')}
            {filterCount > 0 ? ` (${filterCount})` : ''}
          </span>
        </button>

        {filtersOpen && (
          <div className="mt-3 space-y-5 border-l-2 border-slate-800 pl-4">
            <label className="block text-xs text-slate-400">
              {t('search.date')}
              <input
                type="date"
                value={violationDate}
                onChange={(e) => setViolationDate(e.target.value)}
                className="mt-1 block rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100 focus:border-brand-500 focus:outline-none"
              />
              <span className="mt-1 block max-w-prose text-[11px] leading-5 text-slate-500">{t('search.dateHelp')}</span>
            </label>

            <div>
              <div className="flex items-center gap-3 text-xs text-slate-400">
                <span>{scope.length === 0 ? t('search.scopeAll') : t('search.scopeSome', { n: scope.length })}</span>
                {scope.length > 0 && (
                  <button
                    type="button"
                    data-testid="scope-clear"
                    onClick={() => setScope([])}
                    className="underline underline-offset-4 hover:text-slate-100"
                  >
                    {t('search.scopeClear')}
                  </button>
                )}
              </div>
              <div data-testid="scope-list" className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
                {docs.map((doc) => (
                  <label key={doc.doc_code} className="flex cursor-pointer items-start gap-2 py-1 text-xs text-slate-300">
                    <input
                      type="checkbox"
                      data-testid={`scope-${doc.doc_code}`}
                      checked={scope.includes(doc.doc_code)}
                      onChange={(e) =>
                        setScope((current) =>
                          e.target.checked ? [...current, doc.doc_code] : current.filter((code) => code !== doc.doc_code)
                        )
                      }
                      className="mt-0.5 accent-brand-500"
                    />
                    <span className="min-w-0">
                      <span className="block truncate font-medium text-slate-100">{doc.title}</span>
                      <span className="text-slate-500">
                        {doc.doc_code} · {t('search.items', { n: doc.chunk_count })}
                        {!doc.in_force && <span className="text-amber-400"> · {t('search.expired')}</span>}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}

        {!result && !loading && !error && (
          <div className="mt-8">
            <SignRow className="mb-6" />
            <p className="text-xs uppercase tracking-wider text-slate-400">{t('search.try')}</p>
            <ul className="mt-2">
              {EXAMPLE_QUERIES.map((example) => (
                <li key={example} className="border-t border-slate-800 first:border-t-0">
                  <button
                    type="button"
                    onClick={() => {
                      setQuery(example);
                      void runSearch(example);
                    }}
                    className="w-full py-3 text-left text-[15px] text-slate-200 transition-colors duration-200 hover:text-brand-400"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {loading && (
          <div className="mt-8 space-y-3" aria-live="polite">
            <p className="text-sm text-slate-400">{deep ? t('search.loadingDeep') : t('search.loading')}</p>
            <div className="h-4 w-11/12 animate-pulse rounded bg-slate-800" />
            <div className="h-4 w-3/4 animate-pulse rounded bg-slate-800" />
          </div>
        )}

        {error && (
          <div role="alert" className="mt-8 flex items-start gap-2 border-l-2 border-rose-500 pl-4 text-sm leading-6 text-rose-300">
            <AlertTriangle className="mt-1 h-4 w-4 flex-none" />
            <div>
              <p className="font-medium">{t('search.errorTitle')}</p>
              <p className="opacity-80">{error}</p>
            </div>
          </div>
        )}

        {result && !loading && (
          <section className="mt-10" aria-label={t('search.results')}>
            <h2
              data-testid="result-count"
              data-count={hits.length}
              className="text-xs font-medium uppercase tracking-wider text-slate-400"
            >
              {t('search.results')} · {t('search.count', { n: hits.length })}
            </h2>

            {note && (
              <div data-testid="confidence-warning" data-confidence={confidence} className={`mt-4 border-l-2 pl-4 text-sm leading-6 ${note.tone}`}>
                <p className="font-medium">{note.title}</p>
                <p className="opacity-80">{note.body}</p>
              </div>
            )}

            {hits.length === 0 ? (
              <p className="mt-4 text-sm text-slate-400">{t('search.none')}</p>
            ) : (
              <ol className="mt-2">
                {hits.map((hit) => (
                  <li key={hit.path} data-testid="search-hit" className="border-t border-slate-800 py-5 first:border-t-0">
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span data-testid="hit-address" className="text-[15px] font-semibold text-slate-100">
                        {hit.address}
                      </span>
                      <span data-testid="hit-doc-code" className="text-xs text-slate-400">
                        {hit.doc_code}
                      </span>
                      {hit.is_table && (
                        <span data-testid="hit-table-badge" title={hit.table_summary ?? undefined} className="text-xs text-brand-400">
                          {t('search.table')}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 max-w-[68ch] whitespace-pre-wrap text-[15px] leading-7 text-slate-200">{hit.verbatim_text}</p>
                    <AmendmentNotice notes={hit.amended_by ?? []} />
                    <p className="mt-2 text-xs text-slate-500">
                      {t('search.effective', { d: hit.effective_date })}
                      {hit.expiration_date ? ` · ${t('search.expiredOn', { d: hit.expiration_date })}` : ''}
                    </p>
                    {hit.contextualized_text && hit.contextualized_text !== hit.verbatim_text && (
                      <details className="mt-2 text-xs text-slate-400">
                        <summary className="cursor-pointer select-none hover:text-slate-100">{t('search.context')}</summary>
                        <p className="mt-2 max-w-[68ch] whitespace-pre-wrap leading-6 text-slate-300">{hit.contextualized_text}</p>
                      </details>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </section>
        )}
      </div>
    </div>
  );
};
