class BotError (Exception):
    pass


class Cog:
    def __init__(self, bot):
        self.bot = bot


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
