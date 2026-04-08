from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

import discord
from discord.ext import commands

from .cards import Card, blackjack_value, evaluate_video_poker, format_cards, new_deck


HANGMAN_WORDS = [
    "discord",
    "yakitori",
    "python",
    "grenja",
    "casino",
    "kiritori",
    "botmaker",
    "voicechat",
    "achievement",
    "eventnight",
]


@dataclass(slots=True)
class BlackjackSession:
    bet: int
    deck: list[Card]
    player_hand: list[Card]
    dealer_hand: list[Card]


@dataclass(slots=True)
class HangmanSession:
    bet: int
    word: str
    guessed: set[str] = field(default_factory=set)
    misses: set[str] = field(default_factory=set)


@dataclass(slots=True)
class VideoPokerSession:
    bet: int
    deck: list[Card]
    hand: list[Card]
    held_indexes: set[int] = field(default_factory=set)


class CasinoCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot
        self.blackjack_sessions: dict[tuple[int, int], BlackjackSession] = {}
        self.hangman_sessions: dict[tuple[int, int], HangmanSession] = {}
        self.video_poker_sessions: dict[tuple[int, int], VideoPokerSession] = {}

    @commands.command(name="highlow")
    @commands.guild_only()
    async def highlow(self, ctx: commands.Context, bet: int, guess: str) -> None:
        currency = await self.bot.economy.get_currency_name(ctx.guild.id)
        normalized = guess.casefold()
        if normalized not in {"high", "low"}:
            await ctx.send("予想は `high` か `low` を指定してください。")
            return
        if not await self._take_bet(ctx, bet, currency):
            return

        deck = new_deck()
        first = deck.pop()
        second = deck.pop()
        first_value = self._highlow_value(first.rank)
        second_value = self._highlow_value(second.rank)
        payout = 0
        won = False
        if second_value == first_value:
            payout = bet
            summary = "同値だったので引き分けです。"
        else:
            won = (normalized == "high" and second_value > first_value) or (
                normalized == "low" and second_value < first_value
            )
            if won:
                payout = bet * 2
                summary = "的中しました。"
            else:
                summary = "外れました。"

        await self._settle_game(
            ctx,
            bet=bet,
            payout=payout,
            won=won,
            summary=f"1枚目: {first.label} / 2枚目: {second.label}\n{summary}",
        )

    @commands.group(name="blackjack", invoke_without_command=True)
    @commands.guild_only()
    async def blackjack_group(self, ctx: commands.Context, bet: int | None = None) -> None:
        if bet is None:
            await ctx.send("開始は `!blackjack 100`、続行は `!blackjack hit` / `!blackjack stand` です。")
            return

        key = self._key(ctx)
        if key in self.blackjack_sessions:
            await ctx.send("既に進行中のブラックジャックがあります。")
            return

        currency = await self.bot.economy.get_currency_name(ctx.guild.id)
        if not await self._take_bet(ctx, bet, currency):
            return

        deck = new_deck()
        session = BlackjackSession(
            bet=bet,
            deck=deck,
            player_hand=[deck.pop(), deck.pop()],
            dealer_hand=[deck.pop(), deck.pop()],
        )
        self.blackjack_sessions[key] = session

        player_total = blackjack_value(session.player_hand)
        dealer_total = blackjack_value(session.dealer_hand)
        if player_total == 21:
            self.blackjack_sessions.pop(key, None)
            if dealer_total == 21:
                payout = bet
                summary = "両者ブラックジャックで引き分けです。"
                won = False
            else:
                payout = bet * 5 // 2
                summary = "ナチュラルブラックジャックです。"
                won = True
            await self._settle_game(
                ctx,
                bet=bet,
                payout=payout,
                won=won,
                summary=(
                    f"あなた: {format_cards(session.player_hand)} ({player_total})\n"
                    f"ディーラー: {format_cards(session.dealer_hand)} ({dealer_total})\n"
                    f"{summary}"
                ),
            )
            return

        await ctx.send(
            f"ブラックジャック開始\n"
            f"あなた: {format_cards(session.player_hand)} ({player_total})\n"
            f"ディーラー: {session.dealer_hand[0].label} ??\n"
            "続行: `!blackjack hit` / `!blackjack stand`"
        )

    @blackjack_group.command(name="hit")
    async def blackjack_hit(self, ctx: commands.Context) -> None:
        key = self._key(ctx)
        session = self.blackjack_sessions.get(key)
        if session is None:
            await ctx.send("進行中のブラックジャックがありません。")
            return

        session.player_hand.append(session.deck.pop())
        total = blackjack_value(session.player_hand)
        if total > 21:
            self.blackjack_sessions.pop(key, None)
            await self._settle_game(
                ctx,
                bet=session.bet,
                payout=0,
                won=False,
                summary=f"あなた: {format_cards(session.player_hand)} ({total})\nバーストしました。",
            )
            return

        await ctx.send(f"あなた: {format_cards(session.player_hand)} ({total})\n続行: `!blackjack hit` / `!blackjack stand`")

    @blackjack_group.command(name="stand")
    async def blackjack_stand(self, ctx: commands.Context) -> None:
        key = self._key(ctx)
        session = self.blackjack_sessions.pop(key, None)
        if session is None:
            await ctx.send("進行中のブラックジャックがありません。")
            return

        while blackjack_value(session.dealer_hand) < 17:
            session.dealer_hand.append(session.deck.pop())

        player_total = blackjack_value(session.player_hand)
        dealer_total = blackjack_value(session.dealer_hand)
        if dealer_total > 21 or player_total > dealer_total:
            payout = session.bet * 2
            won = True
            summary = "勝ちです。"
        elif player_total == dealer_total:
            payout = session.bet
            won = False
            summary = "引き分けです。"
        else:
            payout = 0
            won = False
            summary = "負けです。"

        await self._settle_game(
            ctx,
            bet=session.bet,
            payout=payout,
            won=won,
            summary=(
                f"あなた: {format_cards(session.player_hand)} ({player_total})\n"
                f"ディーラー: {format_cards(session.dealer_hand)} ({dealer_total})\n"
                f"{summary}"
            ),
        )

    @blackjack_group.command(name="cancel")
    async def blackjack_cancel(self, ctx: commands.Context) -> None:
        removed = self.blackjack_sessions.pop(self._key(ctx), None)
        if removed is None:
            await ctx.send("進行中のブラックジャックがありません。")
            return
        await ctx.send("ブラックジャックを放棄しました。")

    @commands.group(name="hangman", invoke_without_command=True)
    @commands.guild_only()
    async def hangman_group(self, ctx: commands.Context, bet: int | None = None) -> None:
        if bet is None:
            await ctx.send("開始は `!hangman 100`、続行は `!hangman guess a` です。")
            return

        key = self._key(ctx)
        if key in self.hangman_sessions:
            await ctx.send("既に進行中の HangMan があります。")
            return

        currency = await self.bot.economy.get_currency_name(ctx.guild.id)
        if not await self._take_bet(ctx, bet, currency):
            return

        word = random.choice(HANGMAN_WORDS)
        session = HangmanSession(bet=bet, word=word)
        self.hangman_sessions[key] = session
        await ctx.send(f"HangMan 開始: `{self._hangman_mask(session)}`\n推測: `!hangman guess <文字 or 単語>`")

    @hangman_group.command(name="guess")
    async def hangman_guess(self, ctx: commands.Context, *, guess: str) -> None:
        key = self._key(ctx)
        session = self.hangman_sessions.get(key)
        if session is None:
            await ctx.send("進行中の HangMan がありません。")
            return

        guess = guess.casefold().strip()
        if not re.fullmatch(r"[a-z]+", guess):
            await ctx.send("英字で推測してください。")
            return

        if len(guess) == 1:
            if guess in session.guessed or guess in session.misses:
                await ctx.send("その文字は既に試しています。")
                return
            if guess in session.word:
                session.guessed.add(guess)
            else:
                session.misses.add(guess)
        else:
            if guess == session.word:
                session.guessed.update(set(session.word))
            else:
                session.misses.add(guess)

        if set(session.word).issubset(session.guessed):
            self.hangman_sessions.pop(key, None)
            payout = session.bet * 3
            await self._settle_game(
                ctx,
                bet=session.bet,
                payout=payout,
                won=True,
                summary=f"正解です。単語: `{session.word}`",
            )
            return

        if len(session.misses) >= 6:
            self.hangman_sessions.pop(key, None)
            await self._settle_game(
                ctx,
                bet=session.bet,
                payout=0,
                won=False,
                summary=f"ゲームオーバーです。単語: `{session.word}`",
            )
            return

        await ctx.send(f"`{self._hangman_mask(session)}` / miss: `{', '.join(sorted(session.misses)) or '-'}` ({len(session.misses)}/6)")

    @hangman_group.command(name="status")
    async def hangman_status(self, ctx: commands.Context) -> None:
        session = self.hangman_sessions.get(self._key(ctx))
        if session is None:
            await ctx.send("進行中の HangMan がありません。")
            return
        await ctx.send(f"`{self._hangman_mask(session)}` / miss: `{', '.join(sorted(session.misses)) or '-'}` ({len(session.misses)}/6)")

    @hangman_group.command(name="stop")
    async def hangman_stop(self, ctx: commands.Context) -> None:
        removed = self.hangman_sessions.pop(self._key(ctx), None)
        if removed is None:
            await ctx.send("進行中の HangMan がありません。")
            return
        await ctx.send(f"HangMan を中断しました。答え: `{removed.word}`")

    @commands.group(name="videopoker", invoke_without_command=True)
    @commands.guild_only()
    async def video_poker_group(self, ctx: commands.Context, bet: int | None = None) -> None:
        if bet is None:
            await ctx.send("開始は `!videopoker 100`、保持は `!videopoker hold 1 3 5`、確定は `!videopoker draw` です。")
            return

        key = self._key(ctx)
        if key in self.video_poker_sessions:
            await ctx.send("既に進行中の VideoPoker があります。")
            return

        currency = await self.bot.economy.get_currency_name(ctx.guild.id)
        if not await self._take_bet(ctx, bet, currency):
            return

        deck = new_deck()
        hand = [deck.pop() for _ in range(5)]
        self.video_poker_sessions[key] = VideoPokerSession(bet=bet, deck=deck, hand=hand)
        await ctx.send(
            "VideoPoker 開始\n"
            f"{self._format_hand_with_indexes(hand)}\n"
            "保持: `!videopoker hold 1 3 5` / 確定: `!videopoker draw`"
        )

    @video_poker_group.command(name="hold")
    async def video_poker_hold(self, ctx: commands.Context, *positions: int) -> None:
        session = self.video_poker_sessions.get(self._key(ctx))
        if session is None:
            await ctx.send("進行中の VideoPoker がありません。")
            return
        invalid = [position for position in positions if position < 1 or position > 5]
        if invalid:
            await ctx.send("保持位置は 1 から 5 の範囲で指定してください。")
            return

        session.held_indexes = {position - 1 for position in positions}
        held_labels = ", ".join(str(position) for position in sorted(positions)) or "なし"
        await ctx.send(f"保持位置: {held_labels}\n{self._format_hand_with_indexes(session.hand, session.held_indexes)}")

    @video_poker_group.command(name="draw")
    async def video_poker_draw(self, ctx: commands.Context) -> None:
        key = self._key(ctx)
        session = self.video_poker_sessions.pop(key, None)
        if session is None:
            await ctx.send("進行中の VideoPoker がありません。")
            return

        for index in range(5):
            if index not in session.held_indexes:
                session.hand[index] = session.deck.pop()

        hand_name, multiplier = evaluate_video_poker(session.hand)
        payout = session.bet * multiplier
        await self._settle_game(
            ctx,
            bet=session.bet,
            payout=payout,
            won=multiplier > 0,
            summary=f"{self._format_hand_with_indexes(session.hand)}\n結果: **{hand_name}**",
        )

    @video_poker_group.command(name="status")
    async def video_poker_status(self, ctx: commands.Context) -> None:
        session = self.video_poker_sessions.get(self._key(ctx))
        if session is None:
            await ctx.send("進行中の VideoPoker がありません。")
            return
        await ctx.send(self._format_hand_with_indexes(session.hand, session.held_indexes))

    @video_poker_group.command(name="cancel")
    async def video_poker_cancel(self, ctx: commands.Context) -> None:
        removed = self.video_poker_sessions.pop(self._key(ctx), None)
        if removed is None:
            await ctx.send("進行中の VideoPoker がありません。")
            return
        await ctx.send("VideoPoker を放棄しました。")

    def _key(self, ctx: commands.Context) -> tuple[int, int]:
        return (ctx.guild.id, ctx.author.id)

    def _highlow_value(self, rank: str) -> int:
        if rank == "A":
            return 14
        if rank == "K":
            return 13
        if rank == "Q":
            return 12
        if rank == "J":
            return 11
        return int(rank)

    def _hangman_mask(self, session: HangmanSession) -> str:
        return " ".join(character if character in session.guessed else "_" for character in session.word)

    def _format_hand_with_indexes(self, cards: list[Card], held_indexes: set[int] | None = None) -> str:
        held_indexes = held_indexes or set()
        return " ".join(
            f"{index}:{card.label}{'*' if (index - 1) in held_indexes else ''}"
            for index, card in enumerate(cards, start=1)
        )

    async def _take_bet(self, ctx: commands.Context, bet: int, currency: str) -> bool:
        if bet <= 0:
            await ctx.send("賭け金は 1 以上で指定してください。")
            return False
        paid, wallet = await self.bot.economy.spend_balance(ctx.guild.id, ctx.author.id, bet)
        if not paid:
            await ctx.send(f"残高不足です。必要: {bet} {currency} / 現在: {wallet.balance} {currency}")
            return False
        return True

    async def _settle_game(
        self,
        ctx: commands.Context,
        *,
        bet: int,
        payout: int,
        won: bool,
        summary: str,
    ) -> None:
        if payout > 0:
            wallet = await self.bot.economy.add_balance(ctx.guild.id, ctx.author.id, payout)
        else:
            wallet = await self.bot.economy.get_wallet(ctx.guild.id, ctx.author.id)

        awards = await self.bot.achievements.record_casino_game(ctx.guild.id, ctx.author.id, won=won)
        currency = await self.bot.economy.get_currency_name(ctx.guild.id)
        await ctx.send(
            f"{summary}\n"
            f"ベット: {bet} {currency} / 払い戻し: {payout} {currency}\n"
            f"現在残高: {wallet.balance} {currency}"
        )
        await self.bot.announce_achievements(ctx.channel, ctx.author, awards)


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(CasinoCog(bot))
