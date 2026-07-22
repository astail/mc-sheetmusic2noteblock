// 変換設定パネル(docs/DESIGN.md §8 のセクション2)。
// パースサマリを表示し、設定を集めて POST blueprint を実行する。

import { ApiError, createBlueprint } from "./api.js";
import { setState, subscribe } from "./state.js";

export const TPQ_OPTIONS = [3, 4, 5, 6, 8]; // 実効BPM 200/150/120/100/75

// custom プリセットのレンジエディタが選択肢として出す melodic 13音色
// (backend/app/services/instruments.py と一致させる。打楽器3音色は対象外)
export const MELODIC_INSTRUMENTS = [
  { name: "bass", ja: "ベース", blockJa: "オークの板材", baseMidi: 30 },
  { name: "didgeridoo", ja: "ディジュリドゥ", blockJa: "パンプキン", baseMidi: 30 },
  { name: "guitar", ja: "ギター", blockJa: "羊毛(白)", baseMidi: 42 },
  { name: "harp", ja: "ハープ", blockJa: "土(デフォルト系)", baseMidi: 54 },
  { name: "iron_xylophone", ja: "鉄琴", blockJa: "鉄ブロック", baseMidi: 54 },
  { name: "pling", ja: "プリング", blockJa: "グロウストーン", baseMidi: 54 },
  { name: "bit", ja: "ビット", blockJa: "エメラルドブロック", baseMidi: 54 },
  { name: "banjo", ja: "バンジョー", blockJa: "干草の俵", baseMidi: 54 },
  { name: "cow_bell", ja: "カウベル", blockJa: "ソウルサンド", baseMidi: 66 },
  { name: "flute", ja: "フルート", blockJa: "粘土", baseMidi: 66 },
  { name: "bell", ja: "ベル", blockJa: "金ブロック", baseMidi: 78 },
  { name: "chime", ja: "チャイム", blockJa: "パックドアイス", baseMidi: 78 },
  { name: "xylophone", ja: "木琴", blockJa: "骨ブロック", baseMidi: 78 },
];

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

export function noteName(midi) {
  return `${NOTE_NAMES[midi % 12]}${Math.floor(midi / 12) - 1}`;
}

// アップロードファイル由来の文字列(曲名・トラック名)を innerHTML に埋める前にエスケープ
export function escapeHtml(value) {
  return String(value).replace(
    /[&<>"']/g,
    (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch],
  );
}

// tpq 選択肢のラベル: 「実効 BPM 150(原曲比 1.5 倍速)」。原曲 BPM 不明なら比率は省略
export function describeTpq(tpq, originalBpm) {
  const effective = 600 / tpq;
  if (!originalBpm) return `実効 BPM ${effective}`;
  const ratio = effective / originalBpm;
  const rounded = Math.round(ratio * 100) / 100;
  return `実効 BPM ${effective}(原曲比 ${rounded} 倍速)`;
}

// フォーム値 → ConversionSettings。auto の手割当は送らず、小節範囲は両方入力時のみ
export function collectSettings({
  tpq,
  preset,
  transpose,
  handChoices,
  measureStart,
  measureEnd,
  customRanges,
}) {
  const settings = {
    ticks_per_quarter: tpq,
    instrument_preset: preset,
    transpose_semitones: transpose,
  };
  const assignment = {};
  for (const [trackIndex, choice] of Object.entries(handChoices || {})) {
    if (choice !== "auto") assignment[`track_${trackIndex}`] = choice;
  }
  if (Object.keys(assignment).length > 0) settings.hand_assignment = assignment;
  if (measureStart != null && measureEnd != null) {
    settings.measure_range = [measureStart, measureEnd];
  }
  if (preset === "custom") {
    settings.custom_ranges = customRanges;
  }
  return settings;
}

export function validateCustomRanges(preset, customRanges) {
  if (preset !== "custom") return null;
  if (!customRanges || customRanges.length === 0) {
    return "custom を選ぶ場合は音色を1つ以上選択してください";
  }
  return null;
}

export function validateMeasureRange(start, end, measureCount) {
  if (start == null && end == null) return null;
  if (start == null || end == null) return "開始小節と終了小節を両方入力してください";
  if (!Number.isInteger(start) || !Number.isInteger(end)) {
    return "小節範囲は整数で入力してください";
  }
  if (start < 1 || start > end) {
    return "小節範囲は 1 以上かつ 開始 <= 終了 で入力してください";
  }
  if (end > measureCount) {
    return `小節範囲は 1〜${measureCount} で入力してください`;
  }
  return null;
}

export function initSettings() {
  const section = document.getElementById("settings-section");
  const body = document.createElement("div");
  body.id = "settings-body";
  body.innerHTML = '<p class="settings-placeholder">楽譜をアップロードすると設定が表示されます</p>';
  section.appendChild(body);

  subscribe((state, changed) => {
    if (changed.includes("summary") && state.summary) {
      renderPanel(body, state);
    }
  });
}

function renderPanel(body, state) {
  const s = state.summary;
  const measureCount = s.measure_count ?? 0;
  const range =
    s.midi_min != null ? `${noteName(s.midi_min)} 〜 ${noteName(s.midi_max)}` : "－";
  const tracksRows = s.tracks
    .map(
      (t) => `
      <tr>
        <td>${t.index}</td>
        <td>${escapeHtml(t.name ?? "(名称なし)")}${t.is_percussion ? " [打楽器]" : ""}</td>
        <td>${t.staff_number ?? "－"}</td>
        <td>${t.note_count}</td>
        <td>
          <select data-track="${t.index}" class="hand-choice">
            <option value="auto">自動</option>
            <option value="right">右手</option>
            <option value="left">左手</option>
            <option value="ignore">無視</option>
          </select>
        </td>
      </tr>`,
    )
    .join("");
  const tpqOptions = TPQ_OPTIONS.map((tpq) => {
    const recommended = tpq === state.recommendedTpq ? "★推奨 " : "";
    const selected = tpq === (state.recommendedTpq ?? 4) ? "selected" : "";
    return `<option value="${tpq}" ${selected}>tpq ${tpq} — ${recommended}${describeTpq(tpq, s.original_bpm)}</option>`;
  }).join("");
  const customRangeRows = MELODIC_INSTRUMENTS.map(
    (inst) => `
      <tr>
        <td><input type="checkbox" class="custom-range-enable" data-instrument="${inst.name}"></td>
        <td>${inst.ja}</td>
        <td>${inst.blockJa}</td>
        <td>
          <input type="number" class="custom-range-start-midi" data-instrument="${inst.name}"
                 value="${inst.baseMidi}" min="0" max="127" step="1" disabled>
        </td>
      </tr>`,
  ).join("");

  body.innerHTML = `
    <dl class="summary-list">
      <dt>曲名</dt><dd>${escapeHtml(s.title ?? "(無題)")}</dd>
      <dt>原曲 BPM</dt><dd>${s.original_bpm ?? "不明"}${s.has_tempo_changes ? "(テンポ変化あり)" : ""}</dd>
      <dt>音域</dt><dd>${range}</dd>
      <dt>音数</dt><dd>${s.note_count}</dd>
    </dl>
    <table class="tracks-table">
      <thead><tr><th>#</th><th>トラック</th><th>譜表</th><th>音数</th><th>手の割当</th></tr></thead>
      <tbody>${tracksRows}</tbody>
    </table>
    <div class="settings-grid">
      <label>グリッド(tpq)
        <select id="tpq-select">${tpqOptions}</select>
      </label>
      <label>楽器プリセット
        <select id="preset-select">
          <option value="bass_harp_bell">bass_harp_bell(既定)</option>
          <option value="harp_only">harp_only(素材節約)</option>
          <option value="custom">custom(音色ごとに音域を指定)</option>
        </select>
      </label>
      <label>移調(半音)
        <input type="number" id="transpose-input" value="0" min="-12" max="12" step="1">
      </label>
      <label>小節範囲(全 ${measureCount} 小節、未入力なら全曲)
        <span class="measure-range">
          <input type="number" id="measure-start" min="1" max="${measureCount}" step="1" placeholder="開始">
          〜
          <input type="number" id="measure-end" min="1" max="${measureCount}" step="1" placeholder="終了">
        </span>
      </label>
    </div>
    <div id="custom-ranges-editor" class="custom-ranges-editor" hidden>
      <p class="custom-ranges-note">
        custom を選んだ場合、使用する音色にチェックを入れ、その音色に切り替える最低音(元曲側のMIDI番号)を指定してください。
        音色ごとの実際の音高(0クリックの音)は変更できないため、指定した音の付近になるよう自動でオクターブ調整されます。
      </p>
      <table class="custom-ranges-table">
        <thead><tr><th></th><th>音色</th><th>下に置くブロック</th><th>切り替え開始音(MIDI番号)</th></tr></thead>
        <tbody>${customRangeRows}</tbody>
      </table>
    </div>
    <button type="button" id="generate-button" class="generate-button">設計書を生成</button>
    <p id="settings-status" class="upload-status" hidden></p>
  `;

  const status = body.querySelector("#settings-status");
  const generateButton = body.querySelector("#generate-button");
  const presetSelect = body.querySelector("#preset-select");
  const customRangesEditor = body.querySelector("#custom-ranges-editor");

  function showStatus(message, kind) {
    status.hidden = false;
    status.textContent = message;
    status.className = `upload-status upload-status--${kind}`;
  }

  presetSelect.addEventListener("change", () => {
    customRangesEditor.hidden = presetSelect.value !== "custom";
  });

  for (const checkbox of body.querySelectorAll(".custom-range-enable")) {
    checkbox.addEventListener("change", () => {
      const rangeStartInput = body.querySelector(
        `.custom-range-start-midi[data-instrument="${checkbox.dataset.instrument}"]`,
      );
      rangeStartInput.disabled = !checkbox.checked;
    });
  }

  generateButton.addEventListener("click", async () => {
    const handChoices = {};
    for (const select of body.querySelectorAll(".hand-choice")) {
      handChoices[select.dataset.track] = select.value;
    }
    const start = body.querySelector("#measure-start").valueAsNumber;
    const end = body.querySelector("#measure-end").valueAsNumber;
    const measureStart = Number.isNaN(start) ? null : start;
    const measureEnd = Number.isNaN(end) ? null : end;
    const rangeError = validateMeasureRange(measureStart, measureEnd, measureCount);
    if (rangeError) {
      showStatus(rangeError, "error");
      return;
    }
    const preset = presetSelect.value;
    const customRanges = [];
    for (const checkbox of body.querySelectorAll(".custom-range-enable")) {
      if (!checkbox.checked) continue;
      const rangeStartInput = body.querySelector(
        `.custom-range-start-midi[data-instrument="${checkbox.dataset.instrument}"]`,
      );
      customRanges.push({
        instrument: checkbox.dataset.instrument,
        range_start_midi: rangeStartInput.valueAsNumber,
      });
    }
    const customRangesError = validateCustomRanges(preset, customRanges);
    if (customRangesError) {
      showStatus(customRangesError, "error");
      return;
    }
    const settings = collectSettings({
      tpq: Number(body.querySelector("#tpq-select").value),
      preset,
      transpose: Number(body.querySelector("#transpose-input").value) || 0,
      handChoices,
      measureStart,
      measureEnd,
      customRanges,
    });
    const requestedScoreId = state.scoreId;
    showStatus("設計書を生成中…", "busy");
    generateButton.disabled = true;
    try {
      const blueprint = await createBlueprint(requestedScoreId, settings);
      // 応答待ちの間に別スコアがアップロードされていたら、古い結果で state を上書きしない
      if (state.scoreId !== requestedScoreId) return;
      setState({ blueprint, settings });
      showStatus(`設計書を生成しました(${blueprint.meta.step_count} ステップ)`, "success");
      document.getElementById("blueprint-section").scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.detail : "設計書の生成に失敗しました";
      showStatus(message, "error");
    } finally {
      generateButton.disabled = false;
    }
  });
}
