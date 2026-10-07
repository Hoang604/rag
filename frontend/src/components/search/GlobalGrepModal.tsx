import React, { useEffect, useRef, useState } from 'react';
import {
  Search,
  X,
} from 'lucide-react';
import { api } from '../../services/api';
import { GrepHit, GrepMatchTier } from '../../types/api';

interface GlobalGrepModalProps {
  isOpen: boolean;
  onClose: () => void;
  docCode: string;
  onSelectHit: (hit: GrepHit) => void;
}

export const GlobalGrepModal: React.FC<GlobalGrepModalProps> = ({
  isOpen,
  onClose,
  docCode,
  onSelectHit,
}) => {
  const [pattern, setPattern] = useState('');
  const [isRegex, setIsRegex] = useState(false);
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [scope, setScope] = useState<'CURRENT' | 'ALL'>('CURRENT');
  const [loading, setLoading] = useState(false);
  const [hits, setHits] = useState<GrepHit[]>([]);
  const [totalMatches, setTotalMatches] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  // Execute Grep
  useEffect(() => {
    if (!isOpen || !pattern.trim()) {
      setHits([]);
      setTotalMatches(0);
      setErrorMsg(null);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      setErrorMsg(null);
      try {
        const resp = await api.grepStaging({
          pattern: pattern.trim(),
          doc_code: scope === 'CURRENT' ? (docCode || null) : null,
          is_regex: isRegex,
          case_sensitive: caseSensitive,
          limit: 30,
        });
        setHits(resp.hits);
        setTotalMatches(resp.total_matches);
      } catch (err: unknown) {
        setErrorMsg(err instanceof Error ? err.message : String(err));
        setHits([]);
        setTotalMatches(0);
      } finally {
        setLoading(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [pattern, isRegex, caseSensitive, scope, isOpen, docCode]);

  if (!isOpen) return null;

  const renderHighlightedSnippet = (snippet: string) => {
    const parts = snippet.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return (
          <span
            key={i}
            className="font-bold text-amber-300 bg-amber-950/50 px-0.5 rounded"
          >
            {part.slice(2, -2)}
          </span>
        );
      }
      return <span key={i}>{part}</span>;
    });
  };

  const getTierBadgeClass = (tier: GrepMatchTier) => {
    switch (tier) {
      case 'BODY':
        return 'bg-emerald-950/70 text-emerald-300 border-emerald-800';
      case 'ARTICLE_HEADING':
      case 'SECTION_HEADING':
      case 'CHAPTER_HEADING':
        return 'bg-blue-950/70 text-blue-300 border-blue-800';
      case 'HEADING_HINT':
      case 'BODY_HINT':
        return 'bg-purple-950/70 text-purple-300 border-purple-800';
      case 'PATH':
        return 'bg-slate-800 text-slate-300 border-slate-700';
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700';
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/75 p-4 sm:p-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden mt-12 animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input Bar */}
        <div className="flex items-center gap-3 border-b border-slate-800 px-4 py-3.5 bg-slate-950/60">
          <Search className="h-5 w-5 text-brand-400 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={pattern}
            onChange={(e) => setPattern(e.target.value)}
            placeholder={
              scope === 'CURRENT'
                ? `Tìm kiếm trong văn bản hiện tại (${docCode || 'Chưa chọn'})...`
                : 'Tìm kiếm trên toàn bộ kho Staging...'
            }
            className="flex-1 bg-transparent text-sm text-slate-100 placeholder-slate-500 focus:outline-none font-mono"
          />

          {/* Scope Selector */}
          <div className="flex items-center rounded-lg border border-slate-800 bg-slate-900 p-0.5 text-[10px] font-semibold shrink-0">
            <button
              type="button"
              onClick={() => setScope('CURRENT')}
              className={`rounded px-2.5 py-1 transition ${
                scope === 'CURRENT'
                  ? 'bg-brand-600 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Văn bản này
            </button>
            <button
              type="button"
              onClick={() => setScope('ALL')}
              className={`rounded px-2.5 py-1 transition ${
                scope === 'ALL'
                  ? 'bg-brand-600 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Toàn bộ Staging
            </button>
          </div>

          {/* Quick Options */}
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              onClick={() => setIsRegex(!isRegex)}
              className={`rounded px-2 py-1 font-mono text-[10px] font-bold border transition ${
                isRegex
                  ? 'border-brand-500 bg-brand-950 text-brand-300'
                  : 'border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200'
              }`}
              title="Bật/Tắt Regular Expression"
            >
              .*
            </button>
            <button
              type="button"
              onClick={() => setCaseSensitive(!caseSensitive)}
              className={`rounded px-2 py-1 font-mono text-[10px] font-bold border transition ${
                caseSensitive
                  ? 'border-brand-500 bg-brand-950 text-brand-300'
                  : 'border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200'
              }`}
              title="Phân biệt chữ hoa/thường"
            >
              Aa
            </button>
          </div>

          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Results Area */}
        <div className="max-h-[60vh] overflow-y-auto p-3 space-y-2">
          {loading && (
            <div className="py-6 text-center text-xs text-slate-400 animate-pulse">
              Đang quét văn cảnh quy phạm staging...
            </div>
          )}

          {errorMsg && (
            <div className="rounded-lg bg-rose-950/80 p-3 text-xs text-rose-300 border border-rose-800">
              Lỗi cú pháp Regex / Grep: {errorMsg}
            </div>
          )}

          {!loading && !errorMsg && pattern.trim() && hits.length === 0 && (
            <div className="py-8 text-center text-xs text-slate-400">
              Không tìm thấy quy phạm nào khớp với từ khóa tìm kiếm.
            </div>
          )}

          {hits.map((hit) => (
            <div
              key={`${hit.doc_code}:${hit.path}`}
              onClick={() => {
                onSelectHit(hit);
                onClose();
              }}
              className="group flex flex-col gap-1.5 rounded-xl border border-slate-800 bg-slate-950/60 p-3 hover:border-brand-500/60 hover:bg-slate-900/90 cursor-pointer transition"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[9px] font-mono font-bold text-slate-400 shrink-0">
                    #{hit.rank}
                  </span>
                  {hit.doc_code && (
                    <span className="rounded bg-brand-950/60 border border-brand-800/60 px-1.5 py-0.5 text-[9px] font-mono font-bold text-brand-300 shrink-0">
                      {hit.doc_code}
                    </span>
                  )}
                  <span className="text-xs font-semibold text-slate-200 truncate">
                    {hit.address}
                  </span>
                  <span className="font-mono text-[10px] text-slate-500 truncate hidden sm:inline">
                    {hit.path}
                  </span>
                  <span className="rounded bg-sky-950/60 border border-sky-800/60 px-1.5 py-0.5 text-[9px] font-mono font-bold text-sky-300 shrink-0">
                    Dòng {hit.start_line}{hit.end_line !== hit.start_line ? `-${hit.end_line}` : ''}
                  </span>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <span className="rounded bg-amber-950/40 border border-amber-800/40 px-1.5 py-0.5 text-[10px] font-mono font-bold text-amber-300">
                    Score {(hit.score * 100).toFixed(0)}%
                  </span>
                  {hit.matched_in.map((tier) => (
                    <span
                      key={tier}
                      className={`rounded border px-1.5 py-0.5 text-[8px] font-mono font-bold uppercase ${getTierBadgeClass(
                        tier
                      )}`}
                    >
                      {tier}
                    </span>
                  ))}
                </div>
              </div>

              <div className="font-mono text-xs text-slate-300 line-clamp-3 leading-relaxed bg-slate-950/40 p-2.5 rounded border border-slate-850">
                {renderHighlightedSnippet(hit.snippet)}
              </div>
            </div>
          ))}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between border-t border-slate-800 px-4 py-2.5 bg-slate-950/80 text-[11px] text-slate-400 font-mono">
          <span>
            {hits.length} / {totalMatches} kết quả khớp ({scope === 'CURRENT' ? docCode || 'Chưa chọn' : 'Toàn bộ kho Staging'})
          </span>
          <span>Bấm ESC để đóng (hoặc Ctrl+K để bật/tắt)</span>
        </div>
      </div>
    </div>
  );
};
