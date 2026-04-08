# Gr3njaDiscordBot
深夜テンションの開発室公式DiscordBot用のレポです。

Python 3.13 向けの Discord Bot です。以下をまとめて実装しています。

- しりとり
- 実績管理
- ロール管理
- イベント管理
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
4. Bot を起動します。

```powershell
py -3.13 -m gr3nja_discord_bot
```

## 必要な Intent

- `Message Content Intent`
- `Server Members Intent`
- `Voice States`

## 主なコマンド

接頭辞は既定で `!` です。

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
