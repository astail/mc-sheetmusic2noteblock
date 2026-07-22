// custom プリセットのレンジエディタ(音色選択 + 基準音指定)を検証する
// (docs/DESIGN.md §7、issue #46)。
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TWINKLE_MID = path.join(__dirname, "../../../backend/tests/fixtures/twinkle.mid");

test("custom を選ぶとレンジエディタが現れ、チェックした音色で再生できる", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error" && !msg.text().includes("favicon.ico")) {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => consoleErrors.push(err.message));

  await page.goto("/");
  await page.setInputFiles("#file-input", TWINKLE_MID);
  await expect(page.locator("#settings-body")).toContainText("音数");

  const editor = page.locator("#custom-ranges-editor");
  await expect(editor).toBeHidden();

  await page.selectOption("#preset-select", "custom");
  await expect(editor).toBeVisible();

  // custom を選んだのに何も選択しないと生成前にエラーを出す(APIラウンドトリップ不要)
  await page.locator("#generate-button").click();
  await expect(page.locator("#settings-status")).toContainText("音色を1つ以上選択");
  await expect(page.locator(".step-card")).toHaveCount(0);

  // ギター(base_midi=42 の synth 未検証レシピ)を選択して生成
  const guitarRow = page.locator("tr", { hasText: "ギター" });
  await guitarRow.locator(".custom-range-enable").check();
  await expect(guitarRow.locator(".custom-range-base-midi")).toBeEnabled();

  await page.locator("#generate-button").click();
  await expect(page.locator(".step-card").first()).toBeVisible();

  const notes = page.locator(".step-note");
  const noteCount = await notes.count();
  expect(noteCount).toBeGreaterThan(0);
  for (let i = 0; i < noteCount; i++) {
    await expect(notes.nth(i)).toContainText("ギター");
  }

  await page.locator("#play-button").click();
  await expect(page.locator("#stop-button")).toBeEnabled();
  await expect(page.locator("#stop-button")).toBeDisabled({ timeout: 15000 });

  expect(consoleErrors).toEqual([]);
});
