// SPA エントリポイント(ビルドツールなしの ES Modules 構成)。

import { initBlueprintView } from "./blueprint_view.js";
import { initPlayer } from "./player.js";
import { initSettings } from "./settings.js";
import { initUpload } from "./upload.js";

document.addEventListener("DOMContentLoaded", () => {
  initUpload();
  initSettings();
  initBlueprintView();
  initPlayer();
});
