import React from 'react';
import {
  ChevronDownSquare,
  ChevronUpSquare,
  ListTree,
  Maximize2,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

interface CanvasToolbarProps {
  scale: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onResetView: () => void;
  onFitScreen: () => void;
  onExpandAll?: () => void;
  onCollapseAll?: () => void;
  onExpandArticles?: () => void;
}

export const CanvasToolbar: React.FC<CanvasToolbarProps> = ({
  scale,
  onZoomIn,
  onZoomOut,
  onResetView,
  onFitScreen,
  onExpandAll,
  onCollapseAll,
  onExpandArticles,
}) => {
  const percentage = Math.round(scale * 100);

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-900/95 p-1.5 shadow-xl backdrop-blur-md">
      <button
        type="button"
        onClick={onZoomIn}
        title="Phóng to (+)"
        className="rounded-lg p-1.5 text-slate-300 hover:bg-slate-800 hover:text-white transition"
      >
        <ZoomIn className="h-4 w-4" />
      </button>

      <span className="min-w-[44px] text-center font-mono text-xs font-semibold text-slate-300">
        {percentage}%
      </span>

      <button
        type="button"
        onClick={onZoomOut}
        title="Thu nhỏ (-)"
        className="rounded-lg p-1.5 text-slate-300 hover:bg-slate-800 hover:text-white transition"
      >
        <ZoomOut className="h-4 w-4" />
      </button>

      <div className="mx-1 h-4 w-px bg-slate-700" />

      <button
        type="button"
        onClick={onResetView}
        title="Khôi phục 100%"
        className="rounded-lg p-1.5 text-slate-300 hover:bg-slate-800 hover:text-white transition"
      >
        <RotateCcw className="h-4 w-4" />
      </button>

      <button
        type="button"
        onClick={onFitScreen}
        title="Vừa khung hình"
        className="rounded-lg p-1.5 text-slate-300 hover:bg-slate-800 hover:text-white transition"
      >
        <Maximize2 className="h-4 w-4" />
      </button>

      {/* Quick Level Expand/Collapse Controllers */}
      <div className="mx-1 h-4 w-px bg-slate-700" />

      {onCollapseAll && (
        <button
          type="button"
          onClick={onCollapseAll}
          title="Thu gọn tất cả (Mặc định - Siêu mượt)"
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold text-slate-300 hover:bg-slate-800 hover:text-brand-300 transition"
        >
          <ChevronUpSquare className="h-3.5 w-3.5 text-slate-400" />
          <span className="hidden sm:inline">Thu gọn hết</span>
        </button>
      )}

      {onExpandArticles && (
        <button
          type="button"
          onClick={onExpandArticles}
          title="Mở rộng đến cấp Điều"
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold text-slate-300 hover:bg-slate-800 hover:text-brand-300 transition"
        >
          <ListTree className="h-3.5 w-3.5 text-brand-400" />
          <span className="hidden sm:inline">Mở cấp Điều</span>
        </button>
      )}

      {onExpandAll && (
        <button
          type="button"
          onClick={onExpandAll}
          title="Mở rộng toàn bộ cây"
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold text-slate-300 hover:bg-slate-800 hover:text-brand-300 transition"
        >
          <ChevronDownSquare className="h-3.5 w-3.5 text-slate-400" />
          <span className="hidden sm:inline">Mở hết</span>
        </button>
      )}
    </div>
  );
};
