// SPA エントリポイント(ビルドツールなしの ES Modules 構成)。
// 後続 issue で各モジュールを import してここで初期化する:
//   #30/#31 blueprint_view.js、#32 synth.js、#33 player.js

import { initSettings } from "./settings.js";
import { initUpload } from "./upload.js";

document.addEventListener("DOMContentLoaded", () => {
  initUpload();
  initSettings();
});
