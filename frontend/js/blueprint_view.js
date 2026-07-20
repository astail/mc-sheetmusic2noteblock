// 設計書ビュー: サマリーカード・資材リスト・警告一覧(docs/DESIGN.md §7・§8 のセクション3)。
// ステップカード列本体は issue #31 で追加する(この段階では #summary-cards / #materials-list / #warnings-list のみ)。

import { escapeHtml } from "./settings.js";
import { subscribe } from "./state.js";

const WARNING_LABELS = {
  octave_shift: "オクターブシフト",
  big_chord: "大きな和音",
  tempo_change: "テンポ変化",
  merge: "音のマージ",
};

export function formatDuration(seconds) {
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
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
  `;
}
