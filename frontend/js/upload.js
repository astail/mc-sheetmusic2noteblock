// 楽譜アップロード(D&D + ファイル選択)。docs/DESIGN.md §8 のセクション1。

import { ApiError, createOmrJob, getOmrJob, getScore, uploadScore } from "./api.js";
import { setState } from "./state.js";

const SCORE_EXTENSIONS = [".mid", ".musicxml", ".mxl"];
const OMR_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"];
const OMR_POLL_INTERVAL_MS = 1500;
const OMR_STATUS_LABEL = { queued: "順番待ち", running: "解析中" };

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

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

  async function pollOmrJob(jobId, fileName) {
    for (;;) {
      const job = await getOmrJob(jobId);
      if (job.status === "done") {
        const score = await getScore(job.score_id);
        setState({
          scoreId: score.score_id,
          summary: score.summary,
          recommendedTpq: score.recommended_tpq,
          blueprint: null, // 新しいスコアでは前の設計書を破棄
        });
        const warningText = job.warning ? ` ${job.warning}` : "";
        showStatus(
          `「${fileName}」をOMRで読み取りました(音数 ${score.summary.note_count})。` +
            `読み取り精度は楽譜の品質に依存するため、内容をご確認ください。${warningText}`,
          job.warning ? "info" : "success",
        );
        // 次のステップ(変換設定)へ誘導
        document
          .getElementById("settings-section")
          .scrollIntoView({ behavior: "smooth" });
        return;
      }
      if (job.status === "failed") {
        showStatus(job.error?.message ?? "OMR処理に失敗しました", "error");
        return;
      }
      showStatus(
        `「${fileName}」をOMRで解析しています…(${OMR_STATUS_LABEL[job.status] ?? job.status})`,
        "busy",
      );
      await sleep(OMR_POLL_INTERVAL_MS);
    }
  }

  async function handleOmrFile(file) {
    showStatus(`「${file.name}」のOMRジョブを開始しています…`, "busy");
    uploading = true;
    selectButton.disabled = true;
    try {
      const created = await createOmrJob(file);
      await pollOmrJob(created.job_id, file.name);
    } catch (err) {
      if (err instanceof ApiError && err.status === 501) {
        showStatus(
          `${err.detail} うまく認識できない場合は MuseScore 等で ` +
            ".musicxml へ事前に変換してからのアップロードもお試しください。",
          "error",
        );
      } else {
        const message =
          err instanceof ApiError ? err.detail : "OMRジョブの開始に失敗しました";
        showStatus(message, "error");
      }
    } finally {
      uploading = false;
      selectButton.disabled = false;
    }
  }

  async function handleFile(file) {
    if (uploading) return;
    const kind = classifyFile(file.name);
    if (kind === "omr") {
      await handleOmrFile(file);
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
