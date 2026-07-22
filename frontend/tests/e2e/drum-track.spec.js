// MIDI ch10(打楽器)トラックが basedrum/snare/hat の3音色に振り分けられ、
// 設計書表示・再生の両方で動作することを検証する(docs/RESEARCH.md §1、issue #44)。
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DRUM_BEAT_MID = path.join(__dirname, "../../../backend/tests/fixtures/drum_beat.mid");

test("打楽器トラックが3音色に振り分けられ、アイコン付きで再生できる", async ({ page }) => {
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
  await expect(page.locator(".tracks-table")).toContainText("[打楽器]");

  await page.locator("#generate-button").click();
  await expect(page.locator(".step-card").first()).toBeVisible();

  const percussionNotes = page.locator(".step-note--percussion");
  await expect(percussionNotes).toHaveCount(5);
  await expect(percussionNotes.nth(0)).toContainText("バスドラム");
  await expect(percussionNotes.nth(0)).toContainText("打楽器");
  await expect(percussionNotes.nth(0).locator(".step-note-icon")).toHaveText("🥁");
  await expect(percussionNotes.nth(1)).toContainText("スネア");
  await expect(percussionNotes.nth(2)).toContainText("ハット");

  await page.locator("#play-button").click();
  await expect(page.locator("#stop-button")).toBeEnabled();
  await expect(page.locator("#stop-button")).toBeDisabled({ timeout: 15000 });

  expect(consoleErrors).toEqual([]);
});
