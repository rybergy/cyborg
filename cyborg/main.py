import traceback
from cyborg.config import Config
from cyborg.music.commands import Music
from discord.ext import commands
import logging


def run(config: Config):
    logger = logging.getLogger(__name__)

    logger.info(f"Running with config:\n{config}")
    logger.debug(f"Token: {config.token}")

    bot = commands.Bot(
        command_prefix=commands.when_mentioned_or("!"),
        description="Relatively simple music bot example",
    )

    @bot.event
    async def on_ready():
        logger.info(
            f"Logged in as {bot.user} ({bot.user.id if bot.user is not None else ''})"
        )

    @bot.event
    async def on_command_error(ctx: commands.Context, error: BaseException):
        logger.error(f"{error.__traceback__}\n{error}")
        await ctx.send(f":x: {str(error)}")

    if config.token is None:
        raise RuntimeError("No token found in $CYBORG_TOKEN or config file!")

    bot.add_cog(Music(bot, config))
    bot.run(config.token)
