import React, { useMemo, useState } from 'react';
import { useCanvasTransform } from '../../hooks/useCanvasTransform';
import { DocumentTreeNode, DocumentTreeResponse } from '../../types/tree';
import { BreadcrumbNav } from './BreadcrumbNav';
import { CanvasToolbar } from './CanvasToolbar';
import { SearchFilterBar } from './SearchFilterBar';
import { TreeNodeCard } from './TreeNodeCard';

interface TreeHierarchyCanvasProps {
  treeData: DocumentTreeResponse | null;
  loading?: boolean;
  onEditChunk: (node: DocumentTreeNode) => void;
  onDeleteChunk: (path: string) => void;
  onAddChildChunk: (parentPath: string) => void;
}

export const TreeHierarchyCanvas: React.FC<TreeHierarchyCanvasProps> = ({
  treeData,
  loading = false,
  onEditChunk,
  onDeleteChunk,
  onAddChildChunk,
}) => {
  const {
    containerRef,
    transform,
    zoomIn,
    zoomOut,
    resetView,
    fitScreen,
    onMouseDown,
    onMouseMove,
    onMouseUp,
  } = useCanvasTransform();

  const [searchTerm, setSearchTerm] = useState('');
  const [pathFilter, setPathFilter] = useState('');
  const [selectedNodeType, setSelectedNodeType] = useState('');
  const [selectedPath, setSelectedPath] = useState<string>('');

  // Global expand / collapse state
  const [expandSignal, setExpandSignal] = useState(0);
  const [expandLevel, setExpandLevel] = useState<'ALL' | 'COLLAPSE' | 'ARTICLE' | 'CLAUSE' | null>(null);

  const handleExpandAll = () => {
    setExpandLevel('ALL');
    setExpandSignal(Date.now());
  };

  const handleCollapseAll = () => {
    setExpandLevel('COLLAPSE');
    setExpandSignal(Date.now());
  };

  const handleExpandArticles = () => {
    setExpandLevel('ARTICLE');
    setExpandSignal(Date.now());
  };

  // Filter nodes according to search criteria
  const filteredTree = useMemo(() => {
    if (!treeData?.root) return null;
    if (!searchTerm && !pathFilter && !selectedNodeType) return treeData.root;

    function filterNode(node: DocumentTreeNode): DocumentTreeNode | null {
      const matchSearch =
        !searchTerm ||
        node.label.toLowerCase().includes(searchTerm.toLowerCase()) ||
        node.verbatim_text.toLowerCase().includes(searchTerm.toLowerCase()) ||
        node.contextualized_text
          .toLowerCase()
          .includes(searchTerm.toLowerCase());

      const matchPath =
        !pathFilter ||
        node.path.toLowerCase().includes(pathFilter.toLowerCase().replace(/\*/g, ''));

      const matchType =
        !selectedNodeType ||
        node.node_type.toUpperCase() === selectedNodeType.toUpperCase();

      const filteredChildren: DocumentTreeNode[] = [];
      if (node.children) {
        for (const child of node.children) {
          const res = filterNode(child);
          if (res) filteredChildren.push(res);
        }
      }

      if ((matchSearch && matchPath && matchType) || filteredChildren.length > 0) {
        return {
          ...node,
          children: filteredChildren,
        };
      }

      return null;
    }

    return filterNode(treeData.root);
  }, [treeData, searchTerm, pathFilter, selectedNodeType]);

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden bg-slate-950">
      {/* Top Floating Bar: Search, Filter, and Breadcrumbs */}
      <div className="absolute left-6 right-6 top-4 z-20 flex flex-col gap-2 pointer-events-auto">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <BreadcrumbNav
            path={selectedPath}
            onSelectPath={(p) => {
              setSelectedPath(p);
              setPathFilter(p);
            }}
          />
          <CanvasToolbar
            scale={transform.scale}
            onZoomIn={zoomIn}
            onZoomOut={zoomOut}
            onResetView={resetView}
            onFitScreen={fitScreen}
            onExpandAll={handleExpandAll}
            onCollapseAll={handleCollapseAll}
            onExpandArticles={handleExpandArticles}
          />
        </div>

        <SearchFilterBar
          searchTerm={searchTerm}
          onSearchChange={setSearchTerm}
          pathFilter={pathFilter}
          onPathFilterChange={setPathFilter}
          selectedNodeType={selectedNodeType}
          onNodeTypeSelect={setSelectedNodeType}
        />
      </div>

      {/* Infinite Canvas Container */}
      <div
        ref={containerRef}
        className="relative flex-1 cursor-grab active:cursor-grabbing overflow-hidden touch-none"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        {/* Subtle grid pattern */}
        <div
          className="absolute inset-0 pointer-events-none opacity-20"
          style={{
            backgroundImage: `radial-gradient(circle, #475569 1px, transparent 1px)`,
            backgroundSize: `${24 * transform.scale}px ${24 * transform.scale}px`,
            backgroundPosition: `${transform.x}px ${transform.y}px`,
          }}
        />

        {loading ? (
          <div className="flex h-full items-center justify-center">
            <div className="flex items-center gap-3 rounded-lg bg-slate-900/90 px-5 py-3 border border-slate-800 shadow-xl">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
              <span className="text-sm font-medium text-slate-300">
                Đang dựng cây phân cấp điều khoản...
              </span>
            </div>
          </div>
        ) : !filteredTree ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center text-slate-500">
              <p className="text-sm">Không tìm thấy điều khoản nào khớp bộ lọc</p>
            </div>
          </div>
        ) : (
          <div
            className="absolute left-0 top-0 transition-transform duration-75 ease-out will-change-transform"
            style={{
              transform: `translate3d(${transform.x}px, ${transform.y}px, 0) scale(${transform.scale})`,
              transformOrigin: '0 0',
              width: '920px',
              paddingTop: '130px',
              paddingBottom: '200px',
            }}
          >
            <TreeNodeCard
              node={filteredTree}
              onEdit={onEditChunk}
              onDelete={onDeleteChunk}
              onAddChild={onAddChildChunk}
              onSelect={(node) => setSelectedPath(node.path)}
              isSelected={selectedPath === filteredTree.path}
              globalExpandSignal={expandSignal}
              globalExpandLevel={expandLevel}
            />
          </div>
        )}
      </div>
    </div>
  );
};
