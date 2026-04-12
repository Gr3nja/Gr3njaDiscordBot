# Gr3njaDiscordBot

深夜テンションの開発室向けの Discord Bot です。
Python 3.13 で動作し、SQLite を使ってサーバー設定や進行状況を保存します。

現在の主な機能は次のとおりです。

- しりとり
- 実績管理
- セルフロール管理
- ロールショップとサーバー通貨
- イベント管理
- カジノ
- Lavalink ベースの音楽再生
- AI チャットとモデル切り替え
- メッセージログ保存と会話要約
- 自由編集できる検知トリガー
- 自己紹介チャンネルの自動リアクション
- VC 発狂検知とクリップ送信
- `Ducky` 検知時の警告

## 動作要件

- Python `3.13` 以上
- Discord Bot Token
- AI 機能と要約機能を使う場合: OpenAI 互換 API
- 音楽機能を使う場合: Lavalink サーバー

## セットアップ

1. 依存関係をインストールします。

```powershell
py -3.13 -m pip install -e .
```

2. `.env.example` を元に `.env` を作成します。
3. 最低限 `DISCORD_TOKEN` を設定します。
4. AI チャットや要約を使う場合は `AI_BASE_URL` を設定します。
   OpenAI / OpenRouter / LM Studio / vLLM などの OpenAI 互換 API を想定しています。
   API キーが必要な環境では `AI_API_KEY` も設定してください。
5. 音楽機能を使う場合は `LAVALINK_HOST` / `LAVALINK_PORT` / `LAVALINK_PASSWORD` を設定します。
6. Bot を起動します。

```powershell
py -3.13 -m gr3nja_discord_bot
```

または install 後に次でも起動できます。

```powershell
gr3nja-bot
```

## 必要な Intent

- `Message Content Intent`
- `Server Members Intent`
- `Voice States`

## 主要な設定

`.env.example` に全項目があります。特に使うものは以下です。

- `BOT_PREFIX`
  既定の prefix。既定値は `!`
- `BOT_TIMEZONE`
  イベント表示やデイリー判定に使うタイムゾーン。既定値は `Asia/Tokyo`
- `DATABASE_PATH`
  SQLite DB の保存先
- `AI_DEFAULT_MODEL`
  サーバー既定の AI モデルキー。`gemini` / `gpt-oss:20b` / `gemma3:27b`
- `SUMMARY_LOG_RETENTION_DAYS`
  要約用メッセージログの保持日数
- `SUMMARY_DEFAULT_MESSAGE_COUNT`
  `summary recent` が既定で読む件数
- `SUMMARY_MAX_MESSAGE_COUNT`
  `summary recent` で指定できる上限件数
- `MUSIC_DEFAULT_SEARCH`
  `!play` の検索プレフィックス。既定値は `ytsearch`
- `MUSIC_IDLE_DISCONNECT_SECONDS`
  キューが空になってから切断するまでの秒数

## 主なコマンド

接頭辞の既定値は `!` です。
AI と要約は slash command と prefix command の両方に対応しています。

### AI

- `/ai chat <message>`
- `/ai model [modelname]`
- `!ai chat <message>`
- `!ai model [modelname]`

`/ai model` は引数なしで現在設定を表示します。
モデル変更はサーバー管理権限が必要です。

### 要約

- `/summary recent [count]`
- `!summary recent [count]`

現在のチャンネルの直近ログを要約します。
会話の流れ、主な話題、話題を最初に出した人、決まったこと、未解決事項を返します。

### しりとり

- `!shiritori start`
- `!shiritori stop`
- `!shiritori status`
- `!shiritori ranking`

ひらがな・カタカナ前提です。
漢字の読み推定までは行いません。

### 実績

- `!achievement catalog`
- `!achievement list [@member]`
- `!achievement leaderboard`
- `!achievement create <points> <icon> 名前 | 説明`
- `!achievement grant @member <id> [note]`
- `!achievement revoke @member <id>`

### 通貨・ロールショップ・セルフロール

- `!money [@member]`
- `!daily`
- `!role allow @Role`
- `!role disallow @Role`
- `!role list`
- `!role toggle @Role`
- `!shop currency 通貨名`
- `!shop add @Role <price> [description]`
- `!shop remove @Role`
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

作成時に `reward` を省略すると `EVENT_DEFAULT_REWARD` を使います。
開始前 60 分と 10 分で自動リマインドを送ります。

### カジノ

- `!highlow <bet> <high|low>`
- `!blackjack <bet>`
- `!blackjack hit`
- `!blackjack stand`
- `!blackjack cancel`
- `!hangman <bet>`
- `!hangman guess <letter|word>`
- `!hangman status`
- `!hangman stop`
- `!videopoker <bet>`
- `!videopoker hold 1 3 5`
- `!videopoker draw`
- `!videopoker status`
- `!videopoker cancel`

### 音楽

- `!play <keyword|url>`
- `!stop`

`!play` はキーワード検索と URL 再生に対応します。
既に再生中ならキューへ追加します。

### 自由編集トリガー

- `!trigger add <contains|exact|startswith|endswith|regex> キーワード | レスポンス`
- `!trigger list`
- `!trigger remove <id>`

### 自己紹介 / VC 監視

- `!config intro #channel [emoji]`
- `!voice channel [#channel]`
- `!voice watch [threshold]`
- `!voice stop`
- `!voice status`

`Ducky` を含むメッセージには `焼き鳥に修正してください` と返信します。

## AI 機能について

- OpenAI 互換 API の `chat/completions` を利用します。
- 選択できるモデルキーは `gemini` / `gpt-oss:20b` / `gemma3:27b` です。
- 実際に API へ送るモデル ID は `AI_MODEL_GEMINI` / `AI_MODEL_GPT_OSS_20B` / `AI_MODEL_GEMMA3_27B` で変更できます。
- 会話履歴は「ギルド・チャンネル・ユーザー」単位で保持します。
- slash command を使うには Bot 招待時に `applications.commands` スコープが必要です。
- slash command は起動時に同期します。反映が遅い場合は再起動してください。

## 要約機能について

- 通常メッセージは SQLite の `message_logs` テーブルに保存します。
- Bot メッセージと prefix コマンドは要約対象から除外します。
- `summary recent` は保存済みログが足りない場合、`SUMMARY_ENABLE_HISTORY_BACKFILL=true` なら Discord 履歴を読んで補完します。
- ログの保持期間は `SUMMARY_LOG_RETENTION_DAYS` で調整できます。
- 要約機能は AI 設定を流用するため、`AI_BASE_URL` が未設定だと利用できません。

## 音楽機能について

- Lavalink を利用します。Bot 本体とは別に Lavalink サーバーが必要です。
- 検索時の既定ソースは `MUSIC_DEFAULT_SEARCH` で切り替えられます。
- キューが空になると `MUSIC_IDLE_DISCONNECT_SECONDS` 後に自動切断します。
- 同じギルドで VC 監視が動作中に `!play` を実行すると、先に VC 監視を停止して音楽再生へ切り替えます。

### Lavalink の用意

最低限、Lavalink 側の `SERVER_PORT` と `LAVALINK_SERVER_PASSWORD` を Bot 側 `.env` と揃えてください。

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

## VC クリップについて

- `!voice watch` を実行した人が対象 VC に参加している必要があります。
- 音声受信には `discord-ext-voice-recv` を使います。
- Python 3.13 では `audioop` が削除されているため、依存に `audioop-lts` を含めています。
- クリップ送信先は `!voice channel #text-channel` で設定できます。
- `!voice channel` を引数なしで実行すると、現在の送信先を確認できます。
