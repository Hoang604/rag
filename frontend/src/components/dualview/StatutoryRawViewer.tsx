import React, { useEffect, useRef } from 'react';

interface StatutoryRawViewerProps {
  rawText: string;
  searchTerm?: string;
  highlightLineIndex?: number | null;
  onLineClick?: (lineNumber: number, text: string) => void;
}

export const StatutoryRawViewer: React.FC<StatutoryRawViewerProps> = ({
  rawText,
  searchTerm = '',
  highlightLineIndex = null,
  onLineClick,
}) => {
  const lineRefs = useRef<Map<number, HTMLTableRowElement>>(new Map());
  const lines = rawText.split('\n');

  // Auto-scroll to highlighted line when active chunk changes
  useEffect(() => {
    if (highlightLineIndex !== null && highlightLineIndex !== undefined) {
      const el = lineRefs.current.get(highlightLineIndex);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [highlightLineIndex]);

  return (
    <div className="h-full overflow-y-auto bg-slate-950 p-4 font-mono text-xs text-slate-300 leading-relaxed border border-slate-800 rounded-lg">
      <table className="w-full border-collapse">
        <tbody>
          {lines.map((line, idx) => {
            const lineNum = idx + 1;
            const isSearched =
              searchTerm &&
              line.toLowerCase().includes(searchTerm.toLowerCase());
            const isTargeted = highlightLineIndex === idx;

            return (
              <tr
                key={idx}
                ref={(el) => {
                  if (el) lineRefs.current.set(idx, el);
                  else lineRefs.current.delete(idx);
                }}
                onClick={() => onLineClick?.(lineNum, line)}
                style={{ contentVisibility: 'auto', containIntrinsicSize: '24px' }}
                className={`cursor-pointer transition-all duration-150 ${
                  isTargeted
                    ? 'bg-brand-950/80 text-brand-200 font-semibold ring-1 ring-brand-500/50 shadow-inner'
                    : isSearched
                    ? 'bg-amber-950/40 text-amber-200 font-semibold'
                    : 'hover:bg-slate-900/60'
                }`}
              >
                <td className="w-12 select-none pr-3 text-right text-[11px] text-slate-600 align-top border-r border-slate-800/80">
                  {lineNum}
                </td>
                <td className="whitespace-pre-wrap break-words pl-3 py-0.5">
                  {line || ' '}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
