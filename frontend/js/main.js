// SPA エントリポイント(ビルドツールなしの ES Modules 構成)。

import { initBlueprintView } from "./blueprint_view.js";
import { initLayoutView } from "./layout_view.js";
import { initPlayer } from "./player.js";
import { initSettings } from "./settings.js";
import { initUpload } from "./upload.js";

document.addEventListener("DOMContentLoaded", () => {
  initUpload();
  initSettings();
  initBlueprintView();
  // layoutView はステップカードの click に相互ハイライトを付与するため、
  // blueprintView がカードを再生成した後に登録される必要がある
  initLayoutView();
  initPlayer();
});
