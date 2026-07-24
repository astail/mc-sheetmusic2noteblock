// single_block プリセット(打楽器も含め全ノートを1音色=1種類の下ブロックに統一)を検証する。
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DRUM_BEAT_MID = path.join(__dirname, "../../../backend/tests/fixtures/drum_beat.mid");

test("single_block を選ぶと打楽器も含め全ノートが1音色・1種類のブロックに統一される", async ({
  page,
}) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error" && !msg.text().includes("favicon.ico")) {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => consoleErrors.push(err.message));

  await page.goto("/");
  await page.setInputFiles("#file-input", DRUM_BEAT_MID);
  await expect(page.locator("#settings-body")).toContainText("音数");

  const editor = page.locator("#single-instrument-editor");
  await expect(editor).toBeHidden();

  await page.selectOption("#preset-select", "single_block");
  await expect(editor).toBeVisible();
  await page.selectOption("#single-instrument-select", "harp");

  await page.locator("#generate-button").click();
  await expect(page.locator(".step-card").first()).toBeVisible();

  // 打楽器(hand="percussion")のノートも harp に統一され、従来の3音色(バスドラム/
  // スネア/ハット)には分かれない
  const percussionNotes = page.locator(".step-note--percussion");
  await expect(percussionNotes).toHaveCount(5);
  for (let i = 0; i < 5; i++) {
    await expect(percussionNotes.nth(i)).toContainText("ハープ");
    await expect(percussionNotes.nth(i)).toContainText("打楽器");
  }
  await expect(page.locator(".step-note-text", { hasText: "バスドラム" })).toHaveCount(0);
  await expect(page.locator(".step-note-text", { hasText: "スネア" })).toHaveCount(0);
  await expect(page.locator(".step-note-text", { hasText: "ハット" })).toHaveCount(0);

  // 資材リストの下ブロックが1種類だけになっている(harp の物理ブロック dirt のみ)
  const materialsRows = page.locator(".materials-list tbody tr");
  await expect(materialsRows).toHaveCount(4); // 音符ブロック/リピーター/dust + base_block 1種類
  await expect(page.locator(".materials-list")).toContainText("dirt");

  await page.locator("#play-button").click();
  await expect(page.locator("#stop-button")).toBeEnabled();
  await expect(page.locator("#stop-button")).toBeDisabled({ timeout: 15000 });

  expect(consoleErrors).toEqual([]);
});
