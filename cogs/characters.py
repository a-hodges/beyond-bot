import discord
from discord.ext import commands

from . import beyondapi as api
from . import model as m
from . import util


class CharacterCategory (util.Cog):
    @commands.command(ignore_extra=False)
    async def iam(self, ctx, id: int):
        try:
            bc = api.Character(id)
        except ValueError:
            raise Exception('Invalid character')
        character = ctx.session.query(m.Character).get((ctx.guild.id, ctx.author.id))
        if character is not None:
            character.character = id
        else:
            character = m.Character(server=ctx.guild.id, user=ctx.author.id, character=id)
            ctx.session.add(character)
        ctx.session.commit()
        embed = bc.embed()
        author = embed.pop('author')
        fields = embed.pop('fields')
        embed = discord.Embed(**embed)
        embed.set_author(**author)
        for field in fields:
            embed.add_field(**field)
        await ctx.send(embed=embed)

    @commands.command(ignore_extra=False)
    async def whois(self, ctx, user: discord.Member):
        character = ctx.session.query(m.Character).get((ctx.guild.id, ctx.author.id))
        if character is None:
            raise Exception('User has no character')
        try:
            character = api.Character(character.character)
        except ValueError:
            raise Exception('Invalid character')
        embed = character.embed()
        author = embed.pop('author')
        fields = embed.pop('fields')
        embed = discord.Embed(**embed)
        embed.set_author(**author)
        for field in fields:
            embed.add_field(**field)
        await ctx.send(embed=embed)

    @commands.command(ignore_extra=False)
    async def whoami(self, ctx):
        await ctx.invoke(self.whois, ctx.author)


def setup(bot):
    bot.add_cog(CharacterCategory(bot))
