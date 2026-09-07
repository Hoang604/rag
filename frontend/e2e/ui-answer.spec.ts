import { test, expect } from '@playwright/test';
import { assertClean, watchErrors } from './helpers';

/* The LLM tab.
 *
 * Most of these deliberately drive the abstention path: retrieval finds
 * nothing, the server never launches a CLI, and the test costs no model quota
 * and no wall-clock. Exactly one test asks a real question, because the value
 * of this tab is that a model actually answers and the answer is checked --
 * and a suite that never proves that is testing scaffolding.
 */

const open = async (page: import('@playwright/test').Page) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: /Hỏi Đáp \(LLM\)/ }).click();
  await expect(page.getByPlaceholder(/Nhập câu hỏi luật giao thông/)).toBeVisible();
};

test.describe('Answering with a local agent CLI', () => {
  test('the tab opens with nothing staged', async ({ page }) => {
    /* Same defect as the retrieval tab had: this reads the promoted corpus and
       must not be gated behind the staging buffer. */
    await open(page);
    await expect(page.getByText(/Vùng đệm Staging đang trống/)).toBeHidden();
  });

  test('the staging picker is hidden here too', async ({ page }) => {
    await open(page);
    await expect(page.locator('header select')).toBeHidden();
  });

  test('only installed providers are selectable', async ({ page }) => {
    await open(page);
    const select = page.getByTestId('provider-select');
    await expect(select).toBeVisible();
    // Presence is reported by the server from `shutil.which`; a CLI that is
    // absent is offered but disabled rather than hidden, so the reviewer can
    // see what the machine could support.
    //
    // Waited for, not counted immediately: the list arrives from
    // /api/answer/providers after the first paint, and counting straight away
    // raced the fetch -- which is how this test failed the first time it ran.
    const options = select.locator('option');
    await expect.poll(() => options.count(), { timeout: 15_000 }).toBeGreaterThan(0);
    await expect(select).toHaveValue(/.+/);
  });

  test('the ask button stays disabled on an empty box', async ({ page }) => {
    await open(page);
    await expect(page.getByTestId('ask-button')).toBeDisabled();
  });

  test('a meaningless question is refused without calling a model', async ({
    page,
  }) => {
    /* The keyword signal catches this, so `compose` returns before any CLI
       runs. Measured at 25 of 25 meaningless queries, 0 of 408 real ones. */
    const errors = watchErrors(page);
    await open(page);
    await page.getByPlaceholder(/Nhập câu hỏi luật giao thông/).fill('asdkjfh qwoieu zxcvb');
    await page.getByTestId('ask-button').click();

    await expect(page.getByTestId('grounding-abstained')).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByTestId('answer-text')).toContainText('Không tìm thấy');
    assertClean(errors, 'abstained answer');
  });

  test('a real question is answered and the answer is checked', async ({ page }) => {
    test.setTimeout(240_000);
    const errors = watchErrors(page);
    await open(page);
    await page
      .getByPlaceholder(/Nhập câu hỏi luật giao thông/)
      .fill('Xe máy vượt đèn đỏ phạt bao nhiêu?');
    await page.getByTestId('ask-button').click();

    const answer = page.getByTestId('answer-text');
    await expect(answer).toBeVisible({ timeout: 200_000 });
    expect((await answer.innerText()).length).toBeGreaterThan(20);

    // The provisions the model was given stay on the page beside its prose.
    expect(await page.getByTestId('answer-source').count()).toBeGreaterThan(0);

    // One of the two verdicts must be shown -- never neither.
    const ok = page.getByTestId('grounding-ok');
    const failed = page.getByTestId('grounding-failed');
    expect((await ok.count()) + (await failed.count())).toBe(1);
    assertClean(errors, 'real answer');
  });
});
