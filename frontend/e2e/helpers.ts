import { Page, expect } from '@playwright/test';

/** Console and network errors seen since the page was opened. */
export interface PageErrors {
  console: string[];
  pageErrors: string[];
  failedRequests: string[];
}

/** Starts collecting everything the browser complains about.
 *
 * A React app can render a plausible-looking page while throwing underneath,
 * so an assertion on the DOM alone would pass a broken build.
 */
export function watchErrors(page: Page): PageErrors {
  const errors: PageErrors = { console: [], pageErrors: [], failedRequests: [] };
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.console.push(msg.text());
  });
  page.on('pageerror', (err) => errors.pageErrors.push(err.message));
  page.on('response', (res) => {
    if (res.status() >= 500) errors.failedRequests.push(`${res.status()} ${res.url()}`);
  });
  return errors;
}

/** Opens the app and switches to the retrieval tab, waiting for it to be live. */
export async function openSearchTab(page: Page): Promise<void> {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: /Thử Nghiệm Truy Xuất/ }).click();
  await expect(page.getByPlaceholder(/Nhập tình huống vi phạm/)).toBeVisible();
}

/** Normalises rendered text to NFC.
 *
 * The corpus stores decomposed Vietnamese, so "Điều" arrives from the API with
 * a combining mark and does not compare equal to the composed literal in a
 * test file, even though the two render identically.
 */
const norm = (text: string): string => text.normalize('NFC').trim();

/** Types a query, submits it, and waits for the result header to settle.
 *
 * Returns the number of provisions rendered. Waiting on the spinner to clear
 * rather than on a fixed delay keeps the slow first query from flaking.
 */
export async function runSearch(page: Page, query: string): Promise<number> {
  const box = page.getByPlaceholder(/Nhập tình huống vi phạm/);
  await box.fill(query);
  await page.getByRole('button', { name: 'Tra cứu' }).click();
  await expect(page.getByText(/Đang truy hồi trên toàn corpus/)).toBeHidden({
    timeout: 45_000,
  });
  const heading = page.getByTestId('result-count');
  await expect(heading).toBeVisible();
  return Number(await heading.getAttribute('data-count'));
}

/** Returns the document codes of the rendered results, in rank order.
 *
 * Scoped to the result cards: the header carries a document picker whose
 * hidden <option> elements match the same text.
 */
export async function hitDocCodes(page: Page): Promise<string[]> {
  return (await page.getByTestId('hit-doc-code').allTextContents()).map(norm);
}

/** Returns the addresses ("Điều 7 Khoản 7 Điểm c") of the rendered results. */
export async function hitAddresses(page: Page): Promise<string[]> {
  return (await page.getByTestId('hit-address').allTextContents()).map(norm);
}

/** Reads the facet chips the UI resolved for the last query. */
export async function readFacets(
  page: Page
): Promise<{ vehicle: string; role: string; date: string }> {
  const read = async (id: string) => norm((await page.getByTestId(id).textContent()) ?? '');
  return {
    vehicle: await read('facet-vehicle'),
    role: await read('facet-role'),
    date: await read('facet-date'),
  };
}

/** Asserts nothing was thrown or 500ed while the block ran. */
export function assertClean(errors: PageErrors, context: string): void {
  expect(errors.pageErrors, `${context}: uncaught exception`).toEqual([]);
  expect(errors.failedRequests, `${context}: server error`).toEqual([]);
}
