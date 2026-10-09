import {
  AnswerPayload,
  AnswerProvider,
  AnswerResponse,
  CorpusDocument,
  HealthResponse,
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

    return response.json() as Promise<T>;
  }

  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/health');
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
}

export const api = new ApiClient();
