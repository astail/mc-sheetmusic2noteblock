// レイアウト俯瞰図(上から見た配置図)を SVG で描画し、ステップカードと
// 相互ハイライトする(docs/DESIGN.md §7 layout、issue #36)。

import { getState, subscribe } from "./state.js";

const BLOCK_SIZE = 14; // 1ブロックあたりの横幅(px)
const BRANCH_LENGTH = 22; // 分岐(北/南)の長さ(px)
const MARGIN = 16;

// layout.segments から SVG 描画用の座標を計算する(DOM に依存せず単体テスト可能)
export function computeLayoutGeometry(segments) {
  const maxOffset = segments.reduce((max, s) => Math.max(max, s.bus_offset_blocks), 0);
  const width = maxOffset * BLOCK_SIZE + MARGIN * 2;
  const height = BRANCH_LENGTH * 2 + MARGIN * 2;
  const busY = height / 2;
  const points = segments.map((s) => ({
    stepIndex: s.step_index,
    x: MARGIN + s.bus_offset_blocks * BLOCK_SIZE,
    branches: s.branch_sides.map((side) => ({
      side,
      y: side === "north" ? busY - BRANCH_LENGTH : busY + BRANCH_LENGTH,
    })),
  }));
  return { width, height, busY, points };
}

function svgMarkup(geometry) {
  const { width, height, busY, points } = geometry;
  const lastX = points.length > 0 ? points[points.length - 1].x : MARGIN;
  const busLine = `<line x1="${MARGIN}" y1="${busY}" x2="${lastX}" y2="${busY}" class="layout-bus" />`;
  const groups = points
    .map((p) => {
      const branchLines = p.branches
        .map((b) => `<line x1="${p.x}" y1="${busY}" x2="${p.x}" y2="${b.y}" class="layout-branch" />`)
        .join("");
      const noteMarks = p.branches
        .map((b) => `<circle cx="${p.x}" cy="${b.y}" r="3" class="layout-note" />`)
        .join("");
      return `
        <g class="layout-segment" data-step-index="${p.stepIndex}">
          <title>ステップ${p.stepIndex}</title>
          ${branchLines}${noteMarks}
          <circle cx="${p.x}" cy="${busY}" r="4" class="layout-hit" />
        </g>`;
    })
    .join("");
  return `<svg viewBox="0 0 ${width} ${height}" class="layout-svg" role="img" aria-label="配置俯瞰図">${busLine}${groups}</svg>`;
}

export function initLayoutView() {
  const section = document.getElementById("blueprint-section");
  const container = document.createElement("div");
  container.id = "layout-view";
  section.appendChild(container);

  subscribe((state, changed) => {
    if (!changed.includes("blueprint")) return;
    const layout = state.blueprint?.layout;
    if (!layout || layout.segments.length === 0) {
      container.innerHTML = "";
      return;
    }
    render(container, layout);
  });
}

// クリックと、キーボード(Enter/Space)の両方で onSelect を発火できるようにする。
// SVG <g> も <article> も、ネイティブボタンと違い Enter/Space で click が
// 発火しないため、明示的な keydown ハンドリングが必要
function bindSelectable(el, onSelect) {
  el.tabIndex = 0;
  el.addEventListener("click", onSelect);
  el.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault(); // Space によるページスクロールを防ぐ
      onSelect();
    }
  });
}

function render(container, layout) {
  const geometry = computeLayoutGeometry(layout.segments);
  container.innerHTML = `<h3>配置俯瞰図</h3>${svgMarkup(geometry)}`;

  container.querySelectorAll(".layout-segment").forEach((el) => {
    bindSelectable(el, () => selectStep(container, Number(el.dataset.stepIndex)));
  });

  // ステップカードは blueprint_view.js が同じ blueprint 更新で再生成する。
  // 購読の登録順(main.js で blueprintView → layoutView の順)により、
  // このコールバックが呼ばれる時点で最新のカードが DOM に存在する
  document.querySelectorAll(".step-card").forEach((card) => {
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", `ステップ${card.id.replace("step-", "")}を選択`);
    bindSelectable(card, () => selectStep(container, Number(card.id.replace("step-", ""))));
  });
}

function selectStep(container, stepIndex) {
  container
    .querySelectorAll(".layout-segment--selected")
    .forEach((el) => el.classList.remove("layout-segment--selected"));
  container
    .querySelector(`.layout-segment[data-step-index="${stepIndex}"]`)
    ?.classList.add("layout-segment--selected");

  document
    .querySelectorAll(".step-card--selected")
    .forEach((el) => el.classList.remove("step-card--selected"));
  const cardEl = document.getElementById(`step-${stepIndex}`);
  if (cardEl) {
    cardEl.classList.add("step-card--selected");
    cardEl.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}
