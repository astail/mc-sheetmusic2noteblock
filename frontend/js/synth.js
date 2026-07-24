// Web Audio による音色ごとの合成音レシピ(docs/RESEARCH.md §5)。
// Minecraft の実音源は著作物のため使用せず、音色を模した合成音で代替する。

const A4_MIDI = 69;
const A4_FREQUENCY = 440;

// MIDI ノート番号 → 周波数(A4=69=440Hz を基準に半音単位で変換)
export function midiToFrequency(midi) {
  return A4_FREQUENCY * 2 ** ((midi - A4_MIDI) / 12);
}

// 音色ごとの基準音 MIDI(backend/app/services/instruments.py と一致させる)
const INSTRUMENT_BASE_MIDI = { bass: 30, harp: 54, bell: 78 };

// clicks(0〜24)+ 音色基準音 → 周波数。note.midi に依存せず単独で検証できるようにする
export function frequencyFromClicks(instrument, clicks) {
  const base = INSTRUMENT_BASE_MIDI[instrument];
  if (base == null) throw new Error(`未対応の音色です: ${instrument}`);
  return midiToFrequency(base + clicks);
}

// custom プリセット(issue #46)では instruments.py の melodic 13音色すべてが
// 選ばれうるため、個別の合成音を持たない音色は RESEARCH.md §5 が示す同系統
// (同音域帯の代替音色)のレシピを流用する。
const RECIPE_BY_INSTRUMENT = {
  bass: "low", // 矩形波の低域
  didgeridoo: "low", // bass と同音域の代替音色(RESEARCH.md §1)
  harp: "pluck", // 減衰の速い三角波 + ローパス
  iron_xylophone: "pluck", // harp と同音域の別音色
  pling: "pluck", // 〃(RESEARCH.md §5)
  bit: "pluck", // 〃
  banjo: "pluck", // 〃
  guitar: "pluck", // 中低音の弦系音色として pluck 系統を流用
  cow_bell: "bell", // 中高音の金属/持続系音色として bell 系統を流用
  flute: "bell", // 〃
  bell: "bell", // 倍音を重ねたサイン波 + 長めの減衰
  chime: "bell", // bell と同音域の別音色(RESEARCH.md §5)
  xylophone: "bell", // 〃
  basedrum: "noise-low", // ノイズ + ローパス(打楽器。音程の概念がない)
  snare: "noise-mid", // ノイズ + バンドパス
  hat: "noise-high", // ノイズ + ハイパス
};

function recipeFor(instrument) {
  const recipe = RECIPE_BY_INSTRUMENT[instrument];
  if (!recipe) throw new Error(`未対応の音色です: ${instrument}`);
  return recipe;
}

// bell の倍音構成(基音+2倍音+3倍音)。合計振幅が1になるよう正規化しておく
const BELL_PARTIALS = [1, 2, 3];
const BELL_WEIGHTS_RAW = [1, 0.5, 0.25];
const BELL_WEIGHTS = (() => {
  const sum = BELL_WEIGHTS_RAW.reduce((a, b) => a + b, 0);
  return BELL_WEIGHTS_RAW.map((w) => w / sum);
})();

// 各レシピの最長発音時間(秒)。bell が最長(#33 player.js が末尾ノートの減衰を待つのに使う)
export const MAX_NOTE_DURATION_SECONDS = 2.05;

const BASE_PEAK_GAIN = 0.9;

// 和音時にクリップしないよう、同時発音数(polyphony)に応じてピークゲインを下げる
export function normalizedGain(polyphony) {
  return BASE_PEAK_GAIN / Math.max(1, polyphony);
}

// 波形の波高率(peak/RMS比)の違いにより、同じピーク振幅でも聴感音量が異なる
// (矩形波はRMS=振幅そのもので、三角波・正弦波よりも聴感で大きく聞こえる)。
// pluck(三角波、RMS比 1/√3)を基準に、他の波形のRMS比との差分だけ減衰させ
// 聴感音量を揃える。低音(bass/didgeridoo)が不釣り合いに大きく聞こえる問題への対応
const TRIANGLE_RMS_RATIO = 1 / Math.sqrt(3);
const RECIPE_LOUDNESS_COMPENSATION = {
  pluck: 1,
  low: TRIANGLE_RMS_RATIO / 1, // 矩形波(RMS比 1)
  bell: TRIANGLE_RMS_RATIO / (1 / Math.sqrt(2)), // 正弦波近似(RMS比 1/√2)
};

function loudnessCompensation(recipe) {
  return RECIPE_LOUDNESS_COMPENSATION[recipe] ?? 1;
}

// bell 等は減衰(最長2秒)が次ステップ以降の発音と重なりうるため、
// polyphony によるステップ内正規化だけでは足りない。呼び出し側は
// playNote の destination の手前にこのノードを挟み、ステップをまたぐ
// 余韻の重なりも含めてクリップを防ぐ。
export function createLimiter(audioContext) {
  const limiter = audioContext.createDynamicsCompressor();
  const t = audioContext.currentTime;
  limiter.threshold.setValueAtTime(-6, t);
  limiter.knee.setValueAtTime(0, t);
  limiter.ratio.setValueAtTime(20, t);
  limiter.attack.setValueAtTime(0.001, t);
  limiter.release.setValueAtTime(0.1, t);
  return limiter;
}

// ノイズ系レシピ(打楽器)ごとのフィルタ設定。音程の概念がないため周波数は固定値
const NOISE_DURATION_SECONDS = 0.2;
const NOISE_FILTER_BY_RECIPE = {
  "noise-low": { type: "lowpass", frequency: 150 },
  "noise-mid": { type: "bandpass", frequency: 900 },
  "noise-high": { type: "highpass", frequency: 6000 },
};

// ホワイトノイズをフィルタに通して短く減衰させる(打楽器のアタック音を模す)
function playNoise(audioContext, gainNode, recipe, startTime, peak) {
  const bufferSize = Math.ceil(audioContext.sampleRate * NOISE_DURATION_SECONDS);
  const buffer = audioContext.createBuffer(1, bufferSize, audioContext.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < bufferSize; i++) data[i] = Math.random() * 2 - 1;
  const source = audioContext.createBufferSource();
  source.buffer = buffer;
  const filter = audioContext.createBiquadFilter();
  const { type, frequency } = NOISE_FILTER_BY_RECIPE[recipe];
  filter.type = type;
  filter.frequency.setValueAtTime(frequency, startTime);
  source.connect(filter);
  filter.connect(gainNode);
  gainNode.gain.linearRampToValueAtTime(peak, startTime + 0.002);
  gainNode.gain.exponentialRampToValueAtTime(0.001, startTime + NOISE_DURATION_SECONDS);
  source.start(startTime);
  source.stop(startTime + NOISE_DURATION_SECONDS);
  return { stop: () => source.stop() };
}

// audioContext の destination に音符1つ分の音源をスケジュールする。
// polyphony はそのステップの同時発音数(#33 player.js が呼び出し時に渡す)。
// destination は createLimiter() の出力を経由させること(余韻の重なり対策)。
export function playNote(audioContext, destination, { instrument, midi, startTime, polyphony = 1 }) {
  const recipe = recipeFor(instrument);
  const peak = normalizedGain(polyphony) * loudnessCompensation(recipe);
  const gainNode = audioContext.createGain();
  gainNode.gain.setValueAtTime(0, startTime);
  gainNode.connect(destination);

  if (recipe in NOISE_FILTER_BY_RECIPE) {
    return playNoise(audioContext, gainNode, recipe, startTime, peak);
  }

  const frequency = midiToFrequency(midi);

  if (recipe === "pluck") {
    const osc = audioContext.createOscillator();
    osc.type = "triangle";
    osc.frequency.setValueAtTime(frequency, startTime);
    const filter = audioContext.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.setValueAtTime(frequency * 4, startTime);
    osc.connect(filter);
    filter.connect(gainNode);
    gainNode.gain.linearRampToValueAtTime(peak, startTime + 0.005);
    gainNode.gain.exponentialRampToValueAtTime(0.001, startTime + 0.4);
    osc.start(startTime);
    osc.stop(startTime + 0.45);
    return { stop: () => osc.stop() };
  }

  if (recipe === "low") {
    const osc = audioContext.createOscillator();
    osc.type = "square";
    osc.frequency.setValueAtTime(frequency, startTime);
    osc.connect(gainNode);
    gainNode.gain.linearRampToValueAtTime(peak, startTime + 0.01);
    gainNode.gain.exponentialRampToValueAtTime(0.001, startTime + 0.6);
    osc.start(startTime);
    osc.stop(startTime + 0.65);
    return { stop: () => osc.stop() };
  }

  // bell: 倍音を重ねたサイン波 + 長めの減衰
  const oscillators = BELL_PARTIALS.map((mult, i) => {
    const osc = audioContext.createOscillator();
    osc.type = "sine";
    osc.frequency.setValueAtTime(frequency * mult, startTime);
    const partialGain = audioContext.createGain();
    partialGain.gain.setValueAtTime(BELL_WEIGHTS[i], startTime);
    osc.connect(partialGain);
    partialGain.connect(gainNode);
    osc.start(startTime);
    osc.stop(startTime + 2.05);
    return osc;
  });
  gainNode.gain.linearRampToValueAtTime(peak, startTime + 0.02);
  gainNode.gain.exponentialRampToValueAtTime(0.001, startTime + 2.0);
  return { stop: () => oscillators.forEach((o) => o.stop()) };
}
