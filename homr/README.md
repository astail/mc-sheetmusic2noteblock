# homr OMR コンテナ

PDF・楽譜画像を MusicXML に変換する [homr](https://github.com/liebharc/homr)(ディープ
ラーニングベースの OMR)の HTTP サービスです。既定起動では FastAPI/Uvicorn が 8080 番
ポートで待ち受けます。同時に受け付ける変換は1件だけで、実行中の追加リクエストは
アップロードを解析せず `SERVICE_BUSY` の 503 を即時返却します。

homr は画像入力のみ対応(PDF非対応)のため、PDFは本ラッパーが PyMuPDF で各ページを
PNG にラスタライズしてから1ページずつ homr へ渡します。Audiveris ベースの OMR
([../omr](../omr))と異なりグランド譜表(両手ピアノ)のブレース検出を主要機能として
設計されており、右手/左手の分離に強い傾向があります。

## 起動

```bash
docker compose --profile homr up --build -d homr
docker compose ps homr
```

`healthy` になれば homr のモデル、HTTP API が利用できます。8080 は compose ネットワーク
内にのみ公開され、ホストには publish されません。

## HTTP API

`POST /transcribe` の `file` フィールドに PDF、PNG、JPG/JPEG のいずれか1ファイルを
multipart/form-data で渡します。最大サイズは 25 MiB です。1ページ(画像、または1ページ
のPDF)の場合は `application/vnd.recordare.musicxml+xml` の `.mxl` を返します。PDFが
複数ページの場合は各ページの `.mxl` (`page_0.mxl`, `page_1.mxl`, ...)を束ねた
`application/zip` を返します(Audiveris ベースのラッパーが複数ページ誤認識時に返す
形式と同じ契約なので、アプリ側は使うOMRエンジンを意識せずに済みます)。

```bash
curl --fail --form file=@score.png \
  --output transcription.mxl http://localhost:8080/transcribe
```

ホストから試す場合は一時的に compose の `homr` service に `ports: ["8080:8080"]` を
追加してください。`GET /healthz` は `{"status":"ok"}` を返します。

エラーは常に次の固定形式で、homr のログ、作業パス、アップロード名を応答へ含めません。

```json
{"error":{"code":"TRANSCRIPTION_FAILED","message":"The score could not be transcribed."}}
```

アップロードと出力はリクエストごとの隔離された一時ディレクトリで処理し、応答完了後に
削除します。タイムアウト時やサーバー停止時は homr のプロセスグループへ TERM を送り、
猶予時間後も残っていれば KILL します。次の環境変数で調整できます(タイムアウトは
1ページごとに適用されるため、複数ページのPDFでもページ数に応じて自然にスケールします)。

- `OMR_TRANSCRIBE_TIMEOUT_SECONDS`(既定 300 秒、1ページあたり)
- `OMR_PROCESS_TERM_GRACE_SECONDS`(既定 2 秒)
- `OMR_GRACEFUL_SHUTDOWN_SECONDS`(既定 3 秒)

Compose の `stop_grace_period` は、Uvicorn の3秒と子プロセスの2秒にcleanupの余裕を
加えた10秒です。

## 検証

```bash
docker build --target test -t mc-sheetmusic2jukebox-homr:test-suite ./homr
docker run --rm mc-sheetmusic2jukebox-homr:test-suite
```

fake の `homr` コマンド(`tests/fake_homr.py`)に差し替えて、単体テスト・複数ページPDF
のラスタライズ&バンドル・タイムアウト・busy応答・graceful stop等を検証します。

## 配布物と互換性

- [homr](https://github.com/liebharc/homr) 0.7.0 を PyPI から `pip install` します。
  Python 3.11-3.15 対応。CPU推論のみでも動作します(GPU任意)。
- モデル重み(~180MB、初回のみダウンロードが必要)はビルド時(`homr --init`)に
  取得し、コンテナ起動のたびにダウンロードしないようにしています。
- `opencv-python-headless`(homrの依存)がDebian slim上で動くために `libgl1` /
  `libglib2.0-0` / `libxcb1` / `libsm6` / `libxext6` をインストールしています。
- PDFラスタライズには [PyMuPDF](https://pypi.org/project/PyMuPDF/) 1.28.0 を使用し、
  300 DPI 相当(Audiverisの推奨値に合わせた値)でページ画像を生成します。
- HTTP ランタイムは FastAPI 0.139.2、Uvicorn 0.41.0、python-multipart 0.0.32 を
  `requirements.txt` で固定しています。
- homr は
  [AGPL-3.0](https://github.com/liebharc/homr/blob/main/LICENSE)
  で配布されています(Audiverisと同じライセンス)。
