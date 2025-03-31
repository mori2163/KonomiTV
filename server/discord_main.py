import discord
from discord.ext import commands
from discord import app_commands
import datetime
from typing import Dict, List, Tuple, Optional

from app import logging
from app.config import Config, SaveConfig
from fastapi import HTTPException
from app.models.Channel import Channel
from app import schemas # schemas をインポート
from app.models.Program import Program
from app.routers.VideosRouter import VideosAPI

config = Config()

# 日本のタイムゾーンを定数として定義
JST = datetime.timezone(datetime.timedelta(hours=9))

# ボットの初期化
bot = commands.Bot(
    command_prefix='!',
    intents=discord.Intents.default(),
    activity=discord.Game("/helpでコマンド一覧")
)

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

async def setup():
    """"ボットの初期設定を行う"""
    # コグの登録
    await bot.add_cog(UtilityCog(bot))
    await bot.add_cog(SettingCog(bot))
    await bot.add_cog(ViewCog(bot))

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
            name="/setting log_channel",
            value="ログ出力チャンネルを設定する",
            inline=False
        )
        embed.add_field(
            name="/setting enable_log",
            value="ログ出力の有効/無効を切り替える",
            inline=False
        )
        embed.add_field(
            name="/view channel_now",
            value="指定されたチャンネルの現在の番組情報を表示",
            inline=False
        )
        embed.add_field(
            name="/view channel_list",
            value="指定タイプのチャンネル一覧を表示",
            inline=False
        )
        embed.add_field(
            name="/view recorded_info",
            value="録画済み番組一覧を表示",
            inline=False
        )
        await interaction.response.send_message(embed=embed)

class ViewCog(commands.Cog):
    """ビューコマンド集"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    view = app_commands.Group(
        name="view",
        description="チャンネル情報などを確認する"
    )

    #チャンネル一覧を表示するサブコマンド
    @view.command(name="channel_list", description="指定タイプのチャンネル一覧を表示 (地デジ(GR), BS, CS)")
    @app_commands.describe(channel_type="表示したいチャンネルタイプ (地デジ(GR), BS, CS)")
    async def channel_list(self, interaction: discord.Interaction,channel_type: str):
        """チャンネル一覧を表示"""
        await interaction.response.defer(ephemeral=True)
        try:
            #チャンネルタイプが正しいかをフィルタ
            if channel_type in ['GR', 'BS', 'CS', 'all']:
                if channel_type == 'all':
                    channel_types_to_fetch = ['GR', 'BS', 'CS']
                else:
                    channel_types_to_fetch = [channel_type]
                channels_data = await get_specific_channels(channel_types_to_fetch)
            else:
                await interaction.followup.send("チャンネルタイプが正しくありません。GR、BS、CS、またはallを指定してください。", ephemeral=True)
                return

            embed = discord.Embed(
                title="チャンネル一覧 (GR, BS, CS)",
                color=0x0091ff
            )

            for ch_type in channel_types_to_fetch:
                channel_list = channels_data.get(ch_type, [])
                if channel_list:
                    # チャンネルリストを整形 (ID: 名前)
                    value_str = "\n".join([f"`{ch_id}`: {ch_name}" for ch_id, ch_name in channel_list[:25]])
                    embed.add_field(name=f"📺 {ch_type}", value=value_str, inline=False)
                else:
                    # チャンネルが見つからない場合
                    embed.add_field(name=f"📺 {ch_type}", value="チャンネルが見つかりません。", inline=False)
            # タイムスタンプを追加
            embed.set_footer(text=datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logging.error(f'[DiscordBot] Error getting channel list: {e}')
            await interaction.followup.send(f"❌ チャンネル一覧の取得中にエラーが発生しました。\nエラー詳細: {e}", ephemeral=True)

    @view.command(name="channel_now", description="指定されたチャンネルの現在と次の番組情報を表示")
    @app_commands.describe(channel_id="表示したいチャンネルのID (例: gr011)")
    async def channel_now(self, interaction: discord.Interaction, channel_id: str):
        """指定されたチャンネルの現在の番組情報を表示"""
        try:
            channel_instance = await Channel.get_or_none(display_channel_id=channel_id)

            # channelIDが得られなかった場合
            if not channel_instance:
                await interaction.response.send_message(f"❌ チャンネルID '{channel_id}' が見つかりません。", ephemeral=True)
                return

            # Channel インスタンスから現在の番組と次の番組を取得
            program_present, program_following = await channel_instance.getCurrentAndNextProgram()

            embed = discord.Embed(
                title=f"{channel_instance.name} ({channel_instance.display_channel_id}) の現在の番組情報",
                color=0x0091ff
            )

             # 共通関数を使用して番組情報をフォーマット
            embed.add_field(
                name="📺 現在の番組",
                value=format_program_info(program_present),
                inline=False
            )

            embed.add_field(
                name="▶️ 次の番組",
                value=format_program_info(program_following),
                inline=False
            )
            embed.set_footer(text=datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logging.error(f'[DiscordBot] Error getting channel info for {channel_id}: {e}')
            await interaction.response.send_message(f"❌ チャンネル情報の取得中にエラーが発生しました。\n{e}", ephemeral=True)

    @view.command(name="recorded_info", description="録画済み番組一覧を表示")
    @app_commands.describe(page="表示したいページ番号 (デフォルト: 1)")
    async def recorded_info(self, interaction: discord.Interaction, page: int = 1):
        """録画済み番組一覧を表示"""
        await interaction.response.defer()
        try:
            # 不正なページ番号をチェック
            if page < 1:
                await interaction.followup.send("❌ ページ番号は1以上を指定してください。", ephemeral=True)
                return

            # VideosAPI を呼び出して録画番組リストを取得
            # VideosAPI は schemas.RecordedPrograms を返す
            recorded_programs_data: schemas.RecordedPrograms = await VideosAPI(order='desc', page=page)

            if not recorded_programs_data.recorded_programs:
                await interaction.followup.send(f"❌ 録画番組が見つかりません。(ページ: {page})", ephemeral=True)
                return

            # Embed を作成
            embed = discord.Embed(
                title=f"録画済み番組一覧 (ページ {page})",
                color=0x0091ff
            )
             # 各録画番組を個別のフィールドとして追加
            for i, program in enumerate(recorded_programs_data.recorded_programs, 1):
                start_time_jst = program.start_time.astimezone(JST)
                end_time_jst = program.end_time.astimezone(JST)

            # 番組情報をフィールドとして追加
                embed.add_field(
                    name=f"🔵番組 {i}: {program.title}",
                    value=(
                        f"放送時間: {start_time_jst.strftime('%H:%M')} - {end_time_jst.strftime('%H:%M')}\n"
                        f"詳細: {program.description or '詳細情報なし'}"
                    ),
                    inline=False
                )

            # ページ情報をフッターに追加
            total_items = recorded_programs_data.total
            items_per_page = len(recorded_programs_data.recorded_programs)  # 実際のページサイズを使用
            total_pages = (total_items + items_per_page - 1) // items_per_page if items_per_page > 0 else 1

            # 現在のページが総ページ数を超えている場合（ただしデータがある場合）
            if page > total_pages and total_items > 0:
                embed.add_field(
                    name="⚠️ 注意",
                    value=f"指定されたページ番号（{page}）は総ページ数（{total_pages}）を超えています。",
                    inline=False
                )

            #ページ数とタイムスタンプ
            embed.set_footer(text=f"ページ {page} / {total_pages}・全 {total_items} 件・{JST}")

            await interaction.followup.send(embed=embed)

        except HTTPException as e:
            # FastAPI の HTTPException
            error_detail = getattr(e, 'detail', str(e))
            logging.error(f'[DiscordBot] Error getting recorded list (page {page}): {error_detail}')
            await interaction.followup.send(f"❌ 録画番組一覧の取得中にHTTPエラーが発生しました。\n詳細: {error_detail}", ephemeral=True)
        except Exception as e:
            # その他の予期せぬエラー
            logging.error(f'[DiscordBot] Error getting recorded list (page {page}): {e}')
            await interaction.followup.send(f"❌ 録画番組一覧の取得中に予期せぬエラーが発生しました。\nエラー詳細: {e}", ephemeral=True)

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
                f'❌ログ出力設定の中にエラーが発生しました。\n{e}',
                ephemeral=True
            )

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

def format_program_info(program: Optional[Program]):
    """番組情報をフォーマットする"""
    if not program:
        return "情報なし"

    start_time_jst = program.start_time.astimezone(JST)
    end_time_jst = program.end_time.astimezone(JST)

    return (f"**{program.title}**\n" \
            f"{start_time_jst.strftime('%H:%M')} - {end_time_jst.strftime('%H:%M')}\n" \
            f"{program.description or '詳細情報なし'}")

# チャンネル情報取得
async def get_specific_channels(channel_types: List[str] = ['GR', 'BS', 'CS']) -> Dict[str, List[Tuple[str, str]]]:
    """
    指定されたチャンネルタイプのチャンネルID(display_channel_id)と名前のリストを取得する。
    """
    channels_data: Dict[str, List[Tuple[str, str]]] = {ch_type: [] for ch_type in channel_types}
    try:
        # 視聴可能なチャンネルをデータベースから取得 (タイプ、チャンネル番号、リモコンID順)
        all_channels = await Channel.filter(is_watchable=True).order_by('type', 'channel_number', 'remocon_id')
        # 指定されたチャンネルタイプでフィルタリングし、IDと名前を抽出
        for channel in all_channels:
            if channel.type in channel_types:
                # display_channel_id と name をタプルで追加
                channels_data[channel.type].append((channel.display_channel_id, channel.name))
    except Exception as e:
        logging.error(f"[DiscordBot] Error fetching channel data: {e}")
        # エラー発生時は空の辞書を返す
        return {ch_type: [] for ch_type in channel_types}
    return channels_data
