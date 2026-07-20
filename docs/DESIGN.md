# システム設計

## 1. 設計方針

1. **変換パイプラインは純粋関数的なモジュール群**(パース → 手判別 → 量子化 → 音高マッピング → 設計書生成)。FastAPI は薄い I/O 層に留め、変換ロジックを単体テストで固める
2. **量子化は「拍グリッド方式」を既定**(詳細は [RESEARCH.md](RESEARCH.md) §3)。テンポ変化曲向けに秒グリッド方式を補助で用意
3. **設計書 JSON(Blueprint)が唯一の正**。フロント表示・プレビュー再生・印刷はすべてこの JSON から描画する
4. **OMR は別コンテナ + compose profile で分離**。MVP は MIDI/MusicXML パスで完成させる
5. フロントは**ビルド不要の素の HTML/ES Modules**。Node ツールチェーンを持ち込まない。FastAPI の StaticFiles で配信

## 2. 全体構成

```
[ブラウザ]
   │ アップロード / 設定 / 設計書取得
   ▼
[app コンテナ]  FastAPI + music21 + 静的フロント配信 (port 8000)
   │ PDF/画像のみ HTTP (OMR_SERVICE_URL)
   ▼
[omr コンテナ]  JRE + Audiveris + 薄い HTTP ラッパ (profile: omr, 外部非公開)

共有: ./data ボリューム (data/scores/{score_id}/ に original / parsed.json / blueprint.json)
```

## 3. リポジトリ構成

```
mc-sheetmusic2noteblock/
├── docker-compose.yml
├── README.md / .gitignore(data/ 等)
├── docs/                           # 本ドキュメント群
├── backend/
│   ├── Dockerfile                  # python:3.12-slim。frontend/ も COPY して配信
│   ├── pyproject.toml              # fastapi, uvicorn, music21, python-multipart, httpx, pydantic, pytest
│   ├── app/
│   │   ├── main.py                 # アプリ生成、/api ルータ登録、frontend/ 静的マウント
│   │   ├── config.py               # DATA_DIR, OMR_SERVICE_URL, 警告閾値(環境変数)
│   │   ├── storage.py              # score_id 発行、data/scores/{id}/ 配下のファイル管理
│   │   ├── models/
│   │   │   ├── events.py           # NoteEvent(パース結果の中間表現)
│   │   │   ├── settings.py         # ConversionSettings(pydantic)
│   │   │   └── blueprint.py        # Blueprint / Step / NotePlacement / Warning / Materials
│   │   ├── api/
│   │   │   ├── scores.py           # アップロード・メタ取得
│   │   │   ├── blueprints.py       # 変換実行・設計書取得
│   │   │   └── omr.py              # OMR ジョブ(Phase 4)
│   │   └── services/
│   │       ├── parser.py           # music21: MIDI/MusicXML/MXL → list[NoteEvent]
│   │       ├── hand_split.py       # 右手/左手判別
│   │       ├── quantizer.py        # 拍/秒グリッド量子化 + 誤差統計 + デデュープ
│   │       ├── instruments.py      # 音色定義テーブル(音域 MIDI、下ブロック、日本語名)
│   │       ├── pitch_mapper.py     # ピッチ → (音色, クリック回数) + オクターブシフト
│   │       ├── blueprint_builder.py# ステップ生成・リピーター分解
│   │       ├── materials.py        # 資材集計
│   │       ├── layout.py           # 物理レイアウト提案(Phase 3)
│   │       └── omr_client.py       # OMR サービス HTTP クライアント(Phase 4)
│   └── tests/
│       ├── unit/                   # quantizer / pitch_mapper / blueprint_builder / hand_split
│       ├── e2e/test_api_flow.py    # TestClient でアップロード→設計書取得の一気通貫
│       └── fixtures/               # scripts/make_fixtures.py が生成する .mid / .musicxml
├── frontend/
│   ├── index.html                  # 1ページ SPA
│   ├── css/style.css, css/print.css
│   └── js/
│       ├── api.js                  # fetch ラッパ
│       ├── state.js                # スコア ID・設定・設計書のクライアント状態
│       ├── upload.js               # ドラッグ&ドロップアップロード
│       ├── settings.js             # 変換設定パネル(実効 BPM 計算表示含む)
│       ├── blueprint_view.js       # ステップ表・資材・警告の描画
│       ├── player.js               # Web Audio スケジューラ(lookahead 再生・ハイライト)
│       └── synth.js                # 音色ごとの合成音レシピ
├── omr/                            # Phase 4
│   ├── Dockerfile                  # JRE + Audiveris + Python 薄ラッパ
│   └── wrapper/server.py           # POST /transcribe: PDF/画像 → Audiveris batch → .mxl 返却
├── scripts/
│   └── make_fixtures.py            # music21 でテスト用 MIDI/MusicXML を生成
└── data/                           # docker volume。gitignore 対象
    └── scores/{score_id}/
```

## 4. docker-compose

```yaml
services:
  app:
    build:
      context: .
      dockerfile: backend/Dockerfile   # backend/ と frontend/ を両方 COPY
    ports: ["8000:8000"]
    volumes:
      - ./data:/data
    environment:
      - DATA_DIR=/data
      - OMR_SERVICE_URL=http://omr:8080

  omr:
    build: ./omr
    profiles: ["omr"]        # MVP では起動不要。--profile omr 指定時のみ起動
    volumes:
      - ./data:/data
    expose: ["8080"]         # 外部非公開
```

- 通常起動: `docker compose up` → app のみ。PDF/画像アップロードは「OMR 無効」エラーを返す
- OMR 込み: `docker compose --profile omr up`
- 開発時は compose.override.yml で `./backend/app` と `./frontend` をマウントし `uvicorn --reload` に差し替え

## 5. API エンドポイント

| Method | Path | 内容 |
|---|---|---|
| POST | `/api/scores` | multipart アップロード。拡張子で判定。mid/musicxml/mxl → 即パースしサマリ返却。pdf/画像 → OMR ジョブ作成(Phase 4)か 501 |
| GET | `/api/scores/{score_id}` | パースサマリ(曲名、原曲 BPM、パート/譜表構成、音数、音域、推奨 tpq、トラック一覧) |
| POST | `/api/scores/{score_id}/blueprint` | body = ConversionSettings。変換実行し Blueprint JSON を返却+永続化 |
| GET | `/api/scores/{score_id}/blueprint` | 最後に生成した設計書 |
| POST | `/api/omr/jobs` | PDF/画像 → 非同期 OMR(Phase 4)。202 + job_id |
| GET | `/api/omr/jobs/{job_id}` | status: queued/running/done/failed。done 時は score_id を返す |
| GET | `/healthz` | 死活監視 |

変換は同期実行で十分(music21 パースは数秒オーダー)。OMR のみ非同期ジョブ
(`asyncio.create_task` + ファイルベースのジョブ状態。Celery 等は不要)。

## 6. 変換パイプラインの責務分割

```
parser.py         : ファイル → list[NoteEvent]
                    NoteEvent = { offset_ql, duration_ql, midi_pitch, part_id,
                                  staff_number, track_index, channel, measure, beat, tie情報 }
                    ・タイは結合して onset のみ採用(音符ブロックはサステイン不可。
                      duration は情報表示用に保持)
                    ・MIDI の ch10(打楽器)は将来拡張用にフラグ付け

hand_split.py     : NoteEvent → hand("right" | "left" | "other") 付与。優先順:
                    ① MusicXML の staff(1=右手, 2=左手)
                    ② MIDI トラック名ヒューリスティック("left" / "right" / "L.H." 等)
                    ③ トラックが2本なら順序で割当
                    ④ 単一トラックは C4 を境に音域分割(fallback)
                    いずれも UI で上書き可能

quantizer.py      : offset_ql × ticks_per_quarter を最近傍丸め → tick(int)
                    ・同 tick の同一音(同音色・同クリック)はデデュープし警告
                    ・誤差統計(最大/平均 ms、移動ノート数)を返す
                    ・seconds モード: music21 の secondsMap × tempo_scale → 0.1s 丸め

pitch_mapper.py   : (midi_pitch + transpose) → { instrument, clicks, octave_shift }
                    プリセット "bass_harp_bell"(既定):
                      MIDI 30〜53 → bass(木材) / 54〜77 → harp(土等) / 78〜102 → bell(金)
                      ※境界 54・78 は harp 優先。30 未満・102 超はオクターブシフトして警告
                    clicks = midi − 音色の基準音(例: C4=60 → harp 基準 F#3=54 → 6 クリック)
                    プリセット "harp_only"(素材節約・全音を2オクターブに折込)も用意

blueprint_builder : tick 昇順のユニーク集合 → Step 列
                    delay = tick_n − tick_{n−1}(RT)
                    リピーター分解: delay d → [4]×(d//4) + ([d%4] if d%4 else [])
                    delay 0 は存在しない(量子化時点で同 step にマージ済み)

materials.py      : 音符ブロック数(= 総発音イベント数。1発音 = 1ブロックの標準構成)、
                    リピーター総数、ダスト概算、音色ブロック別個数

layout.py         : 「直線リピーターバス + 櫛形分岐」の標準構成テキスト/簡易図(Phase 3)
```

## 7. データモデル

### ConversionSettings(リクエスト)

```json
{
  "mode": "beat",                  // "beat" | "seconds"
  "ticks_per_quarter": 4,          // beat モード: 3|4|5|6|8 → 実効BPM 200|150|120|100|75
  "tempo_scale": 1.0,              // seconds モード用の倍率
  "instrument_preset": "bass_harp_bell",   // | "harp_only" | "custom"
  "custom_ranges": null,
  "transpose_semitones": 0,
  "hand_assignment": {"track_0": "right", "track_1": "left"},  // 自動判別の UI 上書き
  "measure_range": null            // [開始小節, 終了小節] 部分変換(長曲対策)
}
```

### Blueprint(設計書。レスポンス & 永続化)

```json
{
  "meta": {
    "title": "きらきら星", "source_file": "twinkle.mid",
    "original_bpm": 100, "effective_bpm": 100, "ticks_per_quarter": 6,
    "total_rticks": 384, "duration_seconds": 38.4, "step_count": 96,
    "quantization": {"max_error_ms": 33, "mean_error_ms": 8, "moved_notes": 12, "merged_notes": 2}
  },
  "steps": [
    {
      "index": 12, "tick": 48, "time_seconds": 4.8,
      "delay_from_prev_rticks": 7,
      "repeaters": {"chain": [4, 3], "count": 2},
      "notes": [
        {
          "instrument": "harp", "instrument_ja": "ハープ",
          "base_block": "dirt", "base_block_ja": "土(デフォルト系)",
          "clicks": 6, "note_name": "C4", "midi": 60,
          "hand": "right", "octave_shift": 0,
          "source": {"measure": 5, "beat": 2.5, "part": "P1"}
        },
        {
          "instrument": "bass", "instrument_ja": "ベース",
          "base_block": "oak_planks", "base_block_ja": "オークの板材",
          "clicks": 6, "note_name": "C3", "midi": 48,
          "hand": "left", "octave_shift": 0
        }
      ]
    }
  ],
  "materials": {
    "note_block": 214, "repeater": 350, "redstone_dust_estimate": 180,
    "base_blocks": {"dirt": 120, "oak_planks": 74, "gold_block": 20},
    "notes": ["音符ブロックの真上は空気にすること", "起動用ボタン/レバー 1個"]
  },
  "warnings": [
    {"type": "octave_shift", "message": "A0〜B1 の 4音は bass 音域に収めるため +1〜+2 オクターブしました", "steps": [3, 17]},
    {"type": "big_chord", "message": "ステップ42は同時7音です。主バスから分岐ダストを南北（±Z）の両側に伸ばし、音符ブロックを振り分けて配線してください", "steps": [42]},
    {"type": "repeater_limit", "message": "リピーター総数は350個で、設定閾値の300個を超えています。曲を分割して複数の演奏装置に分けることを推奨します"},
    {"type": "tempo_change", "message": "原曲にテンポ変化があります。beat モードでは一定テンポ(100BPM)に平坦化されます"}
  ],
  "layout": {
    "type": "comb_bus",
    "description": "リピーターを +X 方向に直列。各ステップ位置から ±Z 方向へダスト分岐し音符ブロックを設置",
    "segments": [{"step_index": 12, "bus_offset_blocks": 25, "branch_sides": ["north", "south"]}]
  }
}
```

リピーター総数の警告閾値は `REPEATER_WARNING_THRESHOLD`（既定値: 300）で変更できる。

**設計上のポイント**: この JSON だけでフロントの表示・プレビュー再生・印刷がすべて賄える
(`tick` と `clicks` と `instrument` があれば Web Audio 再生に十分)。

## 8. フロントエンド画面構成(1ページ SPA、上から下へのウィザード)

1. **アップロードセクション** — D&D + ファイル選択。`.mid/.musicxml/.mxl` は即時、`.pdf/.png/.jpg` は「実験的機能(OMR)」バッジ付きで進捗ポーリング表示
2. **設定パネル** — パースサマリ(曲名・原曲 BPM・音域・トラック構成)を表示した上で:
   - tpq 選択(各選択肢に「実効 BPM 150(原曲比 1.5 倍速)」のように表示。原曲 BPM に最も近い値を推奨マーク)
   - 楽器プリセット、移調(±半音)、トラック→右手/左手/無視の割当テーブル、小節範囲
   - 「設計書を生成」ボタン → POST blueprint
3. **設計書ビュー**
   - サマリーカード: 実効 BPM / 総ステップ数 / 総リピーター数 / 演奏時間 / 資材リスト表
   - 警告一覧(オクターブシフト・大和音・マージ)
   - **ステップカード列**(本体):
     - 「⏱ 前のステップから 7 RT 遅延 → リピーター2個(4目盛+3目盛)」
     - 音符ごとに「ハープ(下: 土)/ 6クリック = C4 / 右手」。クリック回数は ●●●●●●○○ のドット表示で数えやすく。右手=青系 / 左手=橙系の色分け
   - 印刷ボタン(print.css で紙向けレイアウト)
4. **プレビュー再生バー**(画面下部固定) — 再生/一時停止/停止、再生速度(0.5x/1x)、右手のみ/左手のみソロ。再生中は現在ステップをハイライトして自動スクロール
   - `synth.js`: 音色ごとの合成レシピ(RESEARCH.md §5)
   - `player.js`: `tick × 0.1s ÷ rate` で lookahead スケジューリング + requestAnimationFrame でハイライト同期
