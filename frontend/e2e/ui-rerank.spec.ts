import { test, expect } from '@playwright/test';
import { assertClean, hitAddresses, openSearchTab, runSearch, watchErrors } from './helpers';

// Reranking is a second model in the request path and it ships on, so what is
// worth asserting is that it can be turned off, that it does not break the
// page, and that it cannot turn a query matching nothing into a confident one.
test.describe('Cross-encoder reranking through the interface', () => {
  const toggle = (page: import('@playwright/test').Page) =>
    page.getByTestId('rerank-toggle');

  test('the toggle exists and starts on, matching the server', async ({ page }) => {
    // Reranking ships on. A toggle that started off would show the reviewer a
    // ranking no caller actually receives.
    await openSearchTab(page);
    await expect(toggle(page)).toBeVisible();
    await expect(toggle(page)).toBeChecked();
  });

  test('reranking keeps the red-light answer first', async ({ page }) => {
    // The provision people ask about most, and the one that exposed the
    // cross-encoder's blind spot: the statute says "không chấp hành hiệu lệnh
    // của đèn tín hiệu", the question says "vượt đèn đỏ". Reranking the raw
    // question moved this to rank 3; reranking the expansion does not.
    const errors = watchErrors(page);
    await openSearchTab(page);
    const count = await runSearch(page, 'Xe máy vượt đèn đỏ phạt bao nhiêu?');
    expect(count).toBeGreaterThan(0);
    expect((await hitAddresses(page))[0]).toMatch(/^Điều 7\b/);
    assertClean(errors, 'rerank red light');
  });

  test('a question survives being asked both ways', async ({ page }) => {
    const errors = watchErrors(page);
    await openSearchTab(page);

    await runSearch(page, 'Ô tô vượt đèn đỏ phạt bao nhiêu?');
    const reranked = await hitAddresses(page);
    expect(reranked.length).toBeGreaterThan(0);

    await toggle(page).uncheck();
    await runSearch(page, 'Ô tô vượt đèn đỏ phạt bao nhiêu?');
    const plain = await hitAddresses(page);
    expect(plain.length).toBeGreaterThan(0);

    assertClean(errors, 'both ways');
  });

  test('reranking does not break hostile input', async ({ page }) => {
    const errors = watchErrors(page);
    await openSearchTab(page);
    for (const query of ["'; DROP TABLE chunks; --", 'asdkjhaskdjh', '((((xe máy']) {
      const count = await runSearch(page, query);
      expect(count).toBeGreaterThanOrEqual(0);
    }
    assertClean(errors, 'rerank hostile');
  });

  test('the abstention warning still fires with reranking on', async ({ page }) => {
    // Reranking reorders the same rows, so it must not turn a query that
    // matched nothing into a confident answer.
    await openSearchTab(page);
    await runSearch(page, 'cách nấu phở bò ngon tại nhà');
    await expect(page.getByTestId('confidence-warning')).toHaveAttribute(
      'data-confidence',
      'none'
    );
  });
});
