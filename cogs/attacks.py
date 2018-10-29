import discord
from discord.ext import commands

from . import util
from . import rolls


class AttackCategory (util.Cog):
    @commands.group('attack', aliases=['a'], invoke_without_command=True)
    async def group(self, ctx, *, name: str):
        name = util.strip_quotes(name)

        if not hasattr(ctx, 'advantage'):
            ctx.advantage = 0

        character = util.get_character(ctx, ctx.author.id)
        attack = None
        for a in character.attacks:
            if a['name'].lower() == name.lower():
                attack = a
                break
        if attack is None:
            raise ValueError('No attack with that name')

        name = attack['name']
        if ctx.advantage > 0:
            name += ' with advantage'
        elif ctx.advantage < 0:
            name += ' with disadvantage'
        embed = discord.Embed(title=name, color=character.color())
        embed.set_author(**character.embed_author())
        if attack['attackBonus'] is not None:
            text = []
            result = rolls.do_roll(f"1d20+{attack['attackBonus']}", advantage=ctx.advantage, output=text)
            embed.add_field(name='attack roll', value='\n'.join(text), inline=True)
        if attack['damage'] is not None:
            text = []
            result = rolls.do_roll(attack['damage'], output=text)
            embed.add_field(name='damage roll', value='\n'.join(text), inline=True)
            if attack['damageType'] is None:
                embed.set_footer(text=f'{result} damage')
            else:
                embed.set_footer(text=f"{result} {attack['damageType']} damage")
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
        attacks = map("{0[name]}: {0[attackBonus]:+d}, {0[damage]}, {0[damageType]}".format, character.attacks)
        embed = discord.Embed(description='\n'.join(attacks), color=character.color())
        embed.set_author(**character.embed_author())
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(AttackCategory(bot))
