import nexon
from nexon.ext import commands

TESTING_GUILD_ID = 123456789  # Replace with your testing guild id


class ApplicationCommandCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @nexon.slash_command(guild_ids=[TESTING_GUILD_ID], description="Test command")
    async def my_slash_command(self, interaction: nexon.Interaction):
        await interaction.response.send_message("This is a slash command in a cog!")

    @nexon.user_command(guild_ids=[TESTING_GUILD_ID])
    async def my_user_command(self, interaction: nexon.Interaction, member: nexon.Member):
        await interaction.response.send_message(f"Hello, {member}!")

    @nexon.message_command(guild_ids=[TESTING_GUILD_ID])
    async def my_message_command(
        self, interaction: nexon.Interaction, message: nexon.Message
    ):
        await interaction.response.send_message(f"{message}")


def setup(bot):
    bot.add_cog(ApplicationCommandCog(bot))
