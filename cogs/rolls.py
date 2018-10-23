import re
import random
from itertools import chain

import discord
from discord.ext import commands
import equations

from . import util


async def do_roll(expression, output=[]):
    '''
    Rolls dice
    '''
    expression = expression.strip()
    match = re.match(r'^(.*)\s+((?:dis)?adv|dis|(?:dis)?advantage)$', expression)
    if match:
        expression = match.group(1)
        if match.group(2) in ['adv', 'advantage']:
            adv = 1
        elif match.group(2) in ['dis', 'disadv', 'disadvantage']:
            adv = -1
        else:
            raise Exception('Invalid adv/disadv operator')
    else:
        adv = 0

    original_expression = expression

    # Set up operations
    def roll_dice(a, b, *, silent=False):
        rolls = []
        for _ in range(a):
            if b > 0:
                n = random.randint(1, b)
            elif b < 0:
                n = random.randint(b, -1)
            else:
                n = 0
            rolls.append(n)
        value = sum(rolls)
        if not silent:
            output.append('{}d{}: {} = {}'.format(a, b, ' + '.join(map(str, rolls)), value))
        return value

    def great_weapon_fighting(a, b, low=2, *, silent=False):
        rolls = []
        rerolls = []
        value = 0
        for _ in range(a):
            n = roll_dice(1, b, silent=True)
            rolls.append(n)
            if n <= low:
                n2 = random.randint(1, b)
                rerolls.append(n2)
                value += n2
            else:
                value += n
        if not silent:
            rolled = ' + '.join(map(str, rolls))
            if rerolls:
                rerolled = list(filter(lambda a: a > low, rolls))
                rerolled.extend(rerolls)
                rerolled = ' + '.join(map(str, rerolled))
                output.append('{}g{}: {}, rerolled: {} = {}'.format(a, b, rolled, rerolled, value))
            else:
                output.append('{}g{}: {} = {}'.format(a, b, rolled, value))
        return value

    def roll_advantage(a, b, *, silent=False):
        if a == 1 and b == 20:
            first = roll_dice(a, b, silent=True)
            second = roll_dice(a, b, silent=True)
            out = max(first, second)
            if not silent:
                output.append('{}d{}: max({}, {}) = {}'.format(a, b, first, second, out))
        else:
            out = roll_dice(a, b, silent=silent)
        return out

    def roll_disadvantage(a, b, *, silent=False):
        if a == 1 and b == 20:
            first = roll_dice(a, b, silent=True)
            second = roll_dice(a, b, silent=True)
            out = min(first, second)
            if not silent:
                output.append('{}d{}: min({}, {}) = {}'.format(a, b, first, second, out))
        else:
            out = roll_dice(a, b, silent=silent)
        return out

    operations = equations.operations.copy()
    operations.append({'>': max, '<': min})

    dice = {}
    if adv == 0:
        dice['d'] = roll_dice
    elif adv > 0:
        dice['d'] = roll_advantage
    else:
        dice['d'] = roll_disadvantage
    dice['D'] = dice['d']
    dice['g'] = great_weapon_fighting
    dice['G'] = dice['g']
    operations.append(dice)

    unary = equations.unary.copy()
    unary['!'] = lambda a: a // 2 - 5

    output.append('`{}`'.format(expression))

    # validate
    for token in re.findall(r'[a-zA-Z]+', expression):
        if token not in chain(*operations) and token not in unary:
            search = r'[a-zA-Z]*({})[a-zA-Z]*'.format(re.escape(token))
            search = re.search(search, original_expression)
            if search:
                token = search.group(1)
            raise equations.EquationError('\n{}\nCould not find: `{}`'.format('\n'.join(output), token))

    # do roll
    roll = equations.solve(expression, operations=operations, unary=unary)
    if roll % 1 == 0:
        roll = int(roll)

    output.append('You rolled {}'.format(roll))

    return roll


class RollCategory (util.Cog):
    @commands.group('roll', aliases=['r'], invoke_without_command=True)
    async def group(self, ctx, *, expression: str):
        '''
        Rolls dice
        Note: If a variable name is included in a roll the name will be replaced with the value of the variable

        Parameters:
        [expression*] standard dice notation specifying what to roll
            The expression may include saved rolls, replacing the name with the roll itself
            Rolls may contain other rolls up to 3 levels deep
        [adv] (optional) roll any 1d20s with advantage or disadvantage for the following options:
            Advantage: `adv` | `advantage`
            Disadvantage: `dis` | `disadv` | `disadvantage`

        Mathematic operations from highest precedence to lowest:

        d : NdM rolls an M sided die N times and adds the results together
        g : NgM rolls an M sided die N times, rerolls any 1 or 2 once

        > : picks larger operand
        < : picks smaller operand

        ^ : exponentiation

        * : multiplication
        / : division
        //: division, rounded down

        + : addition
        - : subtraction

        Unary prefixes:
        - : negates a number
        + : does nothing to a number
        ! : gets the modifier of an ability score using standard D&D modifier rules (score/2-5) i.e. !16 = 3
        '''
        if not expression:
            raise commands.MissingRequiredArgument('expression')
        expression = util.strip_quotes(expression)

        output = []
        await do_roll(expression, output=output)
        embed = discord.Embed(description='\n'.join(output), color=ctx.author.color)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(RollCategory(bot))
