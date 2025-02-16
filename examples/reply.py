import nexon
from nexon.ext import commands

intents = nexon.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="$", intents=intents)


@bot.command()
async def hello(ctx):
    await ctx.reply("Hello!")


bot.run("token")
