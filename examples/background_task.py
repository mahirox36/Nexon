from nexon.ext import commands, tasks


class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # an attribute we can access from our task
        self.counter = 0

        # start the task to run in the background
        self.my_background_task.start()

    @tasks.loop(seconds=60)  # task runs every 60 seconds
    async def my_background_task(self):
        channel = self.get_channel(1234567)  # channel ID goes here
        self.counter += 1
        await channel.send(self.counter)

    @my_background_task.before_loop
    async def before_my_task(self):
        await self.wait_until_ready()  # wait until the bot logs in


bot = Bot()
bot.run("token")
