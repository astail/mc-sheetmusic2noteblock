// 同一(音色, クリック数)の音符ブロック再利用が設計書表示・資材集計に
// 反映されることを検証する(docs/IMPLEMENTATION_PLAN.md Phase 5、issue #45)。
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TWINKLE_MID = path.join(__dirname, "../../../backend/tests/fixtures/twinkle.mid");

test("繰り返し音符が既存ブロックの再利用として表示され、資材が減る", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error" && !msg.text().includes("favicon.ico")) {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => consoleErrors.push(err.message));

  await page.goto("/");
  await page.setInputFiles("#file-input", TWINKLE_MID);
  await page.locator("#generate-button").click();
  await expect(page.locator(".step-card").first()).toBeVisible();

  // twinkle.mid 冒頭の「ドド」(同音連打)がブロック再利用として表示される
  await expect(page.locator(".step-note-text").filter({ hasText: "を再利用" }).first()).toBeVisible();
  await expect(page.locator(".materials-notes")).toContainText("箇所で既存の音符ブロックを再利用し");

  await page.locator("#play-button").click();
  await expect(page.locator("#stop-button")).toBeEnabled();
  await expect(page.locator("#stop-button")).toBeDisabled({ timeout: 15000 });

  expect(consoleErrors).toEqual([]);
});
