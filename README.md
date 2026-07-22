# mc-sheetmusic2noteblock

ピアノ楽譜(MIDI / MusicXML / PDF・画像)をアップロードすると、Minecraft の音符ブロック(ノートブロック)+レッドストーン回路でその曲を演奏する装置の「組み立て設計書」をブラウザに表示する Web アプリ。

設計書には、ゲーム内で装置を組むために必要な情報がステップ(発音タイミング)ごとに表示されます:

- 前のステップからの遅延と**リピーター構成**(例: 7 RT → リピーター2個: 4目盛+3目盛)
- 音符ブロックの**下に置くブロック**(例: 土 = ハープ、オークの板材 = ベース、金ブロック = ベル)
- 音符ブロックを**何回叩くか**(右クリック回数 0〜24)
- **右手/左手/打楽器**の別(同時に鳴らす音の組)
- 設計書全体の**資材リスト**(音符ブロック数・リピーター数・ダスト概算・音色別ブロック数)と、注意すべき箇所への**警告**(音域外シフト、大和音の配線、ブロック再利用時の配線注意など)

ブラウザ上で合成音によるプレビュー再生、印刷用レイアウト、配置俯瞰図(SVG)も利用できます。

## クイックスタート

```bash
docker compose up --build
```

ブラウザで <http://localhost:8000> を開き、`.mid` / `.musicxml` / `.mxl` ファイルをドラッグ&ドロップ(またはファイル選択)してください。設定を選んで「設計書を生成」を押すと、ステップカード・資材リスト・プレビュー再生が表示されます。

PDF・画像(スキャン楽譜)から変換したい場合は、[OMR(光学楽譜認識)](#omr光学楽譜認識pdf画像対応)を参照してください(別途起動が必要な任意機能です)。

## 使い方(一連の流れ)

1. **アップロード**: `.mid` / `.musicxml` / `.mxl` をドロップ、または PDF・画像(OMR 有効時)をアップロード
2. **変換設定**: パースした曲のサマリ(曲名・原曲 BPM・音域・トラック構成)を見ながら以下を設定
   - **グリッド(tpq)**: 3/4/5/6/8 から選択。実効 BPM(= 600 / tpq)が原曲 BPM にどれだけ近いかを表示し、推奨値には★マークが付く
   - **楽器プリセット**:
     - `bass_harp_bell`(既定): 低音 → bass、中音 → harp、高音 → bell の3層
     - `harp_only`: 全音を harp の2オクターブに折り込み、必要な音色ブロック種を減らす
     - `custom`: instruments.py の melodic 13音色から自由に選び、各音色の切り替え開始音(MIDI番号)を指定できる
   - **移調**(±半音)、**小節範囲**(部分変換。長い曲の一部だけ変換したい場合)
   - **トラック→右手/左手/無視**の割当上書き(自動判別の結果を手動で修正可能)
3. **設計書を生成**: 上記設定で変換を実行し、ステップカード・資材リスト・警告・配置俯瞰図を表示
4. **プレビュー再生**: 画面下部の再生バーで合成音を確認(再生速度0.5x/1x、右手のみ/左手のみ/両手のソロ切替、現在のステップをハイライト表示)
5. **印刷**: 設計書ビューの「🖨 印刷」ボタンで、紙で持ち込みやすいレイアウトに整形して印刷

## 主な機能

- **音色マッピング**: 16音色(melodic 13 + 打楽器3)を、instruments.py の音域テーブルに基づき自動または手動で音符ブロックへ割り当て
- **打楽器対応**: MIDI ch10 のトラックを GM percussion map に基づき basedrum(石)/ snare(砂)/ hat(ガラス)の3音色へ振り分け
- **同一ブロック再利用**: 同じ(音色, クリック数)の組み合わせが近い配線距離で繰り返し登場する場合、既存の音符ブロックを再利用して資材を削減(再利用箇所には配線上の注意を警告として表示)
- **量子化**: 拍グリッド方式(既定)と秒グリッド方式(テンポ変化がある曲向け)。量子化誤差の統計(最大/平均ms、移動ノート数)も返す
- **手判別**: MusicXML の譜表、MIDI トラック名、トラック順、音域による自動判別 + 手動上書き
- **物理レイアウト提案**: 「直線リピーターバス + 櫛形分岐」の標準構成を配置俯瞰図(SVG)として表示
- **警告表示**: オクターブシフト、大和音(同時発音5音以上)の配線ガイド、リピーター総数超過時の分割提案、ブロック再利用時の配線注意
- **部分変換**: 長い曲の一部の小節だけを変換対象にできる
- **OMR(実験的機能)**: PDF・スキャン画像から Audiveris で MusicXML を生成し、通常のパイプラインへ合流

## OMR(光学楽譜認識、PDF/画像対応)

PDF・画像のアップロードは既定では無効です。別コンテナ(Audiveris)を起動すると使えるようになります:

```bash
docker compose --profile omr up --build
```

- OMR は変換に時間がかかるため非同期ジョブとして扱われます: `POST /api/omr/jobs` でジョブを作成(202 + job_id)、`GET /api/omr/jobs/{job_id}` でポーリングし、`done` になったら通常の score と同様に扱えます
- OMR profile が起動していない状態で PDF・画像をアップロードすると、501 と共に起動方法を案内します(フロントには MuseScore 等での事前 `.musicxml` 変換という代替手段も表示されます)
- 精度は楽譜の品質に強く依存するため、UI 上に「実験的機能」の免責が表示されます
- Audiveris コンテナの詳細(HTTP API、対応形式、ビルド・検証方法、ライセンス)は [omr/README.md](omr/README.md) を参照してください

## API エンドポイント

| Method | Path | 内容 |
|---|---|---|
| POST | `/api/scores` | multipart アップロード。`.mid`/`.musicxml`/`.mxl` のみ対応し即パースしてサマリ返却。PDF/画像は常に501(OMR profile の有効/無効に関わらず、PDF/画像は下記の `POST /api/omr/jobs` を使用すること) |
| GET | `/api/scores/{score_id}` | パースサマリ(曲名、原曲 BPM、パート/譜表構成、音数、音域、推奨 tpq、トラック一覧) |
| POST | `/api/scores/{score_id}/blueprint` | body = ConversionSettings。変換を実行し Blueprint JSON を返却・永続化 |
| GET | `/api/scores/{score_id}/blueprint` | 最後に生成した設計書を取得 |
| POST | `/api/omr/jobs` | PDF/画像 → 非同期 OMR ジョブを作成(202 + job_id)。OMR profile 無効時は501 |
| GET | `/api/omr/jobs/{job_id}` | ジョブ状態(`queued`/`running`/`done`/`failed`)。`done` 時は `score_id` を返す |
| GET | `/healthz` | 死活監視 |

リクエスト・レスポンスの詳細なスキーマ(`ConversionSettings`・`Blueprint` の JSON 例)は [docs/DESIGN.md](docs/DESIGN.md) §7 を参照してください。

## 仕組み(変換パイプライン)

```
アップロードされたファイル
  → parser.py         music21 で解析し NoteEvent 列 + サマリを生成(タイの結合、打楽器の GM percussion map 展開を含む)
  → hand_split.py      右手/左手/打楽器/無視を判定
  → quantizer.py        オフセットを tick へ量子化し、誤差統計を算出
  → pitch_mapper.py     プリセットに応じて (音色, クリック数, オクターブシフト) を決定
  → blueprint_builder.py  tick 順の Step 列・meta・警告(オクターブシフト/大和音/マージ/リピーター超過)を組み立て
  → layout.py           直線バス+櫛形分岐の物理配置(バス上の位置、分岐方向)を算出
  → block_reuse.py       同一(音色, クリック数)の音符ブロックを配線距離内で再利用し、block_id を付与
  → materials.py         音符ブロック数・リピーター数・ダスト概算・音色別ブロック数を集計
  → Blueprint JSON として永続化・返却
```

フロントエンドはビルド不要の素の HTML + ES Modules(`frontend/js/`)で、この Blueprint JSON だけで設計書表示・プレビュー再生(Web Audio 合成音)・印刷レイアウトのすべてを描画します。アーキテクチャや各モジュールの責務分割の詳細は [docs/DESIGN.md](docs/DESIGN.md) を参照してください。

## 環境変数

| 変数 | 既定値 | 内容 |
|---|---|---|
| `DATA_DIR` | `./data` | アップロードされた楽譜・設計書・OMRジョブの永続化先 |
| `OMR_SERVICE_URL` | `http://omr:8080` | OMR コンテナの接続先 |
| `OMR_HEALTHCHECK_TIMEOUT_SECONDS` | `2` | OMR 死活監視のタイムアウト |
| `OMR_REQUEST_TIMEOUT_SECONDS` | `330` | OMR 変換リクエストのタイムアウト |
| `REPEATER_WARNING_THRESHOLD` | `300` | リピーター総数がこれを超えると分割提案の警告を出す |

OMR コンテナ自体の環境変数(`AUDIVERIS_MIN_HEAP` 等)は [omr/README.md](omr/README.md) を参照してください。

## 開発

### バックエンドのテスト

```bash
cd backend
pip install -e .[dev]
pytest -q
```

### フロントエンドの E2E テスト(Playwright)

アプリを起動した状態(`docker compose up`)で実行します。

```bash
cd frontend
npm install
npx playwright install --with-deps chromium
npm run test:e2e
```

### 開発時のホットリロード

`docker compose up` は `compose.override.yml` により自動的に `--reload` 付きで起動し、`backend/app/` と `frontend/` の変更が即座に反映されます。

## リポジトリ構成

```
backend/app/
├── api/            scores・blueprints・omr の各エンドポイント
├── models/         pydantic モデル(NoteEvent, ConversionSettings, Blueprint 等)
├── services/       変換パイプライン各段(parser, hand_split, quantizer, pitch_mapper,
│                    blueprint_builder, layout, block_reuse, materials, instruments, omr_client)
└── storage.py      data/ 配下のファイル管理

frontend/
├── js/              アップロード・設定・設計書ビュー・配置俯瞰図・プレビュー再生の各モジュール
├── css/             画面用・印刷用スタイル
└── tests/e2e/       Playwright E2E テスト

omr/                 Audiveris OMR コンテナ(HTTP ラッパ含む)
docs/                要件定義・調査結果・システム設計・実装計画(設計時の検討記録)
```

## ドキュメント

`docs/` 配下は開発初期の設計・調査プロセスの記録です。実装は完了しており、実際の挙動・API・データモデルは本 README と各ソースのコメントが最新の情報源です。

| ドキュメント | 内容 |
|---|---|
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | 要件定義 |
| [docs/RESEARCH.md](docs/RESEARCH.md) | 調査結果(音符ブロック仕様、量子化の数理、OMR 比較、Web Audio 合成音の設計) |
| [docs/DESIGN.md](docs/DESIGN.md) | システム設計(アーキテクチャ、API、データモデルの JSON 例) |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | 実装順序・テスト戦略(開発時の計画。完了済み) |

## スタック

Python + FastAPI + music21(バックエンド) / 素の HTML + ES Modules + Web Audio API(フロントエンド) / docker compose(OMR は Audiveris を別コンテナで分離)
