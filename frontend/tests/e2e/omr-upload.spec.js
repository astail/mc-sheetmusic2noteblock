// PDF/画像アップロードを OMR ジョブ API に接続する経路を検証する
// (docs/DESIGN.md §8 セクション1、issue #43)。
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCAN_PDF = path.join(__dirname, "../../../backend/tests/fixtures/scan.pdf");

test("OMR profile が無効な場合は起動方法とMuseScoreでの代替を案内する", async ({ page }) => {
  await page.goto("/");
  await page.setInputFiles("#file-input", SCAN_PDF);

  const status = page.locator("#upload-status");
  await expect(status).toContainText("--profile omr");
  await expect(status).toContainText("MuseScore");
});

test("OMR ジョブの進捗をポーリングし、完了したスコアを設定パネルへ反映する", async ({ page }) => {
  let pollCount = 0;

  await page.route("**/api/omr/jobs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ job_id: "job-1", status: "queued" }),
    });
  });

  await page.route("**/api/omr/jobs/job-1", async (route) => {
    pollCount += 1;
    const status = pollCount === 1 ? "queued" : pollCount === 2 ? "running" : "done";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        job_id: "job-1",
        status,
        score_id: status === "done" ? "score-1" : null,
        error: null,
      }),
    });
  });

  await page.route("**/api/scores/score-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        score_id: "score-1",
        summary: {
          title: "scan",
          original_bpm: 120,
          has_tempo_changes: false,
          midi_min: 60,
          midi_max: 72,
          note_count: 42,
          duration_ql: 16,
          measure_count: 4,
          tracks: [
            {
              index: 0,
              part_id: "P1",
              name: "Piano",
              staff_number: null,
              is_percussion: false,
              note_count: 42,
            },
          ],
        },
        recommended_tpq: 4,
      }),
    });
  });

  await page.goto("/");
  await page.setInputFiles("#file-input", SCAN_PDF);

  const status = page.locator("#upload-status");
  await expect(status).toContainText("順番待ち");
  await expect(status).toContainText("解析中");
  await expect(status).toContainText("音数 42");
  await expect(page.locator("#settings-body")).toContainText("音数");
});
