# Audiveris OMR コンテナ

PDF・楽譜画像を MusicXML に変換する Audiveris の HTTP サービスです。既定起動では
FastAPI/Uvicorn が 8080 番ポートで待ち受けます。同時に受け付ける変換は1件だけで、
実行中の追加リクエストはアップロードを解析せず `SERVICE_BUSY` の 503 を即時返却します。

## 起動

```bash
docker compose --profile omr up --build -d omr
docker compose ps omr
```

`healthy` になれば Java、Audiveris のネイティブ依存、HTTP API が利用できます。
8080 は compose ネットワーク内にのみ公開され、ホストには publish されません。

## HTTP API

`POST /transcribe` の `file` フィールドに PDF、PNG、JPG/JPEG のいずれか1ファイルを
multipart/form-data で渡します。最大サイズは 25 MiB です。成功時は
`application/vnd.recordare.musicxml+xml` の `.mxl` を返します。

```bash
curl --fail --form file=@score.png \
  --output transcription.mxl http://localhost:8080/transcribe
```

ホストから試す場合は一時的に compose の `omr` service に `ports: ["8080:8080"]` を
追加してください。`GET /healthz` は `{"status":"ok"}` を返します。

エラーは常に次の固定形式で、Audiveris のログ、作業パス、アップロード名を応答へ
含めません。

```json
{"error":{"code":"TRANSCRIPTION_FAILED","message":"The score could not be transcribed."}}
```

アップロードと出力はリクエストごとの隔離された一時ディレクトリで処理し、応答完了後に
削除します。タイムアウト時やサーバー停止時は Audiveris のプロセスグループへ TERM を送り、
猶予時間後も残っていれば KILL します。次の環境変数で調整できます。

- `OMR_TRANSCRIBE_TIMEOUT_SECONDS`（既定 300 秒）
- `OMR_PROCESS_TERM_GRACE_SECONDS`（既定 2 秒）
- `OMR_GRACEFUL_SHUTDOWN_SECONDS`（既定 3 秒）
- `AUDIVERIS_MIN_HEAP` / `AUDIVERIS_MAX_HEAP`（Java ヒープ）

Compose の `stop_grace_period` は、Uvicorn の3秒と子プロセスの2秒にcleanupの余裕を
加えた10秒です。

既存のCLIも、コマンドを明示すれば利用できます。

```bash
docker compose --profile omr run --rm omr \
  Audiveris -batch -export -output /data/output -- /data/score.png
```

公式 installer に OCR 言語データは含まれません。言語データが未導入でも楽譜認識と
MusicXML export は動作しますが、歌詞などの文字認識には Tesseract の対応言語データを
追加する必要があります。

## 検証

公式 5.11.0 の小さなサンプル画像を使い、build、単体テスト、HTTP 経由の MusicXML export、
MXL ZIP 検証、compose の healthcheck、graceful stop、専用 Compose project の完全な
cleanup に加え、TERM を無視する実行中の fake Audiveris が wrapper の TERM→KILL で
終了して一時workspaceが空になることを一括確認できます。検証は PID を含む一意な
project 名で実行されるため、
同じ checkout で起動中の通常の `omr` service や image には影響しません。検証用の
container、network、image は完了時にすべて削除されます。

```bash
./omr/validate.sh
```

## 配布物と互換性

- Audiveris 5.11.0 の公式 Ubuntu 24.04 x86_64 `.deb` を、URL・SHA-256
  (`f20113aaa33b3149ec8d6a09b2a7963360e65fafd92d69389987a85bbc3ec7a3`)
  とも固定して使用します。
- Audiveris 5.11.0 が要求する Java 25 の JRE ベースです。公式 installer
  同梱 JRE は除き、ベースイメージの JRE を利用して重複を避けています。
- 公式 Linux 配布物は x86_64 のみです。compose は `linux/amd64` を明示しており、
  ARM ホストではエミュレーションが必要です。
- HTTP ランタイムは FastAPI 0.139.2、Uvicorn 0.41.0、python-multipart 0.0.32 を
  `requirements.txt` で固定しています。
- Python と HTTP 依存を含む amd64 runtime image の実測サイズは 228,090,154 bytes
  （約 217.5 MiB）です。`docker image ls` の表示は共有レイヤーの計上方法により
  異なるため、比較時は `docker image inspect <image> --format '{{.Size}}'` を使用します。
- Audiveris は
  [AGPL-3.0-only](https://github.com/Audiveris/audiveris/blob/5.11.0/LICENSE)
  で配布されています。対応するソースは
  [公式 5.11.0 タグ](https://github.com/Audiveris/audiveris/tree/5.11.0)
  から取得できます。
