// プレビュー再生(lookahead スケジューラ)。docs/DESIGN.md §8 の下部固定バー。
//
// 一時停止は AudioContext.suspend()/resume() に委譲する: サスペンド中は
// currentTime が進まないため、スケジュール済みノートの絶対時刻がそのまま
// 再開後も正しく機能する(再スケジュール不要)。

import { createLimiter, playNote } from "./synth.js";
import { getState, subscribe } from "./state.js";

const TICK_SECONDS = 0.1;
const SCHEDULE_AHEAD_SECONDS = 0.1;
const SCHEDULER_INTERVAL_MS = 25;
const START_DELAY_SECONDS = 0.1; // 最初のスケジューラ実行前に発音要求が来ないための余裕

// tick 差と再生速度から発音時刻の差分(秒)を計算する: tick × 0.1s ÷ rate
export function scheduleTime(tick, rate) {
  return (tick * TICK_SECONDS) / rate;
}

export function initPlayer() {
  const bar = document.getElementById("player-bar");
  bar.innerHTML = `
    <button type="button" id="play-button" disabled>▶ 再生</button>
    <button type="button" id="pause-button" disabled>⏸ 一時停止</button>
    <button type="button" id="stop-button" disabled>■ 停止</button>
    <label class="player-rate"><input type="checkbox" id="rate-checkbox"> 0.5倍速</label>
    <label class="player-solo">ソロ:
      <select id="solo-select">
        <option value="both">両手</option>
        <option value="right">右手のみ</option>
        <option value="left">左手のみ</option>
      </select>
    </label>
  `;

  const playButton = bar.querySelector("#play-button");
  const pauseButton = bar.querySelector("#pause-button");
  const stopButton = bar.querySelector("#stop-button");
  const rateCheckbox = bar.querySelector("#rate-checkbox");
  const soloSelect = bar.querySelector("#solo-select");

  let audioContext = null;
  let limiter = null;
  let currentStepIndex = 0;
  let nextStepTime = 0;
  let schedulerTimer = null;
  let highlightQueue = []; // [{stepIndex, time}] 未ハイライトの発音予定
  let rafId = null;
  let highlightedEl = null;

  function rate() {
    return rateCheckbox.checked ? 0.5 : 1;
  }

  function visibleNotes(step) {
    const solo = soloSelect.value;
    return solo === "both" ? step.notes : step.notes.filter((n) => n.hand === solo);
  }

  function scheduler() {
    const steps = getState().blueprint.steps;
    while (
      currentStepIndex < steps.length &&
      nextStepTime < audioContext.currentTime + SCHEDULE_AHEAD_SECONDS
    ) {
      const step = steps[currentStepIndex];
      const notes = visibleNotes(step);
      for (const note of notes) {
        playNote(audioContext, limiter, {
          instrument: note.instrument,
          midi: note.midi,
          startTime: nextStepTime,
          polyphony: notes.length,
        });
      }
      highlightQueue.push({ stepIndex: step.index, time: nextStepTime });
      const next = steps[currentStepIndex + 1];
      if (next) nextStepTime += scheduleTime(next.tick - step.tick, rate());
      currentStepIndex++;
    }
    if (currentStepIndex >= steps.length && schedulerTimer) {
      clearInterval(schedulerTimer);
      schedulerTimer = null;
    }
  }

  function setHighlight(stepIndex) {
    if (highlightedEl) highlightedEl.classList.remove("step-card--active");
    const el = document.getElementById(`step-${stepIndex}`);
    if (el) {
      el.classList.add("step-card--active");
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    highlightedEl = el;
  }

  function highlightLoop() {
    if (!audioContext) return;
    const now = audioContext.currentTime;
    while (highlightQueue.length > 0 && highlightQueue[0].time <= now) {
      setHighlight(highlightQueue.shift().stepIndex);
    }
    rafId = requestAnimationFrame(highlightLoop);
  }

  function play() {
    if (audioContext) {
      audioContext.resume();
      return;
    }
    const blueprint = getState().blueprint;
    if (!blueprint || blueprint.steps.length === 0) return;
    audioContext = new AudioContext();
    limiter = createLimiter(audioContext);
    limiter.connect(audioContext.destination);
    currentStepIndex = 0;
    nextStepTime = audioContext.currentTime + START_DELAY_SECONDS;
    highlightQueue = [];
    scheduler();
    schedulerTimer = setInterval(scheduler, SCHEDULER_INTERVAL_MS);
    rafId = requestAnimationFrame(highlightLoop);
    updateButtons();
  }

  function pause() {
    if (audioContext) audioContext.suspend();
    updateButtons();
  }

  function stop() {
    if (schedulerTimer) clearInterval(schedulerTimer);
    schedulerTimer = null;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
    if (audioContext) audioContext.close();
    audioContext = null;
    if (highlightedEl) highlightedEl.classList.remove("step-card--active");
    highlightedEl = null;
    updateButtons();
  }

  function updateButtons() {
    const hasBlueprint = Boolean(getState().blueprint);
    const isSuspended = audioContext && audioContext.state === "suspended";
    playButton.disabled = !hasBlueprint || (Boolean(audioContext) && !isSuspended);
    pauseButton.disabled = !audioContext || isSuspended;
    stopButton.disabled = !audioContext;
  }

  playButton.addEventListener("click", play);
  pauseButton.addEventListener("click", pause);
  stopButton.addEventListener("click", stop);

  subscribe((state, changed) => {
    if (changed.includes("blueprint")) {
      stop();
      playButton.disabled = !state.blueprint;
    }
  });
}
