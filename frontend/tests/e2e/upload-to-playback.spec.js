// アップロード → 設定 → 生成 → 再生ボタン までを自動操作し、
// console エラーが無いこと・ステップカードに必須4点(遅延/下ブロック/クリック数/左右)が
// 常に揃っていることを検証する(docs/IMPLEMENTATION_PLAN.md E2E-4、受け入れ基準)。
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TWINKLE_MID = path.join(__dirname, "../../../backend/tests/fixtures/twinkle.mid");

test("upload twinkle.mid -> generate blueprint -> play with no console errors", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error" && !msg.text().includes("favicon.ico")) {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => consoleErrors.push(err.message));

  await page.goto("/");

  // 1. アップロード
  await page.setInputFiles("#file-input", TWINKLE_MID);
  await expect(page.locator("#settings-body")).toContainText("音数");

  // 2. 設定 → 3. 生成
  await page.locator("#generate-button").click();
  await expect(page.locator(".step-card").first()).toBeVisible();

  // 受け入れ基準: すべてのステップカードに必須4点が揃っていること
  const noteCount = await page.locator(".step-note").count();
  expect(noteCount).toBeGreaterThan(0);

  const delayTexts = await page.locator(".step-card-delay").allTextContents();
  for (const text of delayTexts) {
    // (a) 前ステップからの遅延・リピーター構成(個数+目盛)。
    // 先頭ステップ(delay=0)のみ「リピーターなし」の明示表記になる
    expect(text).toMatch(/リピーター(\d+個\(.*目盛.*\)|なし)/);
  }

  const noteTexts = await page.locator(".step-note-text").allTextContents();
  for (const text of noteTexts) {
    expect(text).toContain("(下: "); // (b) 下に置くブロックの日本語名
  }

  const dotTexts = await page.locator(".step-note-dots").allTextContents();
  for (const text of dotTexts) {
    expect(text).toHaveLength(24); // (c) クリック回数(0〜24を●○24個で表現)
  }

  const notes = page.locator(".step-note");
  const noteClassNames = [];
  for (let i = 0; i < noteCount; i++) {
    const className = await notes.nth(i).getAttribute("class");
    expect(className).toMatch(/step-note--(right|left)/); // (d) 右手/左手の別
    noteClassNames.push(className);
  }
  // twinkle.mid は右手メロディ+左手和音の両方を含むフィクスチャ(test_hand_split.py で保証)。
  // 全音が片手に寄っていないか(左右判別の回帰)も確認する
  expect(noteClassNames.some((c) => c.includes("step-note--right"))).toBe(true);
  expect(noteClassNames.some((c) => c.includes("step-note--left"))).toBe(true);

  // 4. 再生ボタンまで自動操作。実際に再生が始まったこと(停止/一時停止ボタンが
  // 有効化されること)まで確認し、クリックだけして何も起きない回帰を検出する
  await page.locator("#play-button").click();
  await expect(page.locator("#stop-button")).toBeEnabled();
  await expect(page.locator("#pause-button")).toBeEnabled();
  await page.waitForTimeout(500);

  expect(consoleErrors).toEqual([]);
});
