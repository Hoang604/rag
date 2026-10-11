import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronDown, Loader2, Play, Save, Trash2 } from 'lucide-react';
import { api } from '../../services/api';
import { useI18n } from '../../i18n/I18nContext';
import { MessageKey } from '../../i18n/messages';
import {
  EvalCase,
  EvalCaseRun,
  EvalFoundIn,
  EvalOutcome,
  EvalSplit,
  EvalSplitSummary,
  ProvisionMatch,
} from '../../types/api';

const PAGE = 50;
const GROUPS: EvalFoundIn[] = ['both', 'semantic_only', 'verbatim_only', 'missed'];

const TONE: Record<EvalFoundIn, string> = {
  both: 'text-emerald-400',
  semantic_only: 'text-sky-400',
  verbatim_only: 'text-amber-400',
  missed: 'text-rose-400',
};

const answers = (path: string, expected: string[]) =>
  expected.some((e) => path === e || path.startsWith(`${e}.`));

const inputClass =
  'mt-1 block w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100 focus:border-brand-500 focus:outline-none';

const SummaryTable: React.FC<{ summaries: EvalSplitSummary[] }> = ({ summaries }) => {
  const { t } = useI18n();
  return (
    <table className="mt-6 w-full max-w-2xl text-left text-sm tabular-nums" data-testid="eval-summary">
      <thead className="text-xs uppercase tracking-wider text-slate-400">
        <tr>
          <th className="py-1 pr-4 font-medium" />
          {GROUPS.map((g) => (
            <th key={g} className={`py-1 pr-4 font-medium ${TONE[g]}`}>
              {t(`eval.${g}` as MessageKey)}
            </th>
          ))}
          <th className="py-1 pr-4 font-medium">{t('eval.found')}</th>
          <th className="py-1 font-medium">{t('eval.total')}</th>
        </tr>
      </thead>
      <tbody>
        {summaries.map((s) => {
          const found = s.total - s.missed;
          return (
            <tr key={s.split} className="border-t border-slate-800">
              <td className="py-1.5 pr-4 font-medium text-slate-200">{s.split}</td>
              {GROUPS.map((g) => (
                <td key={g} className="py-1.5 pr-4 text-slate-200">
                  {s[g]}
                </td>
              ))}
              <td className="py-1.5 pr-4 text-slate-100">
                {s.total ? `${((100 * found) / s.total).toFixed(1)}%` : '—'}
              </td>
              <td className="py-1.5 text-slate-400">{s.total}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
};

const HitList: React.FC<{ title: string; tone: string; hits: ProvisionMatch[]; expected: string[] }> = ({
  title,
  tone,
  hits,
  expected,
}) => {
  const { t } = useI18n();
  if (hits.length === 0) return null;
  return (
    <div className="mt-4">
      <h4 className={`text-xs font-medium uppercase tracking-wider ${tone}`}>
        {title} · {hits.length}
      </h4>
      <ol className="mt-1">
        {hits.map((hit) => {
          const ok = answers(hit.path, expected);
          return (
            <li key={hit.path} className={`border-t border-slate-800 py-2 ${ok ? 'bg-emerald-500/10' : ''}`}>
              <div className="flex flex-wrap items-baseline gap-x-3 text-xs">
                <span className="font-semibold text-slate-100">{hit.address}</span>
                <span className="text-slate-400">{hit.doc_code}</span>
                <span className="font-mono text-slate-500">{hit.path}</span>
                {ok && <span className="text-emerald-400">{t('eval.matched')}</span>}
              </div>
              <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-slate-500">{hit.context}</p>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-200">{hit.text}</p>
            </li>
          );
        })}
      </ol>
    </div>
  );
};

interface CaseEditorProps {
  item: EvalCase;
  onSaved: (item: EvalCase) => void;
  onDeleted: (id: string) => void;
  onRun: (run: EvalCaseRun) => void;
  run: EvalCaseRun | null;
}

const CaseEditor: React.FC<CaseEditorProps> = ({ item, onSaved, onDeleted, onRun, run }) => {
  const { t } = useI18n();
  const [draft, setDraft] = useState(item);
  const [docCodes, setDocCodes] = useState(item.doc_codes.join(', '));
  const [expected, setExpected] = useState(item.expected.join('\n'));
  const [busy, setBusy] = useState<'save' | 'run' | 'delete' | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const build = (): EvalCase => ({
    ...draft,
    temporal_violation_date: draft.temporal_violation_date || null,
    note: draft.note || null,
    doc_codes: docCodes
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    expected: expected
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean),
  });

  const act = async (kind: 'save' | 'run' | 'delete') => {
    setBusy(kind);
    setMessage(null);
    try {
      if (kind === 'save') {
        onSaved(await api.saveEvalCase(build()));
        setMessage(t('eval.saved'));
      } else if (kind === 'run') {
        const saved = await api.saveEvalCase(build());
        onSaved(saved);
        onRun(await api.runEvalCase(saved.id));
      } else if (window.confirm(t('eval.confirmDelete', { id: item.id }))) {
        await api.deleteEvalCase(item.id);
        onDeleted(item.id);
      }
    } catch (err) {
      setMessage(`${t('eval.error')} ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(null);
    }
  };

  const field = (key: 'question' | 'query' | 'pattern', label: MessageKey) => (
    <label className="block text-xs text-slate-400">
      {t(label)}
      <input
        value={draft[key]}
        onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
        className={inputClass}
      />
    </label>
  );

  return (
    <div className="space-y-3 border-l-2 border-slate-800 py-3 pl-4">
      {field('question', 'eval.question')}
      {field('query', 'eval.query')}
      {field('pattern', 'eval.pattern')}
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <input
            type="checkbox"
            checked={draft.is_regex}
            onChange={(e) => setDraft({ ...draft, is_regex: e.target.checked })}
            className="accent-brand-500"
          />
          {t('eval.isRegex')}
        </label>
        <label className="block text-xs text-slate-400">
          {t('eval.date')}
          <input
            type="date"
            value={draft.temporal_violation_date ?? ''}
            onChange={(e) => setDraft({ ...draft, temporal_violation_date: e.target.value || null })}
            className={inputClass}
          />
        </label>
        <label className="block text-xs text-slate-400">
          split
          <select
            value={draft.split}
            onChange={(e) => setDraft({ ...draft, split: e.target.value as EvalSplit })}
            className={inputClass}
          >
            <option value="dev">dev</option>
            <option value="holdout">holdout</option>
          </select>
        </label>
      </div>
      <label className="block text-xs text-slate-400">
        {t('eval.docCodes')}
        <input value={docCodes} onChange={(e) => setDocCodes(e.target.value)} className={inputClass} />
      </label>
      <label className="block text-xs text-slate-400">
        {t('eval.expected')}
        <textarea
          value={expected}
          onChange={(e) => setExpected(e.target.value)}
          rows={Math.max(2, expected.split('\n').length)}
          className={`${inputClass} font-mono`}
        />
      </label>
      <label className="block text-xs text-slate-400">
        {t('eval.note')}
        <input
          value={draft.note ?? ''}
          onChange={(e) => setDraft({ ...draft, note: e.target.value || null })}
          className={inputClass}
        />
      </label>
      <div className="flex flex-wrap items-center gap-2">
        {(
          [
            ['run', Play, 'eval.runOne'],
            ['save', Save, 'eval.save'],
            ['delete', Trash2, 'eval.delete'],
          ] as const
        ).map(([kind, Icon, label]) => (
          <button
            key={kind}
            type="button"
            disabled={busy !== null}
            onClick={() => act(kind)}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-50 ${
              kind === 'run'
                ? 'bg-brand-600 text-white hover:bg-brand-700'
                : kind === 'delete'
                  ? 'text-rose-400 hover:text-rose-300'
                  : 'border border-slate-700 text-slate-200 hover:border-slate-500'
            }`}
          >
            {busy === kind ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Icon className="h-3.5 w-3.5" />}
            {t(label)}
          </button>
        ))}
        {message && <span className="text-xs text-slate-400">{message}</span>}
      </div>
      {run && (
        <div data-testid="eval-case-result">
          <p className={`text-sm font-medium ${TONE[run.outcome.found_in]}`}>
            {t(`eval.${run.outcome.found_in}` as MessageKey)}
            {run.outcome.position ? ` · #${run.outcome.position}` : ''}
            <span className="ml-3 text-xs font-normal text-slate-400">
              {t('eval.verbatimTotal', { n: run.result.verbatim_total })}
            </span>
          </p>
          <HitList title={t('eval.both')} tone={TONE.both} hits={run.result.both} expected={build().expected} />
          <HitList
            title={t('eval.semantic_only')}
            tone={TONE.semantic_only}
            hits={run.result.semantic_only}
            expected={build().expected}
          />
          <HitList
            title={t('eval.verbatim_only')}
            tone={TONE.verbatim_only}
            hits={run.result.verbatim_only}
            expected={build().expected}
          />
        </div>
      )}
    </div>
  );
};

export const EvalPanel: React.FC = () => {
  const { t } = useI18n();
  const [cases, setCases] = useState<EvalCase[]>([]);
  const [outcomes, setOutcomes] = useState<Record<string, EvalOutcome>>({});
  const [summaries, setSummaries] = useState<EvalSplitSummary[] | null>(null);
  const [runs, setRuns] = useState<Record<string, EvalCaseRun>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [split, setSplit] = useState<EvalSplit | 'all'>('all');
  const [outcome, setOutcome] = useState<EvalFoundIn | 'notRun' | 'all'>('all');
  const [shown, setShown] = useState(PAGE);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .evalCases()
      .then(setCases)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const runAll = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const result = await api.runEval();
      setOutcomes(Object.fromEntries(result.outcomes.map((o) => [o.id, o])));
      setSummaries(result.summaries);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, []);

  const visible = useMemo(() => {
    const needle = text.trim().toLowerCase();
    return cases.filter((c) => {
      if (split !== 'all' && c.split !== split) return false;
      const o = outcomes[c.id];
      if (outcome === 'notRun' && o) return false;
      if (outcome !== 'all' && outcome !== 'notRun' && o?.found_in !== outcome) return false;
      if (!needle) return true;
      return [c.id, c.question, c.query, c.pattern, ...c.expected].some((v) => v.toLowerCase().includes(needle));
    });
  }, [cases, outcomes, text, split, outcome]);

  return (
    <div className="h-full overflow-y-auto bg-slate-950">
      <div className="mx-auto max-w-5xl px-6 pb-16 pt-8">
        <h1 className="text-[2rem] font-semibold leading-tight tracking-tight text-slate-100">{t('eval.title')}</h1>
        <p className="mt-3 max-w-prose text-sm leading-6 text-slate-400">{t('eval.intro')}</p>

        <div className="mt-6 flex flex-wrap items-end gap-3">
          <button
            type="button"
            data-testid="eval-run-all"
            onClick={runAll}
            disabled={running || cases.length === 0}
            className="flex h-9 items-center gap-1.5 rounded-full bg-brand-600 px-4 text-sm font-medium text-white transition duration-200 hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-700"
          >
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {running ? t('eval.running') : t('eval.runAll')}
          </button>
          <input
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setShown(PAGE);
            }}
            placeholder={t('eval.filterText')}
            className="min-w-[16rem] flex-1 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-100 placeholder-slate-500 focus:border-brand-500 focus:outline-none"
          />
          <select
            value={split}
            onChange={(e) => setSplit(e.target.value as EvalSplit | 'all')}
            className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100"
          >
            <option value="all">{t('eval.allSplits')}</option>
            <option value="dev">dev</option>
            <option value="holdout">holdout</option>
          </select>
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value as EvalFoundIn | 'notRun' | 'all')}
            className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm text-slate-100"
          >
            <option value="all">{t('eval.allOutcomes')}</option>
            {GROUPS.map((g) => (
              <option key={g} value={g}>
                {t(`eval.${g}` as MessageKey)}
              </option>
            ))}
            <option value="notRun">{t('eval.notRun')}</option>
          </select>
        </div>

        {error && (
          <p role="alert" className="mt-4 border-l-2 border-rose-500 pl-4 text-sm text-rose-300">
            {t('eval.error')} {error}
          </p>
        )}
        {summaries && <SummaryTable summaries={summaries} />}

        <p className="mt-6 text-xs text-slate-400">{t('eval.shown', { n: visible.length, total: cases.length })}</p>
        <ul className="mt-2">
          {visible.slice(0, shown).map((c) => {
            const o = outcomes[c.id];
            const isOpen = open === c.id;
            return (
              <li key={c.id} className="border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setOpen(isOpen ? null : c.id)}
                  aria-expanded={isOpen}
                  className="flex w-full items-baseline gap-3 py-2.5 text-left"
                >
                  <span className="w-12 flex-none font-mono text-xs text-slate-500">{c.id}</span>
                  <span className="w-14 flex-none text-xs text-slate-500">{c.split}</span>
                  <span className="min-w-0 flex-1 text-sm text-slate-200">
                    {c.question}
                    <span className="mt-0.5 block truncate text-xs text-slate-500">
                      {c.query} · <span className="font-mono">{c.pattern}</span>
                    </span>
                  </span>
                  <span className={`w-28 flex-none text-right text-xs ${o ? TONE[o.found_in] : 'text-slate-500'}`}>
                    {o ? t(`eval.${o.found_in}` as MessageKey) : t('eval.notRun')}
                  </span>
                  {c.note && <span className="flex-none text-xs text-amber-400" title={c.note}>!</span>}
                  <ChevronDown
                    className={`h-4 w-4 flex-none text-slate-500 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
                  />
                </button>
                {isOpen && (
                  <CaseEditor
                    key={c.id}
                    item={c}
                    run={runs[c.id] ?? null}
                    onSaved={(saved) => setCases((all) => all.map((x) => (x.id === saved.id ? saved : x)))}
                    onDeleted={(id) => {
                      setCases((all) => all.filter((x) => x.id !== id));
                      setOpen(null);
                    }}
                    onRun={(run) => {
                      setRuns((all) => ({ ...all, [c.id]: run }));
                      setOutcomes((all) => ({ ...all, [c.id]: run.outcome }));
                    }}
                  />
                )}
              </li>
            );
          })}
        </ul>
        {visible.length > shown && (
          <button
            type="button"
            onClick={() => setShown((n) => n + PAGE)}
            className="mt-3 text-xs text-slate-400 underline underline-offset-4 hover:text-brand-400"
          >
            {t('eval.more', { n: Math.min(PAGE, visible.length - shown) })}
          </button>
        )}
      </div>
    </div>
  );
};
