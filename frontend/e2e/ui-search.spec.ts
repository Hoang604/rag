import { test, expect } from '@playwright/test';
import {
  assertClean,
  hitAddresses,
  hitDocCodes,
  openSearchTab,
  readFacets,
  runSearch,
  watchErrors,
} from './helpers';

test.describe('Retrieval through the real interface', () => {
  test('every tab renders without throwing', async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    const tabs = [
      'Legal Studio',
      'Đối Chiếu Toàn Văn',
      'Đồ Thị Quan Hệ 2D',
      'Lịch Sử & Diff',
      'Thẩm Định Toàn Vẹn',
      'Thử Nghiệm Truy Xuất',
    ];
    for (const tab of tabs) {
      await page.getByRole('button', { name: new RegExp(tab) }).click();
      await page.waitForTimeout(400);
      assertClean(errors, `tab ${tab}`);
    }
  });

  test('a plain question returns provisions and resolves both facets', async ({ page }) => {
    const errors = watchErrors(page);
    await openSearchTab(page);

    const count = await runSearch(page, 'Xe máy vượt đèn đỏ phạt bao nhiêu?');
    expect(count).toBeGreaterThan(0);

    const facets = await readFacets(page);
    expect(facets.vehicle).toContain('mô tô');
    expect(facets.role).toContain('mức phạt');

    // The motorcycle red-light offence is Điều 7 of NĐ 168/2024.
    expect(await hitDocCodes(page)).toContain('168/2024/ND-CP');
    expect((await hitAddresses(page))[0]).toMatch(/^Điều 7\b/);
    assertClean(errors, 'plain question');
  });

  test('the same offence resolves to a different vehicle article', async ({ page }) => {
    await openSearchTab(page);
    await runSearch(page, 'Ô tô vượt đèn đỏ phạt bao nhiêu?');
    const facets = await readFacets(page);
    expect(facets.vehicle).toContain('ô tô');
    // Điều 6 governs cars, Điều 7 motorcycles: the facet must move the answer.
    expect((await hitAddresses(page))[0]).toMatch(/^Điều 6\b/);
  });

  test('a question typed without tone marks still finds the article', async ({ page }) => {
    const errors = watchErrors(page);
    await openSearchTab(page);
    const count = await runSearch(page, 'xe may vuot den do phat bao nhieu');
    expect(count).toBeGreaterThan(0);
    const facets = await readFacets(page);
    expect(facets.vehicle).toContain('mô tô');
    expect((await hitAddresses(page))[0]).toMatch(/^Điều 7\b/);
    assertClean(errors, 'unaccented');
  });

  test('the violation date moves the answer to the statute in force then', async ({ page }) => {
    await openSearchTab(page);
    const dateBox = page.locator('input[type="date"]');

    await dateBox.fill('2024-06-15');
    await runSearch(page, 'Xe máy vượt đèn đỏ phạt bao nhiêu?');
    const then = await hitDocCodes(page);
    expect(then).toContain('100/2019/ND-CP');
    expect(then).not.toContain('168/2024/ND-CP');

    await dateBox.fill('2025-06-15');
    await runSearch(page, 'Xe máy vượt đèn đỏ phạt bao nhiêu?');
    const now = await hitDocCodes(page);
    expect(now).toContain('168/2024/ND-CP');
    expect(now).not.toContain('100/2019/ND-CP');
  });

  test('the result limit is honoured', async ({ page }) => {
    await openSearchTab(page);
    for (const [option, expected] of [
      ['Top 3', 3],
      ['Top 10', 10],
    ] as const) {
      await page.getByRole('main').getByRole('combobox').selectOption({ label: option });
      const count = await runSearch(page, 'Tốc độ tối đa trên đường cao tốc là bao nhiêu?');
      expect(count).toBeLessThanOrEqual(expected);
    }
  });

  test('every sample question on the page works', async ({ page }) => {
    const errors = watchErrors(page);
    await openSearchTab(page);
    const samples = page.getByRole('main').locator('button', { hasText: /\?$/ });
    const total = await samples.count();
    expect(total).toBeGreaterThan(0);

    for (let i = 0; i < total; i++) {
      await samples.nth(i).click();
      await expect(page.getByText(/Đang truy hồi trên toàn corpus/)).toBeHidden({
        timeout: 45_000,
      });
      const count = Number(
        await page.getByTestId('result-count').getAttribute('data-count')
      );
      expect(count).toBeGreaterThan(0);
    }
    assertClean(errors, 'sample questions');
  });

  test('the submit button stays disabled on an empty box', async ({ page }) => {
    await openSearchTab(page);
    const button = page.getByRole('button', { name: 'Tra cứu' });
    await expect(button).toBeDisabled();
    await page.getByPlaceholder(/Nhập tình huống vi phạm/).fill('   ');
    await expect(button).toBeDisabled();
  });
});
