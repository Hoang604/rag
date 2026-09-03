import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import { PreFlightValidationResponse } from '../types/preflight';

export function usePreFlightCheck(docCode?: string) {
  const [validationResult, setValidationResult] =
    useState<PreFlightValidationResponse | null>(null);
  const [validating, setValidating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const runValidation = useCallback(async () => {
    if (!docCode) {
      setValidationResult(null);
      return null;
    }
    setValidating(true);
    setValidationError(null);
    try {
      const res = await api.validateSession(docCode);
      setValidationResult(res);
      return res;
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : 'Lỗi chạy thẩm định tính toàn vẹn';
      setValidationError(msg);
      return null;
    } finally {
      setValidating(false);
    }
  }, [docCode]);

  useEffect(() => {
    if (docCode) {
      void runValidation();
    }
  }, [docCode, runValidation]);

  return {
    validationResult,
    validating,
    validationError,
    runValidation,
  };
}
