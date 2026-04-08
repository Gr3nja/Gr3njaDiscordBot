from __future__ import annotations

import discord
from discord.ext import commands


class BuyCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    @commands.group(name="shop", invoke_without_command=True)
    @commands.guild_only()
    async def shop_group(self, ctx: commands.Context) -> None:
        await ctx.send("`currency` `add` `remove` `list` `buy` が使えます。")

    @shop_group.command(name="currency")
    @commands.has_permissions(manage_guild=True)
    async def shop_currency(self, ctx: commands.Context, *, currency_name: str) -> None:
        await self.bot.economy.set_currency_name(ctx.guild.id, currency_name.strip())
        await ctx.send(f"サーバー通貨名を `{currency_name.strip()}` に変更しました。")

    @shop_group.command(name="add")
    @commands.has_permissions(manage_roles=True)
    async def shop_add(
        self,
        ctx: commands.Context,
        role: discord.Role,
        price: int,
        *,
        description: str = "",
    ) -> None:
        if price <= 0:
            await ctx.send("価格は 1 以上で指定してください。")
            return
        await self.bot.db.execute(
            """
            INSERT INTO shop_roles (guild_id, role_id, price, description, created_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (guild_id, role_id) DO UPDATE SET
                price = excluded.price,
                description = excluded.description,
                created_by = excluded.created_by
            """,
            (ctx.guild.id, role.id, price, description.strip(), ctx.author.id),
        )
        await ctx.send(f"{role.mention} を {price} でショップに登録しました。")

    @shop_group.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    async def shop_remove(self, ctx: commands.Context, role: discord.Role) -> None:
        cursor = await self.bot.db.execute(
            "DELETE FROM shop_roles WHERE guild_id = ? AND role_id = ?",
            (ctx.guild.id, role.id),
        )
        if cursor.rowcount == 0:
            await ctx.send("そのロールはショップに登録されていません。")
            return
        await ctx.send(f"{role.mention} をショップから削除しました。")

    @shop_group.command(name="list")
    async def shop_list(self, ctx: commands.Context) -> None:
        rows = await self.bot.db.fetchall(
            """
            SELECT role_id, price, description
            FROM shop_roles
            WHERE guild_id = ?
            ORDER BY price ASC, role_id ASC
            """,
            (ctx.guild.id,),
        )
        if not rows:
            await ctx.send("ショップは空です。")
            return

        currency = await self.bot.economy.get_currency_name(ctx.guild.id)
        lines = []
        for row in rows:
            role = ctx.guild.get_role(row["role_id"])
            if role is None:
                continue
            description = f" - {row['description']}" if row["description"] else ""
            lines.append(f"{role.mention}: **{row['price']} {currency}**{description}")
        await ctx.send("ロールショップ一覧\n" + "\n".join(lines))

    @shop_group.command(name="buy")
    async def shop_buy(self, ctx: commands.Context, role: discord.Role) -> None:
        listing = await self.bot.db.fetchone(
            """
            SELECT price, description
            FROM shop_roles
            WHERE guild_id = ? AND role_id = ?
            """,
            (ctx.guild.id, role.id),
        )
        if listing is None:
            await ctx.send("そのロールはショップにありません。")
            return
        if role in ctx.author.roles:
            await ctx.send("そのロールは既に所持しています。")
            return
        if role >= ctx.guild.me.top_role:
            await ctx.send("Bot のロール階層が足りません。")
            return

        paid, wallet = await self.bot.economy.spend_balance(ctx.guild.id, ctx.author.id, listing["price"])
        currency = await self.bot.economy.get_currency_name(ctx.guild.id)
        if not paid:
            await ctx.send(f"残高不足です。必要額: {listing['price']} {currency} / 現在: {wallet.balance} {currency}")
            return

        try:
            await ctx.author.add_roles(role, reason="Role shop purchase")
        except discord.Forbidden:
            await self.bot.economy.add_balance(ctx.guild.id, ctx.author.id, listing["price"])
            await ctx.send("ロール付与権限が不足しているため、購入を取り消しました。")
            return

        await self.bot.db.execute(
            """
            INSERT INTO owned_shop_roles (guild_id, user_id, role_id)
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id, user_id, role_id) DO NOTHING
            """,
            (ctx.guild.id, ctx.author.id, role.id),
        )
        awards = await self.bot.achievements.record_role_purchase(ctx.guild.id, ctx.author.id)
        updated_wallet = await self.bot.economy.get_wallet(ctx.guild.id, ctx.author.id)
        await ctx.send(f"{role.mention} を購入しました。残高: {updated_wallet.balance} {currency}")
        await self.bot.announce_achievements(ctx.channel, ctx.author, awards)


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(BuyCog(bot))
