import { test, expect } from '@playwright/test';
import { assertClean, hitDocCodes, openSearchTab, runSearch, watchErrors } from './helpers';

test.describe('Scoping a question to chosen documents', () => {
  test('the staging picker is gone from the retrieval tab', async ({ page }) => {
    /* It selects which document the reviewer tabs edit and does nothing here
       except decide which results offer a "Sửa" button. Left visible, it read
       as a search filter -- a user changed it, saw results not change, and
       reasonably concluded retrieval was broken. */
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    const picker = page.locator('header select');
    await expect(picker).toBeVisible();

    await page.getByRole('button', { name: /Thử Nghiệm Truy Xuất/ }).click();
    await expect(page.getByPlaceholder(/Nhập tình huống vi phạm/)).toBeVisible();
    await expect(picker).toBeHidden();
  });

  test('the scope selector starts at the whole corpus', async ({ page }) => {
    await openSearchTab(page);
    await expect(page.getByTestId('scope-summary')).toContainText('toàn bộ');
  });

  test('scoping to one document confines every result to it', async ({ page }) => {
    const errors = watchErrors(page);
    await openSearchTab(page);

    const wide = await runSearch(page, 'vượt đèn đỏ');
    expect(wide).toBeGreaterThan(0);

    await page.getByTestId('scope-toggle').click();
    await page.getByTestId('scope-QCVN41/2024/BGTVT').check();
    const scoped = await runSearch(page, 'vượt đèn đỏ');
    expect(scoped).toBeGreaterThan(0);

    const codes = await hitDocCodes(page);
    expect(new Set(codes)).toEqual(new Set(['QCVN41/2024/BGTVT']));
    assertClean(errors, 'scoped retrieval');
  });

  test('clearing the scope goes back to the whole corpus', async ({ page }) => {
    await openSearchTab(page);
    await page.getByTestId('scope-toggle').click();
    await page.getByTestId('scope-QCVN41/2024/BGTVT').check();
    await expect(page.getByTestId('scope-summary')).toContainText('1 văn bản');

    await page.getByTestId('scope-clear').click();
    await expect(page.getByTestId('scope-summary')).toContainText('toàn bộ');
  });

  test('a repealed decree is labelled, not silently empty', async ({ page }) => {
    /* Filtering to NĐ 100/2019 at today's date correctly returns nothing --
       it was superseded by 168/2024 -- and that looks like a defect unless
       the reason is on screen. */
    await openSearchTab(page);
    await page.getByTestId('scope-toggle').click();
    await expect(page.getByTestId('scope-list')).toContainText('hết hiệu lực');
  });
});
