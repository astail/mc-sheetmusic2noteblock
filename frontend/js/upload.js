// 楽譜アップロード(D&D + ファイル選択)。docs/DESIGN.md §8 のセクション1。

import { ApiError, uploadScore } from "./api.js";
import { setState } from "./state.js";

const SCORE_EXTENSIONS = [".mid", ".musicxml", ".mxl"];
const OMR_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"];

// "score" | "omr" | "unsupported"
export function classifyFile(name) {
  const lowered = (name || "").toLowerCase();
  const ext = lowered.slice(lowered.lastIndexOf("."));
  if (SCORE_EXTENSIONS.includes(ext)) return "score";
  if (OMR_EXTENSIONS.includes(ext)) return "omr";
  return "unsupported";
}

export function initUpload() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const selectButton = document.getElementById("file-select-button");
  const status = document.getElementById("upload-status");
  let uploading = false; // アップロード中の並行投入(D&D 含む)をガード

  function showStatus(message, kind) {
    status.hidden = false;
    status.textContent = message;
    status.className = `upload-status upload-status--${kind}`;
  }

  async function handleFile(file) {
    if (uploading) return;
    const kind = classifyFile(file.name);
    if (kind === "omr") {
      showStatus(
        "PDF/画像は実験的機能(OMR)として準備中で、現在は未対応です(Phase 4 で対応予定)",
        "info",
      );
      return;
    }
    if (kind === "unsupported") {
      showStatus("未対応のファイル形式です(.mid / .musicxml / .mxl)", "error");
      return;
    }
    showStatus(`「${file.name}」をアップロード中…`, "busy");
    uploading = true;
    selectButton.disabled = true;
    try {
      const res = await uploadScore(file);
      setState({
        scoreId: res.score_id,
        summary: res.summary,
        recommendedTpq: res.recommended_tpq,
        blueprint: null, // 新しいスコアでは前の設計書を破棄
      });
      showStatus(
        `「${file.name}」を読み込みました(音数 ${res.summary.note_count})`,
        "success",
      );
      // 次のステップ(変換設定)へ誘導
      document
        .getElementById("settings-section")
        .scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.detail : "アップロードに失敗しました";
      showStatus(message, "error");
    } finally {
      uploading = false;
      selectButton.disabled = false;
    }
  }

  selectButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) handleFile(fileInput.files[0]);
    fileInput.value = ""; // 同じファイルの再選択を許可
  });

  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("dropzone--dragover");
  });
  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dropzone--dragover");
  });
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("dropzone--dragover");
    if (event.dataTransfer.files.length > 0) handleFile(event.dataTransfer.files[0]);
  });
}
