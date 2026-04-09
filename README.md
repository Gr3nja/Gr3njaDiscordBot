# Gr3njaDiscordBot
深夜テンションの開発室公式DiscordBot用のレポです。

Python 3.13 向けの Discord Bot です。以下をまとめて実装しています。

- しりとり
- 実績管理
- ロール管理
- イベント管理
- Lavalink ベースの音楽再生
- AI チャットとモデル切り替え
- `Ducky` 検知時の警告
- 自己紹介チャンネルの自動リアクション
- VC 発狂検知とクリップ送信
- サーバー通貨とロール購入
- カジノ機能
- 自由編集できる検知トリガー

## セットアップ

1. Python 3.13 を使います。
2. 依存関係を入れます。

```powershell
py -3.13 -m pip install -e .
```

3. `.env.example` を参考に `.env` を作成し、`DISCORD_TOKEN` を設定します。
4. AI 機能を使う場合は `AI_BASE_URL` を設定します。
   OpenAI 互換 API を想定しているため、OpenAI / OpenRouter / LM Studio / vLLM などでも使えます。
   API キー不要のローカル推論サーバー以外では `AI_API_KEY` も設定してください。
   AI の選択肢は `gemini` / `gpt-oss:20b` / `gemma3:27b` の 3 種類です。
   実APIモデル名を変えたい場合は `AI_MODEL_GEMINI` / `AI_MODEL_GPT_OSS_20B` / `AI_MODEL_GEMMA3_27B` を編集してください。
5. 音楽機能を使う場合は、別途 Lavalink サーバーを起動して `LAVALINK_HOST` / `LAVALINK_PORT` / `LAVALINK_PASSWORD` を設定します。
6. Bot を起動します。

```powershell
py -3.13 -m gr3nja_discord_bot
```

## 必要な Intent

- `Message Content Intent`
- `Server Members Intent`
- `Voice States`

## 主なコマンド

接頭辞は既定で `!` です。
`/ai ...` は slash command、`!ai ...` は prefix command として使えます。

### しりとり

- `!shiritori start`
- `!shiritori stop`
- `!shiritori status`
- `!shiritori ranking`

ひらがな・カタカナ前提です。漢字の読み推定までは行いません。

### 実績

- `!achievement catalog`
- `!achievement list [@member]`
- `!achievement leaderboard`
- `!achievement create <points> <icon> 名前 | 説明`
- `!achievement grant @member <id>`

### ロールと通貨

- `!money [@member]`
- `!daily`
- `!role allow @Role`
- `!role disallow @Role`
- `!role toggle @Role`
- `!shop currency 通貨名`
- `!shop add @Role <price> [description]`
- `!shop list`
- `!shop buy @Role`

### イベント

- `!event create <YYYY-MM-DDTHH:MM> <reward> <max> タイトル | 説明`
- `!event list`
- `!event info <id>`
- `!event join <id>`
- `!event leave <id>`
- `!event cancel <id>`
- `!event complete <id>`

### カジノ

- `!highlow <bet> <high|low>`
- `!blackjack <bet>`
- `!blackjack hit`
- `!blackjack stand`
- `!hangman <bet>`
- `!hangman guess <letter|word>`
- `!videopoker <bet>`
- `!videopoker hold 1 3 5`
- `!videopoker draw`

### 音楽

- `!play <keyword|url>`
- `!stop`

`!play` はキーワード検索または URL 再生に対応します。
再生中に `!play` を実行するとキューへ追加します。

### AI

- `/ai chat <message>`
- `/ai model [modelname]`
- `!ai chat <message>`
- `!ai model [modelname]`

`/ai model` はモデル名を省略すると現在値を表示します。
指定できるモデルは `gemini` / `gpt-oss:20b` / `gemma3:27b` だけです。
モデル変更はサーバー管理権限が必要です。
会話履歴は「サーバー・チャンネル・ユーザー」単位で保持されます。

### 自由編集トリガー

- `!trigger add <contains|exact|startswith|endswith|regex> キーワード | レスポンス`
- `!trigger list`
- `!trigger remove <id>`

### 自己紹介 / VC 設定

- `!config intro #channel 🤝`
- `!voice channel #clips`
- `!voice watch [threshold]`
- `!voice stop`
- `!voice status`

`Ducky` を含むメッセージには `焼き鳥に修正してください` と返信します。

## VC クリップについて

- Bot が対象 VC に参加している必要があります。`!voice watch` で監視開始します。
- Discord 側の音声受信拡張を使います。
- Python 3.13 では `audioop` が削除されているため、依存に `audioop-lts` を含めています。
- クリップ送信先は `!voice channel` で変更できます。

## 音楽機能について

- 音楽再生は Lavalink を利用します。Bot 本体とは別に Lavalink サーバーが必要です。
- キーワード検索は `MUSIC_DEFAULT_SEARCH` で切り替えられます。既定値は `ytsearch` です。
- キューが空になると `MUSIC_IDLE_DISCONNECT_SECONDS` 後に自動切断します。
- 既に VC 監視が動作中のサーバーで `!play` を使うと、先に VC 監視を停止してから音楽再生へ切り替えます。

### Lavalink の用意

Lavalink 公式ドキュメントどおり、Docker で別コンテナとして起動できます。最低限 `SERVER_PORT` と `LAVALINK_SERVER_PASSWORD` を合わせて、Bot 側の `.env` に同じ接続情報を設定してください。

```yaml
services:
  lavalink:
    image: ghcr.io/lavalink-devs/lavalink:4-alpine
    restart: unless-stopped
    environment:
      - SERVER_PORT=2333
      - LAVALINK_SERVER_PASSWORD=youshallnotpass
    ports:
      - "2333:2333"
```

## AI 機能について

- `/ai chat` は OpenAI 互換の `chat/completions` API を利用します。
- 選択できる AI は `Gemini` / `gpt-oss:20b` / `Gemma3:27b` の 3 種類です。
- `.env` の `AI_DEFAULT_MODEL` をサーバー既定として使い、`/ai model` でギルド単位に上書きできます。
- 実際に API へ送るモデル ID は `AI_MODEL_GEMINI` / `AI_MODEL_GPT_OSS_20B` / `AI_MODEL_GEMMA3_27B` で調整できます。
- slash command を使うには Bot の招待に `applications.commands` スコープが必要です。
- slash command は起動時に同期します。反映に少し時間がかかる場合は Bot を再起動してください。
