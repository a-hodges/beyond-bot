import discord
from discord.ext import commands

from . import util
from . import rolls


class CustomRollCategory (util.Cog):
    @commands.group('customroll', aliases=['cr'], invoke_without_command=True)
    async def group(self, ctx, *, name: str):
        name = util.strip_quotes(name)

        if not hasattr(ctx, 'advantage'):
            ctx.advantage = 0

        character = util.get_character(ctx, ctx.author.id)
        roll = character.custom_rolls().get(name.lower())
        if roll is None:
            raise ValueError('No roll with that name')

        if ctx.advantage > 0:
            name += ' with advantage'
        elif ctx.advantage < 0:
            name += ' with disadvantage'

        embed = discord.Embed(color=character.color())
        embed.set_author(**character.embed_author())
        text = []
        rolls.do_roll(roll, advantage=ctx.advantage, output=text)
        embed.add_field(name=name, value='\n'.join(text), inline=False)
        await ctx.send(embed=embed)

    @group.command(aliases=['a', 'adv'])
    async def advantage(self, ctx, *, name: str):
        ctx.advantage = 1
        await ctx.invoke(self.group, name=name)

    @group.command(aliases=['d', 'dis', 'disadv'])
    async def disadvantage(self, ctx, *, name: str):
        ctx.advantage = -1
        await ctx.invoke(self.group, name=name)

    @group.command(ignore_extra=False)
    async def list(self, ctx):
        character = util.get_character(ctx, ctx.author.id)
        rolls = map("**{0[0]}:** {0[1]}".format, character.custom_rolls().items())
        embed = discord.Embed(title='Custom Rolls', description='\n'.join(rolls), color=character.color())
        embed.set_author(**character.embed_author())
        msg = await ctx.send(embed=embed)
        await msg.add_reaction(util.delete_emoji)
        await ctx.message.delete()


def setup(bot):
    bot.add_cog(CustomRollCategory(bot))
