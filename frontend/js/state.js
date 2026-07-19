// クライアント状態(score_id / サマリ / 変換設定 / 設計書)と最小の購読通知。

const state = {
  scoreId: null,
  summary: null, // ScoreSummary
  recommendedTpq: null,
  settings: null, // ConversionSettings 相当(設定パネル #29 が初期化)
  blueprint: null, // Blueprint
};

const listeners = new Set();

export function getState() {
  return state;
}

// 変更をマージし、変更キーの配列とともに購読者へ通知する
export function setState(partial) {
  Object.assign(state, partial);
  const changed = Object.keys(partial);
  for (const listener of listeners) {
    listener(state, changed);
  }
}

// listener(state, changedKeys) を登録し、解除関数を返す
export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
