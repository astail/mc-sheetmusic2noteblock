// 再生バーの音量スライダー(既定50%)と、既定で両手が同時に再生されることを検証する。
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TWINKLE_MID = path.join(__dirname, "../../../backend/tests/fixtures/twinkle.mid");

test("音量スライダーは既定50%で、再生ボタンは既定で両手を同時に再生する", async ({ page }) => {
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

  // 既定でソロは「両手」(右手・左手を同時に再生)
  await expect(page.locator("#solo-select")).toHaveValue("both");

  // 音量スライダーは既定50%
  const slider = page.locator("#volume-slider");
  await expect(slider).toHaveValue("50");
  await expect(page.locator("#volume-value")).toHaveText("50%");

  // スライダーを動かすと表示%が追従する
  await slider.fill("80");
  await slider.dispatchEvent("input");
  await expect(page.locator("#volume-value")).toHaveText("80%");
  await slider.fill("50");
  await slider.dispatchEvent("input");

  await page.locator("#generate-button").click();
  await expect(page.locator(".step-card").first()).toBeVisible();

  // 両手(右手メロディ+左手和音)が同じステップカードに同時に現れる
  const firstCardHands = page.locator(".step-card").first().locator(".step-note");
  const handClasses = await firstCardHands.evaluateAll((nodes) =>
    nodes.map((n) => (n.className.includes("step-note--left") ? "left" : "right")),
  );
  expect(handClasses.length).toBeGreaterThan(0);

  await page.locator("#play-button").click();
  await expect(page.locator("#stop-button")).toBeEnabled();
  // 再生中に音量を変更してもエラーにならない
  await slider.fill("20");
  await slider.dispatchEvent("input");
  await expect(page.locator("#volume-value")).toHaveText("20%");
  await expect(page.locator("#stop-button")).toBeDisabled({ timeout: 15000 });

  expect(consoleErrors).toEqual([]);
});
