from __future__ import annotations

import discord
from discord.ext import commands


class RoleCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    @commands.group(name="role", invoke_without_command=True)
    @commands.guild_only()
    async def role_group(self, ctx: commands.Context) -> None:
        await ctx.send("`allow` `disallow` `toggle` `list` が使えます。")

    @role_group.command(name="allow")
    @commands.has_permissions(manage_roles=True)
    async def role_allow(self, ctx: commands.Context, role: discord.Role) -> None:
        await self.bot.db.execute(
            """
            INSERT INTO self_roles (guild_id, role_id, created_by)
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id, role_id) DO NOTHING
            """,
            (ctx.guild.id, role.id, ctx.author.id),
        )
        await ctx.send(f"{role.mention} をセルフロールに追加しました。")

    @role_group.command(name="disallow")
    @commands.has_permissions(manage_roles=True)
    async def role_disallow(self, ctx: commands.Context, role: discord.Role) -> None:
        cursor = await self.bot.db.execute(
            "DELETE FROM self_roles WHERE guild_id = ? AND role_id = ?",
            (ctx.guild.id, role.id),
        )
        if cursor.rowcount == 0:
            await ctx.send("そのロールはセルフロールに登録されていません。")
            return
        await ctx.send(f"{role.mention} をセルフロールから外しました。")

    @role_group.command(name="list")
    async def role_list(self, ctx: commands.Context) -> None:
        rows = await self.bot.db.fetchall(
            """
            SELECT role_id
            FROM self_roles
            WHERE guild_id = ?
            ORDER BY role_id ASC
            """,
            (ctx.guild.id,),
        )
        if not rows:
            await ctx.send("セルフロールはまだありません。")
            return

        roles = [ctx.guild.get_role(row["role_id"]) for row in rows]
        labels = [role.mention for role in roles if role is not None]
        await ctx.send("セルフロール一覧\n" + "\n".join(labels))

    @role_group.command(name="toggle")
    async def role_toggle(self, ctx: commands.Context, role: discord.Role) -> None:
        allowed = await self.bot.db.fetchval(
            "SELECT 1 FROM self_roles WHERE guild_id = ? AND role_id = ?",
            (ctx.guild.id, role.id),
            default=0,
        )
        if not allowed:
            await ctx.send("そのロールはセルフ付与対象ではありません。")
            return

        if role >= ctx.guild.me.top_role:
            await ctx.send("Bot のロール階層が足りません。")
            return

        try:
            if role in ctx.author.roles:
                await ctx.author.remove_roles(role, reason="Self role toggle")
                await ctx.send(f"{role.mention} を外しました。")
            else:
                await ctx.author.add_roles(role, reason="Self role toggle")
                await ctx.send(f"{role.mention} を付与しました。")
        except discord.Forbidden:
            await ctx.send("ロール変更権限が不足しています。")


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(RoleCog(bot))
