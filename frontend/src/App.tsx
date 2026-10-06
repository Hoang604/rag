import React, { useState } from 'react';
import { Header } from './components/layout/Header';
import { NavigationTabs, TabId } from './components/layout/NavigationTabs';
import { LegalStudioContainer } from './components/studio/LegalStudioContainer';
import { AuditHistoryDiff } from './components/diff/AuditHistoryDiff';
import { SurgicalEditorDrawer } from './components/editor/SurgicalEditorDrawer';
import { AddChunkModal } from './components/editor/AddChunkModal';
import { DeleteConfirmModal } from './components/editor/DeleteConfirmModal';
import { VisualGraphInspector } from './components/graph/VisualGraphInspector';
import { DualViewContainer } from './components/dualview/DualViewContainer';
import { PreFlightChecklist } from './components/checklist/PreFlightChecklist';
import { PromotionModal } from './components/checklist/PromotionModal';
import { CreateSessionModal } from './components/upload/CreateSessionModal';
import { LlmAnswerPanel } from './components/answer/LlmAnswerPanel';
import { DryRunSearchSimulator } from './components/search/DryRunSearchSimulator';
import { ToastProvider, useToast } from './components/toast/ToastContext';
import { useStagingSession } from './hooks/useStagingSession';
import { usePreFlightCheck } from './hooks/usePreFlightCheck';
import { DocumentTreeNode } from './types/tree';
import { StagingChunk } from './types/staging';
import { api } from './services/api';

const AppContent: React.FC = () => {
  const { success, error } = useToast();
  const [mode, setMode] = useState<'lookup' | 'review'>('lookup');
  const [activeTab, setActiveTab] = useState<TabId>('studio');

  // Staging session hook
  const {
    sessions,
    activeDocCode,
    setActiveDocCode,
    session,
    treeData,
    refreshSessions,
    patchChunks,
    finalizeChunks,
    addEdge,
    deleteEdge,
  } = useStagingSession();

  // Pre-flight check hook
  const {
    validationResult,
    validating,
    runValidation,
  } = usePreFlightCheck(activeDocCode);

  // Modal / Drawer state
  const [selectedNode, setSelectedNode] = useState<DocumentTreeNode | null>(null);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [addParentPath, setAddParentPath] = useState('');
  const [deleteTargetChunk, setDeleteTargetChunk] = useState<string | null>(null);
  const [isPromotionOpen, setIsPromotionOpen] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  // Chunk handlers
  const handleToggleFinalizeChunk = async (node: DocumentTreeNode) => {
    const collectLeafPaths = (n: DocumentTreeNode): string[] => {
      if (!n.children || n.children.length === 0) return [n.path];
      return n.children.flatMap(collectLeafPaths);
    };
    const targetPaths = collectLeafPaths(node);
    const isCurrentlyReviewed = node.review_status === 'REVIEWED';
    try {
      if (isCurrentlyReviewed) {
        const chunksToReopen =
          session?.chunks
            ?.filter((c) => targetPaths.includes(c.path))
            ?.map((c) => ({ ...c, review_status: 'PENDING' as const })) || [];
        const ok = await patchChunks(chunksToReopen, []);
        if (ok) {
          success(
            'Đã mở lại điều khoản',
            `Đã chuyển ${targetPaths.length} mục sang Chờ rà soát.`
          );
        }
      } else {
        const ok = await finalizeChunks(targetPaths);
        if (ok) {
          success(
            'Rà soát điều khoản thành công',
            `Đã cập nhật trạng thái đã rà soát cho ${targetPaths.length} mục.`
          );
        }
      }
    } catch (err) {
      error('Lỗi cập nhật trạng thái', err instanceof Error ? err.message : 'Lỗi hệ thống');
    }
  };

  const handleEditChunk = (node: DocumentTreeNode) => {
    setSelectedNode(node);
    setIsEditorOpen(true);
  };

  const handleDeleteChunkConfirm = async () => {
    if (!deleteTargetChunk) return;
    try {
      await patchChunks([], [deleteTargetChunk]);
      success('Đã xóa điều khoản', `Đã loại bỏ ${deleteTargetChunk} khỏi Staging.`);
    } catch (err) {
      error('Lỗi xóa điều khoản', err instanceof Error ? err.message : 'Lỗi hệ thống');
    } finally {
      setDeleteTargetChunk(null);
    }
  };

  const handleAddChildChunk = (parentPath: string) => {
    setAddParentPath(parentPath);
    setIsAddModalOpen(true);
  };

  const handleSaveChunk = async (chunk: StagingChunk) => {
    const ok = await patchChunks([chunk], []);
    if (ok) {
      success('Lưu thành công', `Đã cập nhật điều khoản ${chunk.path}.`);
    }
    return ok;
  };

  const handleAddChunkDirect = async (chunk: StagingChunk) => {
    const ok = await patchChunks([chunk], []);
    if (ok) {
      success('Thêm thành công', `Đã tạo điều khoản mới ${chunk.path}.`);
    }
    return ok;
  };

  const blockingCount =
    validationResult?.issues?.filter((i) => i.blocking)?.length || 0;

  const switchBar = (light: boolean) => (
    <div
      className={`flex flex-none items-center justify-between gap-3 px-5 text-sm ${
        light ? 'bg-[#0f4c4f] py-2.5 text-white' : 'border-b border-slate-800 bg-slate-900 py-2 text-slate-300'
      }`}
    >
      <span className="flex items-center gap-2.5 font-semibold">
        {light && (
          <svg viewBox="0 0 24 24" className="h-6 w-6 flex-none" aria-hidden>
            <rect x="1" y="1" width="22" height="22" rx="5" fill="#f6f1e7" />
            <path d="M12 4 L19 18 H5 Z" fill="none" stroke="#0f4c4f" strokeWidth="2" strokeLinejoin="round" />
            <path d="M12 9 V14" stroke="#e9a820" strokeWidth="2" strokeLinecap="round" />
          </svg>
        )}
        <span className={light ? 'text-base' : 'text-slate-100'}>{light ? 'Tra cứu luật giao thông' : 'Quản lý dữ liệu luật'}</span>
      </span>
      <button
        type="button"
        onClick={() => setMode(light ? 'review' : 'lookup')}
        title={light ? 'Thêm, chỉnh sửa và kiểm tra các văn bản luật có trong hệ thống' : undefined}
        className={light ? 'text-white/80 underline underline-offset-4 hover:text-white' : 'underline underline-offset-4 hover:text-white'}
      >
        {light ? 'Quản lý dữ liệu luật' : '← Về trang tra cứu'}
      </button>
    </div>
  );

  if (mode === 'lookup') {
    return (
      <div className="flex h-screen w-screen flex-col overflow-hidden bg-[#faf8f4]">
        {switchBar(true)}
        <main className="min-h-0 flex-1">
          <LlmAnswerPanel />
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-slate-950 text-slate-100">
      {switchBar(false)}
      {/* Top Global Header */}
      <Header
        sessions={sessions}
        showDocPicker={activeTab !== 'search'}
        activeDocCode={activeDocCode}
        session={session}
        onSelectDoc={setActiveDocCode}
        onRefresh={refreshSessions}
        onOpenPromotionModal={() => setIsPromotionOpen(true)}
        onOpenCreateSessionModal={() => setIsCreateOpen(true)}
        onQuickValidate={runValidation}
        validating={validating}
        blockingIssuesCount={blockingCount}
      />

      {/* Primary Navigation Tabs */}
      <NavigationTabs
        activeTab={activeTab}
        onTabChange={setActiveTab}
        chunksCount={session?.chunks?.length || 0}
        edgesCount={session?.edges?.length || 0}
        diffsCount={session?.mutation_history?.length || 0}
        issuesCount={blockingCount}
      />

      {/* Main Subsystem Body */}
      <main className="relative flex-1 overflow-hidden">
        {/* Retrieval reads the promoted corpus, so it is the one tab that has
            nothing to do with the staging buffer. Gating it behind a staged
            document left anyone with an empty buffer unable to ask a question
            at all. */}
        {activeTab === 'search' ? (
          <DryRunSearchSimulator session={session} onEditChunk={handleEditChunk} />
        ) : !session ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center max-w-sm p-6">
              <p className="text-sm text-slate-400 mb-4">
                Chưa có văn bản nào được chọn hoặc Vùng đệm Staging đang trống.
              </p>
              <button
                type="button"
                onClick={() => setIsCreateOpen(true)}
                className="rounded-xl bg-gradient-to-r from-brand-600 to-brand-700 px-5 py-2.5 text-xs font-semibold text-white shadow-lg shadow-brand-950 hover:from-brand-500 hover:to-brand-600 transition"
              >
                + Tải Lên &amp; Bóc Tách Văn Bản Mới
              </button>
            </div>
          </div>
        ) : (
          <>
            {activeTab === 'studio' && (
              <LegalStudioContainer
                session={session}
                treeData={treeData}
                onEditChunk={handleEditChunk}
                onDeleteChunk={(path) => setDeleteTargetChunk(path)}
                onAddChildChunk={handleAddChildChunk}
                onAddEdge={addEdge}
                onToggleFinalizeChunk={handleToggleFinalizeChunk}
              />
            )}

            {activeTab === 'dualview' && (
              <DualViewContainer
                session={session}
                onEditChunk={handleEditChunk}
              />
            )}

            {activeTab === 'graph' && (
              <VisualGraphInspector
                session={session}
                onAddEdge={addEdge}
                onDeleteEdge={deleteEdge}
                onSelectNode={(_path) => {
                  setActiveTab('studio');
                }}
              />
            )}

            {activeTab === 'diff' && <AuditHistoryDiff session={session} />}

            {activeTab === 'checklist' && (
              <PreFlightChecklist
                session={session}
                validationResult={validationResult}
                validating={validating}
                onReValidate={runValidation}
                onOpenPromotionModal={() => setIsPromotionOpen(true)}
              />
            )}

          </>
        )}
      </main>

      {/* Modals and Drawers */}
      <SurgicalEditorDrawer
        isOpen={isEditorOpen}
        onClose={() => setIsEditorOpen(false)}
        selectedNode={selectedNode}
        onSaveChunk={handleSaveChunk}
      />

      <AddChunkModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onAdd={handleAddChunkDirect}
        parentPath={addParentPath}
      />

      <DeleteConfirmModal
        isOpen={deleteTargetChunk !== null}
        onClose={() => setDeleteTargetChunk(null)}
        onConfirm={handleDeleteChunkConfirm}
        path={deleteTargetChunk || ''}
      />

      {session && (
        <PromotionModal
          isOpen={isPromotionOpen}
          onClose={() => setIsPromotionOpen(false)}
          session={session}
          onPromote={async (payload) => {
            const res = await api.promoteSession(session.doc_code, payload);
            await refreshSessions();
            return res;
          }}
        />
      )}

      {/* Dedicated Upload & Ingestion Modal */}
      <CreateSessionModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSuccess={async (newCode) => {
          await refreshSessions();
          setActiveDocCode(newCode);
        }}
      />
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
};

export default App;
