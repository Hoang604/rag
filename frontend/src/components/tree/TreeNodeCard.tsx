import React, { memo, useEffect, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Edit3,
  FileText,
  Plus,
  Trash2,
} from 'lucide-react';
import { DocumentTreeNode } from '../../types/tree';
import { getNodeTypeColor } from '../../utils/ltree';
import { naturalLegalCompare } from '../../utils/sorting';

interface TreeNodeCardProps {
  node: DocumentTreeNode;
  onEdit: (node: DocumentTreeNode) => void;
  onDelete: (path: string) => void;
  onAddChild?: (parentPath: string) => void;
  onSelect?: (node: DocumentTreeNode) => void;
  isSelected?: boolean;
  depth?: number;
  globalExpandSignal?: number; // timestamp to trigger collapse/expand all
  globalExpandLevel?: 'ALL' | 'COLLAPSE' | 'ARTICLE' | 'CLAUSE' | null;
}

export const TreeNodeCard: React.FC<TreeNodeCardProps> = memo(
  ({
    node,
    onEdit,
    onDelete,
    onAddChild,
    onSelect,
    isSelected = false,
    depth = 0,
    globalExpandSignal,
    globalExpandLevel,
  }) => {
    // Default: Collapse all child branches (Articles, Clauses, Points) to ensure instant 120 FPS rendering on 100+ page documents
    const [collapsed, setCollapsed] = useState(() => depth > 0);
    const [showFullText, setShowFullText] = useState(false);

    // Synchronize with global expand / collapse level signals
    useEffect(() => {
      if (globalExpandLevel === 'COLLAPSE') {
        setCollapsed(depth > 0);
      } else if (globalExpandLevel === 'ALL') {
        setCollapsed(false);
      } else if (globalExpandLevel === 'ARTICLE') {
        // Expand Document and Chapter, collapse Articles and below
        if (node.node_type === 'DOCUMENT' || node.node_type === 'CHAPTER' || node.node_type === 'SECTION') {
          setCollapsed(false);
        } else {
          setCollapsed(true);
        }
      } else if (globalExpandLevel === 'CLAUSE') {
        if (node.node_type === 'POINT') {
          setCollapsed(true);
        } else {
          setCollapsed(false);
        }
      }
    }, [globalExpandSignal, globalExpandLevel, depth, node.node_type]);

    const colors = getNodeTypeColor(node.node_type);
    const hasChildren = node.children && node.children.length > 0;

    return (
      <div
        className={`relative my-2 transition-all duration-150 will-change-transform ${
          depth > 0 ? 'ml-5 border-l-2 border-slate-800/80 pl-3.5' : ''
        }`}
        style={{ contentVisibility: 'auto', containIntrinsicSize: '90px' }}
      >
        {/* Node Main Card */}
        <div
          onClick={() => onSelect?.(node)}
          className={`group relative rounded-xl border p-3.5 shadow-sm transition-all duration-150 ${colors.bg} ${
            isSelected
              ? 'border-brand-500 ring-2 ring-brand-500/30 shadow-brand-950/50'
              : `${colors.border} hover:border-slate-500 hover:shadow-md`
          }`}
        >
          {/* Header bar */}
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              {hasChildren && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setCollapsed(!collapsed);
                  }}
                  className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition"
                  title={collapsed ? 'Mở rộng mục này' : 'Thu gọn mục này'}
                >
                  {collapsed ? (
                    <ChevronRight className="h-4 w-4 text-brand-400" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                </button>
              )}

              <span
                className={`rounded-md border px-2 py-0.5 text-xs font-semibold uppercase tracking-wider ${colors.badge}`}
              >
                {node.node_type}
              </span>

              <span className="font-semibold text-xs sm:text-sm text-slate-100">
                {node.label}
              </span>

              <span className="rounded bg-slate-900/80 px-2 py-0.5 font-mono text-[10px] sm:text-[11px] text-slate-400 border border-slate-800">
                {node.path}
              </span>

              {hasChildren && collapsed && (
                <span className="rounded bg-brand-950/60 px-1.5 py-0.2 text-[10px] font-mono text-brand-400 border border-brand-800/60">
                  +{node.children.length} mục con
                </span>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-1 opacity-80 group-hover:opacity-100 transition-opacity">
              {onAddChild && (
                <button
                  type="button"
                  title="Thêm mục con"
                  onClick={(e) => {
                    e.stopPropagation();
                    onAddChild(node.path);
                  }}
                  className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-brand-400"
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
              )}
              <button
                type="button"
                title="Chỉnh sửa điều khoản này"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(node);
                }}
                className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-brand-300"
              >
                <Edit3 className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                title="Xóa điều khoản này"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(node.path);
                }}
                className="rounded p-1.5 text-slate-400 hover:bg-rose-950 hover:text-rose-400"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {/* Lead sentence if present */}
          {node.lead_sentence && (
            <div className="mt-2 text-xs italic text-slate-300">
              {node.lead_sentence}
            </div>
          )}

          {/* Verbatim text display */}
          {node.verbatim_text && (
            <div className="mt-2.5 rounded-lg bg-slate-950/70 p-3 border border-slate-800/80 text-xs font-mono text-slate-200 leading-relaxed whitespace-pre-wrap">
              {showFullText || node.verbatim_text.length <= 260
                ? node.verbatim_text
                : `${node.verbatim_text.substring(0, 260)}...`}
              {node.verbatim_text.length > 260 && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setShowFullText(!showFullText);
                  }}
                  className="ml-2 text-brand-400 hover:underline font-sans font-medium text-[11px]"
                >
                  {showFullText ? 'Thu gọn' : 'Xem toàn bộ'}
                </button>
              )}
            </div>
          )}

          {/* Contextualized text accordion for clauses/points */}
          {node.contextualized_text && node.contextualized_text !== node.verbatim_text && (
            <div className="mt-2">
              <details className="text-[11px] text-slate-400 group/ctx">
                <summary className="cursor-pointer hover:text-slate-200 transition select-none flex items-center gap-1 font-medium text-brand-400/90">
                  <FileText className="h-3 w-3" />
                  <span>Văn cảnh CPHC tổng hợp</span>
                </summary>
                <div className="mt-1.5 rounded bg-slate-900/90 p-2.5 border border-slate-800 text-slate-300 font-mono whitespace-pre-wrap leading-relaxed">
                  {node.contextualized_text}
                </div>
              </details>
            </div>
          )}

          {/* Metadata Badges */}
          {node.metadata && Object.keys(node.metadata).length > 0 && (
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
              {Object.entries(node.metadata).map(([k, v]) => (
                <span
                  key={k}
                  className="inline-flex items-center gap-1 rounded bg-slate-900 px-2 py-0.5 text-[10px] font-mono text-slate-300 border border-slate-800"
                >
                  <span className="text-slate-500">{k}:</span>
                  <span>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Render children lazily only when expanded */}
        {!collapsed && hasChildren && (
          <div className="space-y-1 mt-1">
            {[...node.children]
              .sort((a, b) => naturalLegalCompare(a.path, b.path))
              .map((child) => (
                <TreeNodeCard
                  key={child.path}
                  node={child}
                  onEdit={onEdit}
                  onDelete={onDelete}
                  onAddChild={onAddChild}
                  onSelect={onSelect}
                  isSelected={isSelected}
                  depth={depth + 1}
                  globalExpandSignal={globalExpandSignal}
                  globalExpandLevel={globalExpandLevel}
                />
              ))}
          </div>
        )}
      </div>
    );
  }
);

TreeNodeCard.displayName = 'TreeNodeCard';
