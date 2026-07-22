// 設計書ビュー: サマリーカード・資材リスト・警告一覧・ステップカード列(docs/DESIGN.md §7・§8 のセクション3)。

import { escapeHtml } from "./settings.js";
import { subscribe } from "./state.js";

const WARNING_LABELS = {
  octave_shift: "オクターブシフト",
  big_chord: "大きな和音",
  tempo_change: "テンポ変化",
  merge: "音のマージ",
  repeater_limit: "曲の分割提案",
  block_reuse: "ブロック再利用",
};

const HAND_LABELS = { right: "右手", left: "左手", percussion: "打楽器" };

export function formatDuration(seconds) {
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

// clicks(0〜24) を ●●●●●●○○ のドット表示にする(REQUIREMENTS.md 必須4点)
export function clicksDots(clicks) {
  return "●".repeat(clicks) + "○".repeat(24 - clicks);
}

// 「⏱ 前のステップから 7 RT → リピーター2個(4目盛+3目盛)」/ 先頭ステップは曲頭からの遅延として表記
export function describeDelay(step, index) {
  const prefix = index === 0 ? "曲頭から" : "前のステップから";
  if (step.delay_from_prev_rticks === 0) {
    return `⏱ ${prefix} 0 RT(リピーターなし)`;
  }
  const chainText = step.repeaters.chain.map((v) => `${v}目盛`).join("+");
  return `⏱ ${prefix} ${step.delay_from_prev_rticks} RT → リピーター${step.repeaters.count}個(${chainText})`;
}

// 配線距離内で同じ(音色, クリック数)が再登場した場合の追記。
// 「ブロック#3を再利用(初出: ステップ5)」
function describeReuse(note) {
  if (note.reused_from_step == null) return "";
  return ` (ブロック#${note.block_id}を再利用、初出: ステップ${note.reused_from_step})`;
}

// 「ハープ(下: 土)/ 6クリック = C4 / 右手」。打楽器は音程の概念がないため専用の表記にする
export function describeNote(note) {
  if (note.hand === "percussion") {
    return `${note.instrument_ja}(下: ${note.base_block_ja}) / 打楽器${describeReuse(note)}`;
  }
  return `${note.instrument_ja}(下: ${note.base_block_ja}) / ${note.clicks}クリック = ${note.note_name} / ${HAND_LABELS[note.hand] ?? note.hand}${describeReuse(note)}`;
}

// 元の小節・拍の併記。source がなければ null
export function describeSource(source) {
  if (!source) return null;
  return `小節${source.measure} 拍${source.beat}(${source.part})`;
}

export function initBlueprintView() {
  const section = document.getElementById("blueprint-section");
  const body = document.createElement("div");
  body.id = "blueprint-body";
  body.innerHTML = '<p class="settings-placeholder">設計書を生成すると表示されます</p>';
  section.appendChild(body);

  subscribe((state, changed) => {
    if (changed.includes("blueprint")) {
      if (state.blueprint) {
        renderBlueprint(body, state.blueprint);
      } else {
        body.innerHTML = '<p class="settings-placeholder">設計書を生成すると表示されます</p>';
      }
    }
  });
}

function renderBlueprint(body, blueprint) {
  const { meta, materials, warnings } = blueprint;

  const summaryCards = [
    ["実効 BPM", meta.effective_bpm ?? "－(秒モード)"],
    ["総ステップ数", meta.step_count],
    ["総リピーター数", materials.repeater],
    ["演奏時間", formatDuration(meta.duration_seconds)],
  ]
    .map(([label, value]) => `
      <div class="summary-card">
        <div class="summary-card-label">${label}</div>
        <div class="summary-card-value">${escapeHtml(String(value))}</div>
      </div>`)
    .join("");

  const baseBlockRows = Object.entries(materials.base_blocks)
    .map(([block, count]) => `<tr><td>${escapeHtml(block)}</td><td>${count}</td></tr>`)
    .join("");
  const materialNotes = materials.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("");

  const warningItems = warnings
    .map((w) => {
      const label = WARNING_LABELS[w.type] ?? w.type;
      const link =
        w.steps && w.steps.length > 0
          ? ` <a href="#step-${w.steps[0]}" class="warning-jump">ステップ${w.steps[0]}へ</a>`
          : "";
      return `<li class="warning-item warning-item--${escapeHtml(w.type)}"><strong>${escapeHtml(label)}</strong>: ${escapeHtml(w.message)}${link}</li>`;
    })
    .join("");

  body.innerHTML = `
    <button type="button" id="print-button" class="print-button no-print">🖨 印刷</button>
    <div class="summary-cards">${summaryCards}</div>
    <section class="materials-list">
      <h3>資材リスト</h3>
      <table class="tracks-table">
        <thead><tr><th>資材</th><th>個数</th></tr></thead>
        <tbody>
          <tr><td>音符ブロック</td><td>${materials.note_block}</td></tr>
          <tr><td>リピーター</td><td>${materials.repeater}</td></tr>
          <tr><td>レッドストーンダスト(概算)</td><td>${materials.redstone_dust_estimate}</td></tr>
          ${baseBlockRows}
        </tbody>
      </table>
      ${materialNotes ? `<ul class="materials-notes">${materialNotes}</ul>` : ""}
    </section>
    ${
      warnings.length > 0
        ? `<section class="warnings-list"><h3>警告</h3><ul>${warningItems}</ul></section>`
        : ""
    }
    <section class="step-cards">
      <h3>ステップ</h3>
      ${blueprint.steps.map((step) => renderStepCard(step)).join("")}
    </section>
  `;

  body.querySelector("#print-button").addEventListener("click", () => window.print());
}

function renderStepCard(step) {
  const notesHtml = step.notes
    .map((note) => {
      const source = describeSource(note.source);
      const marker =
        note.hand === "percussion"
          ? `<span class="step-note-icon" title="打楽器">🥁</span>`
          : `<span class="step-note-dots" title="${note.clicks}/24 クリック">${clicksDots(note.clicks)}</span>`;
      return `
        <li class="step-note step-note--${escapeHtml(note.hand)}">
          <span class="step-note-text">${escapeHtml(describeNote(note))}</span>
          ${marker}
          ${source ? `<span class="step-note-source">${escapeHtml(source)}</span>` : ""}
        </li>`;
    })
    .join("");

  return `
    <article id="step-${step.index}" class="step-card">
      <div class="step-card-delay">${escapeHtml(describeDelay(step, step.index))}</div>
      <ul class="step-notes">${notesHtml}</ul>
    </article>`;
}
