from discord.ext import commands

from . import beyondapi as api
from . import model as m


class BotError (Exception):
    pass


class Cog:
    def __init__(self, bot):
        self.bot = bot


def get_character(id, user=None):
    '''
    If only id is given gets the character from the id
    If id and user is given gets the claim from the ctx (passed in as id) and user id
    '''
    if user is not None:
        ctx = id
        claim = ctx.session.query(m.Character).get((ctx.guild.id, user))
        if claim is None:
            raise LookupError('User has no character')
        id = claim.character
    character = api.Character(id)
    return character


def invalid_subcommand(ctx):
    message = 'Command "{} {}" is not found'.format(ctx.invoked_with, ctx.message.content.split()[1])
    return commands.CommandNotFound(message)


def strip_quotes(arg):
    '''
    Strips quotes from arguments
    '''
    if len(arg) >= 2 and arg.startswith('"') and arg.endswith('"'):
        arg = arg[1:-1]
    return arg
