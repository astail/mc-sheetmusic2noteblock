# Audiveris OMR コンテナ

PDF・楽譜画像を MusicXML に変換する Audiveris のバッチ実行環境です。
HTTP API は issue #41 で追加するため、現時点の既定コマンドは CLI のロード確認後に
コンテナを継続起動します。

## 起動

```bash
docker compose --profile omr up --build -d omr
docker compose ps omr
```

`healthy` になれば Java と Audiveris のネイティブ依存をロードできています。
8080 は compose ネットワーク内にのみ公開され、ホストには publish されません。

## バッチ変換

入力ファイルを `./data` に置き、単発コンテナで実行します。

```bash
docker compose --profile omr run --rm omr \
  Audiveris -batch -export -output /data/output -- /data/score.png
```

出力は `./data/output/*.mxl` です。`AUDIVERIS_MIN_HEAP` と
`AUDIVERIS_MAX_HEAP` で Java ヒープを調整できます。

公式 installer に OCR 言語データは含まれません。言語データが未導入でも楽譜認識と
MusicXML export は動作しますが、歌詞などの文字認識には Tesseract の対応言語データを
追加する必要があります。

## 検証

公式 5.11.0 の小さなサンプル画像を使い、build、CLI、実際の MusicXML export、
compose の healthcheck、2 秒未満の graceful stop、専用 Compose project の完全な
cleanup を一括確認できます。検証は PID を含む一意な project 名で実行されるため、
同じ checkout で起動中の通常の `omr` service には影響しません。

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
- amd64 検証環境では `docker image inspect issue-40-omr:latest
  --format '{{.Size}}'` が 204,427,493 bytes（約 195 MiB）でした。同じ image でも
  Docker 29 の `docker image ls` は共有レイヤー込みで 767 MB、
  `docker system df -v` は shared 426 MB / unique 340.8 MB と表示します。
  ストレージドライバーと共有レイヤーの計上方法で値が異なるため、ディスク使用量は
  `docker system df -v` も併せて確認してください。
- Audiveris は
  [AGPL-3.0-only](https://github.com/Audiveris/audiveris/blob/5.11.0/LICENSE)
  で配布されています。対応するソースは
  [公式 5.11.0 タグ](https://github.com/Audiveris/audiveris/tree/5.11.0)
  から取得できます。
