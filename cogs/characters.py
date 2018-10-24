import re

import discord
from discord.ext import commands

from . import model as m
from . import util


CHARACTER_URL = re.compile(r'(?:https://)?(?:www\.)?dndbeyond\.com/profile/\w+/characters/(\d+)')
SHARE_URL = re.compile(r'(?:https://)?ddb\.ac/characters/(\d+)/\w+')
NUMBER_EXPR = re.compile(r'(\d+)')


class CharacterCategory (util.Cog):
    @commands.command(ignore_extra=False)
    async def iam(self, ctx, id: str):
        for pattern in [CHARACTER_URL, SHARE_URL, NUMBER_EXPR]:
            match = pattern.match(id)
            if match is not None:
                id = int(match.group(1))
                break
        character = util.get_character(id)
        claim = ctx.session.query(m.Character).get((ctx.guild.id, ctx.author.id))
        if claim is not None:
            claim.character = id
        else:
            claim = m.Character(server=ctx.guild.id, user=ctx.author.id, character=id)
            ctx.session.add(claim)
        ctx.session.commit()
        embed = discord.Embed(color=character.color())
        embed.set_author(**character.embed_author())
        for field in character.embed_fields():
            embed.add_field(**field)
        await ctx.send(embed=embed)

    @commands.command(ignore_extra=False)
    async def whois(self, ctx, user: discord.Member):
        try:
            character = util.get_character(ctx, user.id)
        except LookupError:
            embed = discord.Embed(description='User has no character')
        else:
            embed = discord.Embed(color=character.color())
            embed.set_author(**character.embed_author())
            for field in character.embed_fields():
                embed.add_field(**field)
        await ctx.send(embed=embed)

    @commands.command(ignore_extra=False)
    async def whoami(self, ctx):
        await ctx.invoke(self.whois, ctx.author)

    @commands.command(ignore_extra=False)
    async def unclaim(self, ctx):
        claim = ctx.session.query(m.Character).get((ctx.guild.id, ctx.author.id))
        if claim is not None:
            ctx.session.delete(claim)
            ctx.session.commit()
        embed = discord.Embed(description='Done')
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(CharacterCategory(bot))
