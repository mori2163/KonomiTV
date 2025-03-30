import discord
from discord.ext import commands
from discord import app_commands
import datetime
from app import logging
from app.config import Config, SaveConfig
config = Config()

# ボットの初期化
bot = commands.Bot(
    command_prefix='!',
    intents=discord.Intents.default(),
    activity=discord.Game("/helpでコマンド一覧")
)

async def send_bot_status_message(status:str):
    """ボットの状態をログチャンネルに送信する共通関数"""
    try:
        channel_id = config.discord.log_channel_id

        if not channel_id or not config.discord.log_enabled:
            return

        channel = await bot.fetch_channel(channel_id)
        # チャンネルが存在しているかを確認
        if channel and isinstance(channel, discord.TextChannel):
            time = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
            embed = discord.Embed(colour=0x0091ff)

            if status == "startup":
                embed.set_author(name="🟢KonomiTVが起動しました")
            elif status == "shutdown":
                embed.set_author(name="🛑KonomiTVが終了しました")

            embed.set_footer(text=time)
            await channel.send(embed=embed)
            logging.info(f'[DiscordBot] Sent {status} message to #{channel.name} (ID: {channel.id})')
        elif channel:
            # テキストチャンネル以外が見つかった場合
            logging.warning(f'[DiscordBot] Configured log channel (ID: {channel_id}) is not a TextChannel.')
        else:
            # チャンネルが見つからなかった場合
            logging.warning(f'[DiscordBot] Log channel (ID: {channel_id}) not found.')
    except Exception as e:
        logging.error(f'[DiscordBot] Error sending {status} message: {e}')

@bot.event
async def on_ready():
    """起動時に実行されるイベントハンドラ"""
    if bot.user:
        logging.info(f'[DiscordBot] ✅ Login successful! (User: {bot.user} (ID: {bot.user.id})')
    else:
        logging.info('[DiscordBot] ✅ Login successful! (User info unavailable)')

    # コマンドツリーを同期
    try:
        await bot.tree.sync()
        logging.info('[DiscordBot] 🔄 Slash commands synchronized.')
    except Exception as e:
        logging.error(f'[DiscordBot] Error synchronizing command tree: {e}')

     # 起動時にログチャンネルにメッセージを送信
    await send_bot_status_message("startup")

class UtilityCog(commands.Cog):
    """ユーティリティコマンド集"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="コマンド一覧を表示")
    async def help(self, interaction: discord.Interaction):
        """ヘルプメッセージを表示"""
        embed = discord.Embed(
            title="コマンド一覧",
            description="利用可能なスラッシュコマンド",
            color=0x00ff00
        )
        embed.add_field(
            name="/setting",
            value="各種設定を行う",
            inline=False
        )
        await interaction.response.send_message(embed=embed)

class SettingCog(commands.Cog):
    """設定コマンド集"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    #settingコマンドグループを定義
    setting = app_commands.Group(
        name="setting",
        description="各種設定を行う"
    )

    #ログを出力するチャンネルの設定をするサブコマンド
    @setting.command(name="log_channel", description="ログチャンネルを設定")
    async def log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """ログチャンネルを設定"""
        try:
            #引数からチャンネルIDを変更
            config.discord.log_channel_id = channel.id

            # 設定ファイルを保存
            SaveConfig(config)

            await interaction.response.send_message(
                f"✅ログチャンネルを{channel.mention}に設定しました。",
                ephemeral=True
            )
            logging.info(f'[DiscordBot] Log channel set to {channel.name} (ID: {channel.id})')

        #エラー時の処理
        except Exception as e:
            logging.error(f'[DiscordBot] Error setting log channel: {e}')
            await interaction.response.send_message(
                f'❌ログチャンネルの設定に失敗しました。',
                  ephemeral=True
            )

    #ログの出力を有効/無効にするサブコマンド
    @setting.command(name="enable_log",description="ログ出力の有効/無効を切り替えます。")
    @app_commands.describe(enabled="ログ出力の有効にするか無効にするか")

    async def log_enabled(self, interaction: discord.Interaction, enabled: bool):
        """ログ出力の有無を設定"""
        try:
            #有効にするかを設定
            config.discord.log_enabled = enabled
            SaveConfig(config) # 設定ファイルを保存

            status = "有効" if enabled else "無効"
            await interaction.response.send_message(
                f"✅ログ出力を{status}に設定しました。",
                ephemeral=True
            )
            logging.info(f'[DiscordBot] Log enabled set to {status} by {interaction.user.name} (ID: {interaction.user.id})')

        #エラー時の処理
        except Exception as e:
            logging.error(f'[DiscordBot] Error setting log enabled: {e}')
            await interaction.response.send_message(
                f'❌ログ出力設定の選考中にエラーが発生しました。\n{e}',
                ephemeral=True
            )

async def setup():
    """"ボットの初期設定を行う"""
    # コグの登録
    await bot.add_cog(UtilityCog(bot))
    await bot.add_cog(SettingCog(bot))


async def start_discord_bot():
    """Discord ボットを起動する"""

    # Discord トークンが設定されているか確認
    if config.discord.token is None:
        logging.error("[Discord Bot] Discord Bot token is not configured correctly. Aborting startup.")
        return # トークンがなければ起動しない

    try:
        # コグの登録など、ボット起動前の非同期セットアップ
        await setup()
        # ボットを非同期で起動
        logging.info("Discord Bot started successfully.")
        await bot.start(config.discord.token)

    #ログインに失敗した際の処理
    except discord.LoginFailure:
        logging.error("[Discord Bot] Discord Bot login failed, please check the token setting in Config.yaml.")
    #内部エラーが発生した際の処理
    except Exception as e:
        logging.error(f"[Discord Bot] An internal error occurred. Error details: {e}")

async def stop_discord_bot():
    """Discord ボットを停止する"""
    try:
        # 停止メッセージを送信
        await send_bot_status_message("shutdown")
        # ボットを停止
        await bot.close()
        logging.info("[DiscordBot] Discord Bot stopped successfully.")
    except Exception as e:
        logging.error(f"[Discord Bot] An internal error occurred while stopping the bot. Error details: {e}")
