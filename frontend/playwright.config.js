// docs/IMPLEMENTATION_PLAN.md の E2E 4「Playwright MCP でアップロード〜再生ボタンまで自動化」を
// 再現可能な形で固定化したもの。実行前に `docker compose up` 等でアプリを起動しておくこと。
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:8000",
  },
});
