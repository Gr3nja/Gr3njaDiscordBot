from __future__ import annotations

import re

import discord
from discord.ext import commands


MATCH_TYPES = {"contains", "exact", "startswith", "endswith", "regex"}


class RuleCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def trigger_listener(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if not message.content.strip() or message.content.startswith(self.bot.config.prefix):
            return
        if "ducky" in message.content.casefold():
            return
        await self._fire_trigger(message)

    async def _fire_trigger(self, message: discord.Message) -> None:
        rows = await self.bot.db.fetchall(
            """
            SELECT id, keyword, response, match_type
            FROM trigger_rules
            WHERE guild_id = ?
            ORDER BY id ASC
            """,
            (message.guild.id,),
        )
        haystack = message.content.casefold()
        for row in rows:
            if self._match_trigger(row["match_type"], row["keyword"], haystack, message.content):
                await message.channel.send(row["response"])
                break

    @staticmethod
    def _match_trigger(match_type: str, keyword: str, folded_haystack: str, raw_haystack: str) -> bool:
        folded_keyword = keyword.casefold()
        if match_type == "contains":
            return folded_keyword in folded_haystack
        if match_type == "exact":
            return folded_haystack == folded_keyword
        if match_type == "startswith":
            return folded_haystack.startswith(folded_keyword)
        if match_type == "endswith":
            return folded_haystack.endswith(folded_keyword)
        if match_type == "regex":
            return re.search(keyword, raw_haystack, flags=re.IGNORECASE) is not None
        return False

    @commands.group(name="trigger", invoke_without_command=True)
    @commands.guild_only()
    async def trigger_group(self, ctx: commands.Context) -> None:
        await ctx.send("`add` `list` `remove` を使えます。例: `!trigger add contains 焼き鳥 | おいしい`")

    @trigger_group.command(name="add")
    async def trigger_add(self, ctx: commands.Context, match_type: str, *, payload: str) -> None:
        match_type = match_type.casefold()
        if match_type not in MATCH_TYPES:
            await ctx.send(f"match_type は {', '.join(sorted(MATCH_TYPES))} のどれかを指定してください。")
            return

        keyword, separator, response = payload.partition("|")
        keyword = keyword.strip()
        response = response.strip()
        if not separator or not keyword or not response:
            await ctx.send("形式: `!trigger add <type> キーワード | レスポンス`")
            return

        if match_type == "regex":
            try:
                re.compile(keyword)
            except re.error as exc:
                await ctx.send(f"正規表現が不正です: `{exc}`")
                return

        await self.bot.db.execute(
            """
            INSERT INTO trigger_rules (guild_id, match_type, keyword, response, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ctx.guild.id, match_type, keyword, response, ctx.author.id),
        )
        awards = await self.bot.achievements.record_trigger_creation(ctx.guild.id, ctx.author.id)
        await ctx.send(f"トリガーを追加しました: `{match_type}` / `{keyword}` -> `{response}`")
        await self.bot.announce_achievements(ctx.channel, ctx.author, awards)

    @trigger_group.command(name="list")
    async def trigger_list(self, ctx: commands.Context) -> None:
        rows = await self.bot.db.fetchall(
            """
            SELECT id, match_type, keyword, response, created_by
            FROM trigger_rules
            WHERE guild_id = ?
            ORDER BY id ASC
            """,
            (ctx.guild.id,),
        )
        if not rows:
            await ctx.send("トリガーはまだありません。")
            return

        lines = [
            f"`{row['id']}` [{row['match_type']}] `{row['keyword']}` -> `{row['response']}` (by <@{row['created_by']}>)"
            for row in rows[:20]
        ]
        if len(rows) > 20:
            lines.append(f"... and {len(rows) - 20} more")
        await ctx.send("\n".join(lines))

    @trigger_group.command(name="remove")
    async def trigger_remove(self, ctx: commands.Context, trigger_id: int) -> None:
        cursor = await self.bot.db.execute(
            "DELETE FROM trigger_rules WHERE guild_id = ? AND id = ?",
            (ctx.guild.id, trigger_id),
        )
        if cursor.rowcount == 0:
            await ctx.send("その ID のトリガーは見つかりませんでした。")
            return
        await ctx.send(f"トリガー `{trigger_id}` を削除しました。")


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(RuleCog(bot))
