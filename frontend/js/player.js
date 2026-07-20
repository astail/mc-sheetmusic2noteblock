// プレビュー再生(lookahead スケジューラ)。docs/DESIGN.md §8 の下部固定バー。
//
// 一時停止は AudioContext.suspend()/resume() に委譲する: サスペンド中は
// currentTime が進まないため、スケジュール済みノートの絶対時刻がそのまま
// 再開後も正しく機能する(再スケジュール不要)。

import { MAX_NOTE_DURATION_SECONDS, createLimiter, playNote } from "./synth.js";
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
  // 直近に発音したステップを基準に、まだ発音していないステップの時刻を
  // scheduler() のたびにライブな rate() で再計算する(速度変更を即時反映するため)
  let anchorTime = 0;
  let anchorTick = 0;
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
    while (currentStepIndex < steps.length) {
      const step = steps[currentStepIndex];
      // 直近に発音したステップからの距離を、その都度ライブな rate() で計算する。
      // まだ発音していない限り何度でも再計算されるため、速度変更が次の
      // scheduler() 実行(最大 SCHEDULER_INTERVAL_MS 後)で反映される
      const targetTime = anchorTime + scheduleTime(step.tick - anchorTick, rate());
      if (targetTime >= audioContext.currentTime + SCHEDULE_AHEAD_SECONDS) break;

      const notes = visibleNotes(step);
      for (const note of notes) {
        playNote(audioContext, limiter, {
          instrument: note.instrument,
          midi: note.midi,
          startTime: targetTime,
          polyphony: notes.length,
        });
      }
      highlightQueue.push({ stepIndex: step.index, time: targetTime });
      anchorTime = targetTime;
      anchorTick = step.tick;
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
    const totalSteps = getState().blueprint?.steps.length ?? 0;
    const finished = !schedulerTimer && highlightQueue.length === 0 && currentStepIndex >= totalSteps;
    if (finished) {
      finishPlayback(); // 最後のステップまで表示し終えたら再生バーを再生前の状態に戻す
      return;
    }
    rafId = requestAnimationFrame(highlightLoop);
  }

  function play() {
    if (audioContext) {
      audioContext.resume().then(updateButtons); // resume は非同期のため解決後に反映
      return;
    }
    const blueprint = getState().blueprint;
    if (!blueprint || blueprint.steps.length === 0) return;
    audioContext = new AudioContext();
    limiter = createLimiter(audioContext);
    limiter.connect(audioContext.destination);
    currentStepIndex = 0;
    // tick 0 を基準に開始する(先頭ステップが曲頭から遅れている場合もこの後の
    // scheduleTime 計算で自然に反映される)
    anchorTime = audioContext.currentTime + START_DELAY_SECONDS;
    anchorTick = 0;
    highlightQueue = [];
    scheduler();
    schedulerTimer = setInterval(scheduler, SCHEDULER_INTERVAL_MS);
    rafId = requestAnimationFrame(highlightLoop);
    updateButtons();
  }

  function pause() {
    if (audioContext) audioContext.suspend().then(updateButtons); // suspend は非同期のため解決後に反映
  }

  // スケジューラ/ハイライトを止めて UI を再生前の状態に戻す(AudioContext は閉じない)
  function resetUiState() {
    if (schedulerTimer) clearInterval(schedulerTimer);
    schedulerTimer = null;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
    if (highlightedEl) highlightedEl.classList.remove("step-card--active");
    highlightedEl = null;
    updateButtons();
  }

  // ユーザーが「■ 停止」を押した場合: 即座に無音化する
  function stop() {
    const ctx = audioContext;
    audioContext = null;
    resetUiState();
    if (ctx) ctx.close();
  }

  // 最後のステップまで表示し終えた場合: 末尾ノート(最長 bell の減衰)が
  // 鳴り終わるまで AudioContext を閉じずに待ってから片付ける
  function finishPlayback() {
    const ctx = audioContext;
    audioContext = null;
    resetUiState();
    setTimeout(() => ctx.close(), MAX_NOTE_DURATION_SECONDS * 1000);
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
