# mc-sheetmusic2noteblock

ピアノ楽譜(MIDI / MusicXML / PDF・画像)をアップロードすると、Minecraft の音符ブロック(ノートブロック)+レッドストーン回路でその曲を演奏する装置の「組み立て設計書」をブラウザに表示する Web アプリ。

設計書には、ゲーム内で装置を組むために必要な情報がステップごとに表示されます:

- 前のステップからの遅延と**リピーター構成**(例: 7 RT → リピーター2個: 4目盛+3目盛)
- 音符ブロックの**下に置くブロック**(例: 土 = ハープ、オークの板材 = ベース、金ブロック = ベル)
- 音符ブロックを**何回叩くか**(右クリック回数 0〜24)
- **右手/左手**の別(同時に鳴らす音の組)

ブラウザ上で合成音によるプレビュー再生も可能です。

## ステータス

設計フェーズ完了。実装はこれから([docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) の Phase 0 から着手予定)。

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | 要件定義 |
| [docs/RESEARCH.md](docs/RESEARCH.md) | 調査結果(音符ブロック仕様、量子化の数理、OMR 比較) |
| [docs/DESIGN.md](docs/DESIGN.md) | システム設計(アーキテクチャ、API、データモデル) |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | 実装順序・テスト・検証計画 |

## 予定スタック

Python + FastAPI + music21 / 素の HTML + ES Modules / docker compose(OMR は Audiveris を別コンテナで)
