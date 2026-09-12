import { test, expect, APIRequestContext } from '@playwright/test';

const API = 'http://127.0.0.1:8000/api';

async function search(request: APIRequestContext, body: unknown) {
  return request.post(`${API}/search`, {
    data: body as Record<string, unknown>,
    failOnStatusCode: false,
    // Reranking is CPU-bound and serialises, so a request queued behind
    // nineteen others waits for all of them. The config's 20 s action timeout
    // is a UI figure and has nothing to say about that.
    timeout: 120_000,
  });
}

test.describe('Search API contract', () => {
  test('health reports a live database', async ({ request }) => {
    const res = await request.get(`${API}/health`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.status).toBe('OK');
    expect(body.database).toBe('CONNECTED');
  });

  test('a valid query returns a well-formed payload', async ({ request }) => {
    // Reranking puts roughly a second on this, so the default action timeout
    // is not enough once other tests are loading the same CPU.
    test.setTimeout(90_000);
    const res = await search(request, { query: 'xe máy vượt đèn đỏ', limit: 5 });
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.hits.length).toBeGreaterThan(0);
    expect(body.hits.length).toBeLessThanOrEqual(5);
    for (const [i, hit] of body.hits.entries()) {
      expect(hit.rank).toBe(i + 1);
      expect(hit.doc_code).toBeTruthy();
      expect(hit.path).toBeTruthy();
      expect(typeof hit.score).toBe('number');
      expect(Array.isArray(hit.vehicle_classes)).toBe(true);
    }
    // The list must be non-increasing in whatever score decided its order,
    // or the ranking is not a ranking. With reranking on that is the
    // cross-encoder's score; the fused score stays on the payload and is no
    // longer the ordering key, which is exactly the confusion worth asserting
    // away.
    const ordering = body.hits.map((h: { score: number; rerank_score: number | null }) =>
      h.rerank_score ?? h.score
    );
    expect([...ordering].sort((a: number, b: number) => b - a)).toEqual(ordering);
  });

  // A malformed request must be refused, not crashed on.
  const BAD_BODIES: Array<[string, unknown]> = [
    ['missing query', { limit: 5 }],
    ['null query', { query: null }],
    ['numeric query', { query: 123 }],
    ['array query', { query: ['a', 'b'] }],
    ['object query', { query: { a: 1 } }],
    ['empty body', {}],
    ['limit zero', { query: 'xe máy', limit: 0 }],
    ['limit negative', { query: 'xe máy', limit: -5 }],
    ['limit huge', { query: 'xe máy', limit: 100000 }],
    ['limit string', { query: 'xe máy', limit: 'five' }],
    ['limit float', { query: 'xe máy', limit: 2.7 }],
    ['bad date', { query: 'xe máy', violation_date: 'hôm qua' }],
    ['impossible date', { query: 'xe máy', violation_date: '2025-02-30' }],
    ['date as number', { query: 'xe máy', violation_date: 20250101 }],
    ['empty query', { query: '' }],
    ['whitespace query', { query: '   ' }],
  ];

  for (const [name, body] of BAD_BODIES) {
    test(`rejects or handles: ${name}`, async ({ request }) => {
      const res = await search(request, body);
      // 4xx is the right answer; 200 with a sane payload is acceptable where
      // the value is merely unusual. 5xx never is.
      expect(res.status(), `${name} produced a server error`).toBeLessThan(500);
    });
  }

  test('a far-future violation date does not return expired law', async ({ request }) => {
    const res = await search(request, {
      query: 'xe máy vượt đèn đỏ',
      violation_date: '2030-01-01',
      limit: 5,
    });
    expect(res.status()).toBe(200);
    const body = await res.json();
    for (const hit of body.hits) {
      expect(hit.doc_code).not.toBe('100/2019/ND-CP');
    }
  });

  test('a 2024 violation date returns the statute then in force', async ({ request }) => {
    const res = await search(request, {
      query: 'xe máy vượt đèn đỏ',
      violation_date: '2024-06-15',
      limit: 5,
    });
    const body = await res.json();
    const codes = body.hits.map((h: { doc_code: string }) => h.doc_code);
    expect(codes).toContain('100/2019/ND-CP');
    expect(codes).not.toContain('168/2024/ND-CP');
  });

  test('injection strings execute nothing', async ({ request }) => {
    const payloads = [
      "'; DROP TABLE chunks; --",
      "' OR '1'='1",
      'UNION SELECT * FROM documents',
      "1); DELETE FROM documents WHERE ('1'='1",
    ];
    for (const query of payloads) {
      const res = await search(request, { query, limit: 3 });
      expect(res.status(), `${query} produced a server error`).toBeLessThan(500);
    }
    // The corpus must still be there afterwards.
    const after = await search(request, { query: 'xe máy vượt đèn đỏ', limit: 3 });
    expect(after.status()).toBe(200);
    expect((await after.json()).hits.length).toBeGreaterThan(0);
  });

  test('concurrent load is served, slowly, without errors', async ({ request }) => {
    // Reranking is CPU-bound and serialises: measured on this machine the
    // endpoint does 10.3 requests a second without it and 1.95 with, a 5.3x
    // drop. Nothing fails -- every request is answered -- but a test written
    // for the old throughput times out, and pretending otherwise would hide a
    // real capacity limit behind a green suite.
    test.setTimeout(120_000);
    const queries = [
      'xe máy vượt đèn đỏ',
      'ô tô đi vào đường cấm',
      'nồng độ cồn xe máy',
      'tốc độ tối đa cao tốc',
      'xe đạp đi ngược chiều',
    ];
    const started = Date.now();
    const responses = await Promise.all(
      Array.from({ length: 20 }, (_, i) =>
        search(request, { query: queries[i % queries.length], limit: 5 })
      )
    );
    const elapsed = (Date.now() - started) / 1000;
    for (const res of responses) expect(res.status()).toBe(200);

    // A floor, not a target. It catches the reranker becoming an order of
    // magnitude slower without failing on ordinary machine-to-machine variance.
    expect(20 / elapsed, `throughput was ${(20 / elapsed).toFixed(2)} req/s`).toBeGreaterThan(0.5);
  });

  test('unknown routes and wrong methods fail cleanly', async ({ request }) => {
    const missing = await request.get(`${API}/no-such-endpoint`, {
      failOnStatusCode: false,
    });
    expect(missing.status()).toBe(404);

    const wrongMethod = await request.get(`${API}/search`, { failOnStatusCode: false });
    expect([404, 405]).toContain(wrongMethod.status());
  });

  test('a staging document code containing a slash resolves', async ({ request }) => {
    const list = await request.get(`${API}/staging`);
    expect(list.status()).toBe(200);
    const sessions = await list.json();
    expect(sessions.length).toBeGreaterThan(0);
    // Every doc_code here has the form "168/2024/ND-CP", so the path
    // converter is load-bearing on essentially every staging route.
    const code = sessions[0].doc_code as string;
    expect(code).toContain('/');
    const detail = await request.get(`${API}/staging/${code}`, {
      failOnStatusCode: false,
    });
    expect(detail.status()).toBe(200);
  });
});
