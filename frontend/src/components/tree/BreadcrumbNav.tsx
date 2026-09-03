import React from 'react';
import { ChevronRight, Home } from 'lucide-react';
import { parseLTreePath } from '../../utils/ltree';

interface BreadcrumbNavProps {
  path?: string;
  onSelectPath?: (path: string) => void;
}

export const BreadcrumbNav: React.FC<BreadcrumbNavProps> = ({
  path,
  onSelectPath,
}) => {
  if (!path) {
    return (
      <div className="flex items-center gap-2 text-xs text-slate-400 px-3 py-1.5 bg-slate-900/60 rounded-md border border-slate-800">
        <Home className="w-3.5 h-3.5 text-slate-500" />
        <span>Toàn bộ văn bản</span>
      </div>
    );
  }

  const segments = parseLTreePath(path);

  return (
    <nav className="flex items-center gap-1.5 text-xs text-slate-300 px-3 py-1.5 bg-slate-900/80 rounded-md border border-slate-800 overflow-x-auto">
      <button
        onClick={() => onSelectPath?.('')}
        className="flex items-center gap-1 text-slate-400 hover:text-white transition"
      >
        <Home className="w-3.5 h-3.5" />
        <span>Gốc</span>
      </button>

      {segments.map((seg, idx) => (
        <React.Fragment key={seg.fullPath}>
          <ChevronRight className="w-3.5 h-3.5 text-slate-600 shrink-0" />
          <button
            onClick={() => onSelectPath?.(seg.fullPath)}
            className={`whitespace-nowrap transition px-1.5 py-0.5 rounded ${
              idx === segments.length - 1
                ? 'font-bold text-brand-400 bg-brand-950/60 border border-brand-800/40'
                : 'text-slate-300 hover:text-white hover:bg-slate-800'
            }`}
          >
            {seg.label}
          </button>
        </React.Fragment>
      ))}
    </nav>
  );
};
