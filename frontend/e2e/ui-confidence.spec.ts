import { test, expect } from '@playwright/test';
import { openSearchTab, runSearch } from './helpers';

// The fused score is a sum of reciprocal ranks, so five irrelevant provisions
// score much like five good ones. These assert the page says so rather than
// presenting an unanswerable question's nearest neighbours as an answer.
test.describe('Retrieval confidence is shown to the reader', () => {
  const warning = (page: import('@playwright/test').Page) =>
    page.getByTestId('confidence-warning');

  test('an answerable question carries no warning', async ({ page }) => {
    await openSearchTab(page);
    await runSearch(page, 'Xe máy vượt đèn đỏ phạt bao nhiêu?');
    await expect(warning(page)).toHaveCount(0);
  });

  test('a meaningless query is marked as matching nothing', async ({ page }) => {
    await openSearchTab(page);
    await runSearch(page, 'asdkjhaskdjh');
    await expect(warning(page)).toHaveAttribute('data-confidence', 'none');
    await expect(warning(page)).toContainText('ngoài phạm vi');
  });

  test('an out-of-domain question is not presented as answered', async ({ page }) => {
    await openSearchTab(page);
    await runSearch(page, 'cách nấu phở bò ngon tại nhà');
    await expect(warning(page)).toHaveAttribute('data-confidence', 'none');
  });

  test('an injection string is marked as matching nothing', async ({ page }) => {
    await openSearchTab(page);
    await runSearch(page, 'UNION SELECT * FROM documents');
    await expect(warning(page)).toHaveAttribute('data-confidence', 'none');
  });

  test('a legal question from another field is flagged as weak', async ({ page }) => {
    await openSearchTab(page);
    await runSearch(page, 'thuế thu nhập cá nhân tính thế nào');
    // Shares no traffic vocabulary but plenty of legal register, so the
    // keyword side still matches and only the similarity signal fires.
    await expect(warning(page)).toHaveAttribute('data-confidence', 'low');
  });
});
