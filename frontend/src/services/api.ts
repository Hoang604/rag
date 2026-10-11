import {
  AnswerPayload,
  AnswerProvider,
  AnswerResponse,
  CorpusDocument,
  EvalCase,
  EvalCaseRun,
  EvalRun,
  SearchPayload,
  SearchResponse,
} from '../types/api';

const API_BASE = '/api';

class ApiClient {
  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      let errorMessage = `API Error ${response.status}: ${response.statusText}`;
      try {
        const errorJson = (await response.json()) as {
          error?: { message?: string; code?: number };
          detail?: string | { message?: string };
        };
        if (errorJson.error?.message) {
          errorMessage = errorJson.error.message;
        } else if (typeof errorJson.detail === 'string') {
          errorMessage = errorJson.detail;
        } else if (typeof errorJson.detail === 'object' && errorJson.detail?.message) {
          errorMessage = errorJson.detail.message;
        }
      } catch {
        errorMessage = `API Error ${response.status}: ${response.statusText}`;
      }
      throw new Error(errorMessage);
    }

    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  async search(payload: SearchPayload): Promise<SearchResponse> {
    return this.request<SearchResponse>('/search', {
      method: 'POST',
      body: JSON.stringify({ limit: 5, violation_date: null, ...payload }),
    });
  }

  async documents(): Promise<CorpusDocument[]> {
    return this.request<CorpusDocument[]>('/documents');
  }

  async answerProviders(): Promise<AnswerProvider[]> {
    return this.request<AnswerProvider[]>('/answer/providers');
  }

  async answer(payload: AnswerPayload): Promise<AnswerResponse> {
    return this.request<AnswerResponse>('/answer', {
      method: 'POST',
      body: JSON.stringify({ limit: 5, violation_date: null, ...payload }),
    });
  }

  async evalCases(): Promise<EvalCase[]> {
    return this.request<EvalCase[]>('/eval/cases');
  }

  async saveEvalCase(item: EvalCase): Promise<EvalCase> {
    return this.request<EvalCase>(`/eval/cases/${item.id}`, { method: 'PUT', body: JSON.stringify(item) });
  }

  async deleteEvalCase(id: string): Promise<void> {
    return this.request<void>(`/eval/cases/${id}`, { method: 'DELETE' });
  }

  async runEvalCase(id: string): Promise<EvalCaseRun> {
    return this.request<EvalCaseRun>(`/eval/cases/${id}/run`, { method: 'POST' });
  }

  async runEval(): Promise<EvalRun> {
    return this.request<EvalRun>('/eval/run', { method: 'POST' });
  }
}

export const api = new ApiClient();
