from __future__ import annotations

import discord
from discord.ext import commands


class AchievementCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    @commands.group(name="achievement", aliases=["achievements"], invoke_without_command=True)
    @commands.guild_only()
    async def achievement_group(self, ctx: commands.Context) -> None:
        await ctx.send("`catalog` `list` `leaderboard` `create` `grant` `revoke` が使えます。")

    @achievement_group.command(name="catalog")
    async def achievement_catalog(self, ctx: commands.Context) -> None:
        rows = await self.bot.achievements.list_definitions(ctx.guild.id)
        if not rows:
            await ctx.send("実績定義はまだありません。")
            return

        lines = [
            f"`{row['id']}` {row['icon']} **{row['name']}** (+{row['points']}) - {row['description']}"
            for row in rows[:25]
        ]
        if len(rows) > 25:
            lines.append(f"... and {len(rows) - 25} more")
        await ctx.send("\n".join(lines))

    @achievement_group.command(name="list")
    async def achievement_list(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        target = member or ctx.author
        rows = await self.bot.achievements.list_member_achievements(ctx.guild.id, target.id)
        if not rows:
            await ctx.send(f"{target.mention} はまだ実績を持っていません。")
            return

        lines = [
            f"{row['icon']} **{row['name']}** (+{row['points']}) - {row['description']}"
            for row in rows[:20]
        ]
        if len(rows) > 20:
            lines.append(f"... and {len(rows) - 20} more")
        await ctx.send(f"{target.mention} の実績一覧\n" + "\n".join(lines))

    @achievement_group.command(name="leaderboard")
    async def achievement_leaderboard(self, ctx: commands.Context) -> None:
        rows = await self.bot.achievements.leaderboard(ctx.guild.id)
        if not rows:
            await ctx.send("実績ランキングはまだありません。")
            return

        lines = []
        for index, row in enumerate(rows, start=1):
            lines.append(
                f"{index}. <@{row['user_id']}> - {row['total_points']}pt / {row['achievement_count']}件"
            )
        await ctx.send("実績ランキング\n" + "\n".join(lines))

    @achievement_group.command(name="create")
    @commands.has_permissions(manage_guild=True)
    async def achievement_create(self, ctx: commands.Context, points: int, icon: str, *, payload: str) -> None:
        name, separator, description = payload.partition("|")
        name = name.strip()
        description = description.strip()
        if not separator or not name or not description:
            await ctx.send("形式: `!achievement create <points> <icon> 名前 | 説明`")
            return

        achievement_id = await self.bot.achievements.create_custom_definition(
            guild_id=ctx.guild.id,
            creator_id=ctx.author.id,
            name=name,
            description=description,
            points=points,
            icon=icon,
        )
        await ctx.send(f"カスタム実績を作成しました。ID: `{achievement_id}` / {icon} **{name}**")

    @achievement_group.command(name="grant")
    @commands.has_permissions(manage_guild=True)
    async def achievement_grant(
        self,
        ctx: commands.Context,
        member: discord.Member,
        achievement_id: int,
        *,
        note: str | None = None,
    ) -> None:
        award = await self.bot.achievements.grant(
            guild_id=ctx.guild.id,
            user_id=member.id,
            achievement_id=achievement_id,
            awarded_by=ctx.author.id,
            note=note,
        )
        if award is None:
            await ctx.send("付与できませんでした。ID が存在しないか、既に所持しています。")
            return

        await ctx.send(f"{member.mention} に {award.icon} **{award.name}** を付与しました。")

    @achievement_group.command(name="revoke")
    @commands.has_permissions(manage_guild=True)
    async def achievement_revoke(self, ctx: commands.Context, member: discord.Member, achievement_id: int) -> None:
        revoked = await self.bot.achievements.revoke(ctx.guild.id, member.id, achievement_id)
        if not revoked:
            await ctx.send("該当する実績付与が見つかりませんでした。")
            return
        await ctx.send(f"{member.mention} から実績 `{achievement_id}` を剥奪しました。")


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(AchievementCog(bot))
