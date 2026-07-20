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

  // 受け入れ基準: すべてのステップカード・すべての音符に必須4点が
  // 揃っていること。allTextContents() は存在する要素しか拾わないため、
  // 各カード/各音符に対して要素の存在(toHaveCount(1))から検証する
  const stepCards = page.locator(".step-card");
  const stepCardCount = await stepCards.count();
  expect(stepCardCount).toBeGreaterThan(0);

  const noteClassNames = [];
  for (let i = 0; i < stepCardCount; i++) {
    const card = stepCards.nth(i);

    // (a) 前ステップからの遅延・リピーター構成(個数+目盛)。
    // 先頭ステップ(delay=0)のみ「リピーターなし」の明示表記になる
    const delay = card.locator(".step-card-delay");
    await expect(delay).toHaveCount(1);
    await expect(delay).toHaveText(/リピーター(\d+個\(.*目盛.*\)|なし)/);

    const notes = card.locator(".step-note");
    const noteCountInCard = await notes.count();
    expect(noteCountInCard).toBeGreaterThan(0);
    for (let j = 0; j < noteCountInCard; j++) {
      const note = notes.nth(j);

      const text = note.locator(".step-note-text");
      await expect(text).toHaveCount(1);
      await expect(text).toContainText("(下: "); // (b) 下に置くブロックの日本語名

      // (c) クリック回数(0〜24)。dots の title 属性(`${clicks}/24 クリック`)が
      // 真の値の情報源。文字列長だけでなく●の個数がその値と一致すること、
      // かつ .step-note-text の「Nクリック」表記とも整合することを検証し、
      // 「常に○のみ」等の表示だけ壊れる回帰を検出する
      const dots = note.locator(".step-note-dots");
      await expect(dots).toHaveCount(1);
      const dotsText = await dots.textContent();
      expect(dotsText).toHaveLength(24);
      const title = await dots.getAttribute("title");
      const clicksMatch = title?.match(/^(\d+)\/24/);
      expect(clicksMatch).not.toBeNull();
      const clicks = Number(clicksMatch[1]);
      expect(clicks).toBeGreaterThanOrEqual(0);
      expect(clicks).toBeLessThanOrEqual(24);
      expect(dotsText).toBe("●".repeat(clicks) + "○".repeat(24 - clicks));
      await expect(text).toContainText(`${clicks}クリック`);

      const className = await note.getAttribute("class");
      expect(className).toMatch(/step-note--(right|left)/); // (d) 右手/左手の別
      noteClassNames.push(className);
    }
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

  // player.js は 0.1秒先読みのスケジューラのため、後半ステップのスケジュール中に
  // 起きる console エラーは再生完了まで待たないと観測できない。自然終了で
  // 停止ボタンが再び無効化される(finishPlayback)のを待ってから判定する
  await expect(page.locator("#stop-button")).toBeDisabled({ timeout: 15000 });

  expect(consoleErrors).toEqual([]);
});
