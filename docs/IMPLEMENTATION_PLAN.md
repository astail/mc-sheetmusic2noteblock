# 実装順序と検証計画

## 実装フェーズ

### Phase 0: 足場(〜0.5日)

- リポジトリ初期化、`backend/Dockerfile`、`docker-compose.yml`
- FastAPI 起動、`/healthz`、frontend/ の静的配信、`data/` ボリューム確認
- **完了条件**: `docker compose up` → ブラウザで空ページが表示される

### Phase 1: 変換コア + API(MVP の心臓部)

1. `scripts/make_fixtures.py` でテストデータ生成(**先に作る = TDD の足場**)
2. `parser` → `hand_split` → `quantizer` → `pitch_mapper` → `blueprint_builder` → `materials` を単体テストと共に実装
3. `/api/scores`(MIDI/MusicXML/MXL)と `/api/scores/{id}/blueprint`

- **完了条件**: curl で MIDI を投げて Blueprint JSON スキーマ通りの設計書が返る

### Phase 2: フロントエンド(ここまでで MVP 完成)

- アップロード → 設定 → 設計書ビュー → プレビュー再生
- **完了条件**: きらきら星 MIDI をブラウザで変換し、ステップカードを見ながら合成音プレビューが量子化どおり鳴る

### Phase 3: 設計書の充実

- 物理レイアウト提案(`layout.py` + 簡易俯瞰図 SVG)
- 印刷 CSS、部分変換(小節範囲)、大和音警告の配線ガイド文
- リピーター総数が閾値超過時の「曲を分割して」提案

### Phase 4: OMR(実験的)

- `omr/` サービス: JRE 付きイメージに Audiveris をインストールし、`Audiveris -batch -export` を叩く薄い HTTP ラッパ
- 非同期ジョブ API + フロントの進捗表示
- 出力 .mxl は既存パイプラインへそのまま合流。精度免責の文言を UI に明示
- oemer は依存の重さから採用見送り(README に代替として記載)

### Phase 5(任意)

- 打楽器トラック対応(basedrum / snare / hat)
- 同一和音の音符ブロック再利用最適化
- カスタム音色レンジエディタ

## テスト戦略

### フィクスチャ(`make_fixtures.py` で music21 により生成)

| ファイル | 内容 | 検証対象 |
|---|---|---|
| `scale_c_major.musicxml` | 4分音符のドレミ8音 | 最小ケース |
| `twinkle_both_hands.musicxml` | 右手メロディ+左手和音、2譜表 | 手判別 |
| `twinkle.mid` | 同曲の MIDI 版 | トラック→手のフォールバック |
| `tempo_change.mid` | 途中で BPM 変化 | 警告と seconds モード |
| `extreme_range.mid` | A0 と C8 を含む | オクターブシフト警告 |
| `sixteenth_150bpm.mid` | 150BPM の16分音符 | 誤差ゼロ量子化 |

### 単体テスト(pytest)

- **quantizer**: 150BPM・tpq=4 で16分音符が誤差 0 で整数 tick に乗る / 90BPM 曲で tpq 推奨値と誤差統計が正しい / 同 tick 同音のデデュープ
- **pitch_mapper**: 境界値 MIDI 30・54・78・102 / A0 → シフト+警告 / clicks 計算(C4 = harp 6クリック)
- **blueprint_builder**: delay 7 → [4,3] / delay 12 → [4,4,4] / 先頭ステップの扱い
- **materials**: 個数集計の一致

### E2E

1. `docker compose up --build` → `/healthz` が 200
2. `curl -F file=@scale_c_major.musicxml /api/scores` → score_id とサマリ
3. `curl -X POST .../blueprint -d '{"ticks_per_quarter":4,...}'` → steps 数 = 8、全 delay = 4(= リピーター1個4目盛)、全音 harp、C4 = 6クリック…を数値でアサート
4. ブラウザで twinkle をアップロード → プレビュー再生 → 聴感でメロディ確認(Playwright MCP でアップロード〜再生ボタンまで自動化し console エラー無しを確認)
5. **実機スポットチェック(手動)**: 生成された設計書の冒頭8ステップを Paper サーバー(26.2 experimental)で実際に組み、プレビュー音と聴き比べる。**これが本プロダクトの最終受け入れ試験**

## 受け入れ基準

「**設計書だけを見てゲーム内で組めるか**」。具体的には、すべてのステップカードに以下の4点が常に揃っていること:

- (a) 前ステップからの遅延と**リピーター構成**(個数と目盛)
- (b) 音符ブロックの**下に置くブロックの日本語名**
- (c) **クリック回数**(0〜24)
- (d) **右手/左手の別**(同時に鳴らす音の組が分かること)
