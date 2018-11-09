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
            if isinstance(attack['attackBonus'], (int, float)):
                text = []
                result = rolls.do_roll(f"1d20+{attack['attackBonus']}", advantage=ctx.advantage, output=text)
                embed.add_field(name='attack roll', value='\n'.join(text), inline=True)
            else:
                embed.add_field(name='attack roll', value=attack['attackBonus'])
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
        attacks = []
        for attack in character.attacks:
            if isinstance(attack['attackBonus'], (int, float)):
                attacks.append(f"**{attack['name']}:** {attack['attackBonus']:+d}, {attack['damage']}, {attack['damageType']}")
            else:
                attacks.append(f"**{attack['name']}:** {attack['attackBonus']}, {attack['damage']}, {attack['damageType']}")
        embed = discord.Embed(title='Attacks', description='\n'.join(attacks), color=character.color())
        embed.set_author(**character.embed_author())
        msg = await ctx.send(embed=embed)
        await msg.add_reaction(util.delete_emoji)
        await ctx.message.delete()


def setup(bot):
    bot.add_cog(AttackCategory(bot))
