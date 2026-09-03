import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import {
  BatchPatchPayload,
  CreateEdgePayload,
  DeleteEdgePayload,
} from '../types/api';
import {
  StagingChunk,
  StagingDocumentSession,
  StagingSessionSummary,
  StagingStatus,
} from '../types/staging';
import { DocumentTreeResponse } from '../types/tree';

export function useStagingSession(initialDocCode?: string) {
  const [sessions, setSessions] = useState<StagingSessionSummary[]>([]);
  const [activeDocCode, setActiveDocCode] = useState<string | undefined>(
    initialDocCode
  );
  const [session, setSession] = useState<StagingDocumentSession | null>(null);
  const [treeData, setTreeData] = useState<DocumentTreeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [treeLoading, setTreeLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load list of all sessions
  const refreshSessions = useCallback(async () => {
    try {
      const list = await api.listSessions();
      setSessions(list);
      if (!activeDocCode && list.length > 0) {
        setActiveDocCode(list[0].doc_code);
      }
      return list;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Lỗi tải danh sách văn bản';
      setError(msg);
      return [];
    }
  }, [activeDocCode]);

  // Load active session detail and tree hierarchy
  const loadActiveSession = useCallback(async (docCode: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getSession(docCode);
      setSession(data);
      return data;
    } catch (err) {
      const msg = err instanceof Error ? err.message : `Lỗi tải văn bản ${docCode}`;
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTreeHierarchy = useCallback(async (docCode: string) => {
    setTreeLoading(true);
    try {
      const tree = await api.getDocumentTree(docCode);
      setTreeData(tree);
      return tree;
    } catch (err) {
      console.error('Failed to load tree:', err);
      return null;
    } finally {
      setTreeLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  // Sync when activeDocCode changes
  useEffect(() => {
    if (activeDocCode) {
      void loadActiveSession(activeDocCode);
      void loadTreeHierarchy(activeDocCode);
    } else {
      setSession(null);
      setTreeData(null);
    }
  }, [activeDocCode, loadActiveSession, loadTreeHierarchy]);

  // Mutation helper: patch chunks in-place
  const patchChunks = useCallback(
    async (updatedChunks: StagingChunk[], removedPaths: string[] = []) => {
      if (!activeDocCode) return false;
      try {
        const payload: BatchPatchPayload = {
          updated_chunks: updatedChunks,
          removed_paths: removedPaths,
        };
        await api.patchChunks(activeDocCode, payload);
        await loadActiveSession(activeDocCode);
        await loadTreeHierarchy(activeDocCode);
        await refreshSessions();
        return true;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Lỗi cập nhật điều khoản';
        setError(msg);
        return false;
      }
    },
    [activeDocCode, loadActiveSession, loadTreeHierarchy, refreshSessions]
  );

  // Mutation helper: add edge
  const addEdge = useCallback(
    async (edge: CreateEdgePayload) => {
      if (!activeDocCode) return false;
      try {
        await api.addEdges(activeDocCode, [edge]);
        await loadActiveSession(activeDocCode);
        await refreshSessions();
        return true;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Lỗi thêm quan hệ pháp lý';
        setError(msg);
        return false;
      }
    },
    [activeDocCode, loadActiveSession, refreshSessions]
  );

  // Mutation helper: delete edge
  const deleteEdge = useCallback(
    async (payload: DeleteEdgePayload) => {
      if (!activeDocCode) return false;
      try {
        await api.deleteEdge(activeDocCode, payload);
        await loadActiveSession(activeDocCode);
        await refreshSessions();
        return true;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Lỗi xóa quan hệ pháp lý';
        setError(msg);
        return false;
      }
    },
    [activeDocCode, loadActiveSession, refreshSessions]
  );

  // Mutation helper: update status
  const updateStatus = useCallback(
    async (status: StagingStatus, actor = 'HUMAN:reviewer', description = '') => {
      if (!activeDocCode) return false;
      try {
        await api.updateSessionStatus(activeDocCode, status, actor, description);
        await loadActiveSession(activeDocCode);
        await refreshSessions();
        return true;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Lỗi chuyển trạng thái';
        setError(msg);
        return false;
      }
    },
    [activeDocCode, loadActiveSession, refreshSessions]
  );

  return {
    sessions,
    activeDocCode,
    setActiveDocCode,
    session,
    treeData,
    loading,
    treeLoading,
    error,
    setError,
    refreshSessions,
    loadActiveSession,
    loadTreeHierarchy,
    patchChunks,
    addEdge,
    deleteEdge,
    updateStatus,
  };
}
