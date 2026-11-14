"""Discord companion: alerts with screenshots, remote control, and stats.

Slash commands (only users in discord.allowed_user_ids may use control commands):
  /status                      every instance and what it is doing
  /start   instance [script]   start a script (Any Quest, Crest, Login & Mail...)
  /stop    instance|all        stop
  /pause   instance            pause / resume
  /resume  instance
  /screenshot instance         live screenshot
  /stats   [instance]          runs, crests, errors, uptime
  /resetstats instance|all     zero an instance's counters
  /history [instance] [count]  recent crests, refills and problems
  /summary                     the last 24 hours (also posted daily)
  /crests  [instance]          4+ / Burst / Lv4 today, session, all-time, observed rates
  /scripts                     list scripts
"""
from __future__ import annotations

import asyncio
import io
import threading
import time
from typing import TYPE_CHECKING

import cv2

from .stats import fmt_duration

if TYPE_CHECKING:
    from .manager import Manager

try:
    import discord
    from discord import app_commands
except ImportError:  # pragma: no cover
    discord = None


STATUS_ICON = {"idle": "⚪", "starting": "🟡", "running": "🟢", "paused": "🟠", "error": "🔴"}


class DiscordBot:
    def __init__(self, manager: "Manager"):
        if discord is None:
            raise RuntimeError("discord.py is not installed (pip install discord.py)")
        self.m = manager
        cfg = manager.config["discord"]
        self.token: str = cfg.get("token", "")
        self.channel_id = int(cfg.get("channel_id") or 0)
        self.ping_user_id = int(cfg.get("ping_user_id") or 0)
        self.allowed = {int(x) for x in cfg.get("allowed_user_ids", []) or []}
        if not self.token:
            raise RuntimeError("Discord token is empty")
        self.loop: asyncio.AbstractEventLoop | None = None
        self.client: discord.Client | None = None
        self.thread: threading.Thread | None = None
        self.ready = threading.Event()

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="discord", daemon=True)
        self.thread.start()
        self.m.discord = self

    def stop(self) -> None:
        if self.m.discord is self:
            self.m.discord = None
        if self.loop and self.client:
            asyncio.run_coroutine_threadsafe(self.client.close(), self.loop)

    def _run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.client = self._build_client()
        try:
            self.loop.run_until_complete(self.client.start(self.token))
        except Exception as e:  # noqa: BLE001
            self.m.log("discord", f"Discord bot stopped: {e}")
        finally:
            self.ready.clear()

    # ------------------------------------------------------------ sending
    def send(self, text: str, png: bytes | None = None, ping: bool = False) -> None:
        """Thread-safe: queue a message to the alert channel."""
        if not self.loop or not self.client or not self.ready.is_set():
            return
        asyncio.run_coroutine_threadsafe(self._send(text, png, ping), self.loop)

    async def _send(self, text: str, png: bytes | None, ping: bool) -> None:
        try:
            ch = self.client.get_channel(self.channel_id) or await self.client.fetch_channel(self.channel_id)
            if ping and self.ping_user_id:
                text = f"<@{self.ping_user_id}> {text}"
            file = discord.File(io.BytesIO(png), "screen.png") if png else None
            await ch.send(text[:1900], file=file)
        except Exception as e:  # noqa: BLE001
            self.m.log("discord", f"Could not send alert: {e}")

    # ------------------------------------------------------------ commands
    def _build_client(self):
        bot = self
        m = self.m
        intents = discord.Intents.none()
        intents.guilds = True
        client = discord.Client(intents=intents)
        tree = app_commands.CommandTree(client)

        def allowed(inter: discord.Interaction) -> bool:
            return inter.user.id in bot.allowed

        async def deny(inter: discord.Interaction) -> None:
            await inter.response.send_message(
                "You are not allowed to control this bot. Add your user ID to "
                "discord.allowed_user_ids in config.yaml.", ephemeral=True)

        async def instance_ac(inter, current: str):
            return [app_commands.Choice(name=n, value=n)
                    for n in list(m.instances) + ["all"] if current.lower() in n.lower()][:25]

        async def script_ac(inter, current: str):
            return [app_commands.Choice(name=label[:100], value=k)
                    for k, label in m.scripts_available().items()
                    if current.lower() in label.lower()][:25]

        @tree.command(description="Show every instance and what it is doing")
        async def status(inter: discord.Interaction):
            lines = []
            for n, i in m.instances.items():
                up = fmt_duration(m.stats.uptime(n)) if i.status in ("running", "paused") else "-"
                lines.append(f"{STATUS_ICON.get(i.status, '❔')} **{n}** - {i.status} "
                             f"({m.scripts_available().get(i.script, i.script)}, {i.serial}) up {up} "
                             f"{i.detail if i.status in ('error', 'idle') else ''}")
            await inter.response.send_message("\n".join(lines) or "No instances configured")

        @tree.command(description="Start a script on an instance")
        @app_commands.autocomplete(instance=instance_ac, script=script_ac)
        async def start(inter: discord.Interaction, instance: str, script: str | None = None):
            if not allowed(inter):
                return await deny(inter)
            if instance == "all":
                msg = "\n".join(m.start_all())
            else:
                msg = m.start(instance, script)
            await inter.response.send_message(msg)

        @tree.command(description="Stop an instance (or all)")
        @app_commands.autocomplete(instance=instance_ac)
        async def stop(inter: discord.Interaction, instance: str):
            if not allowed(inter):
                return await deny(inter)
            msg = "\n".join(m.stop_all()) if instance == "all" else m.stop(instance)
            await inter.response.send_message(msg)

        @tree.command(description="Pause an instance")
        @app_commands.autocomplete(instance=instance_ac)
        async def pause(inter: discord.Interaction, instance: str):
            if not allowed(inter):
                return await deny(inter)
            await inter.response.send_message(m.pause(instance))

        @tree.command(description="Resume a paused instance")
        @app_commands.autocomplete(instance=instance_ac)
        async def resume(inter: discord.Interaction, instance: str):
            if not allowed(inter):
                return await deny(inter)
            await inter.response.send_message(m.resume(instance))

        @tree.command(description="Live screenshot of an instance")
        @app_commands.autocomplete(instance=instance_ac)
        async def screenshot(inter: discord.Interaction, instance: str):
            if not allowed(inter):
                return await deny(inter)
            await inter.response.defer()
            try:
                img = await asyncio.to_thread(m.screenshot, instance)
                ok, buf = cv2.imencode(".png", img)
                await inter.followup.send(file=discord.File(io.BytesIO(buf.tobytes()), "screen.png"))
            except Exception as e:  # noqa: BLE001
                await inter.followup.send(f"Screenshot failed: {e}")

        @tree.command(description="Runs, crests, errors and uptime")
        @app_commands.autocomplete(instance=instance_ac)
        async def stats(inter: discord.Interaction, instance: str | None = None):
            data = m.stats.all()
            names = [instance] if instance and instance != "all" else list(data)
            embed = discord.Embed(title="Rerun stats")
            for n in names:
                d = data.get(n, {})
                total = d.get("seconds_run", 0) + m.stats.uptime(n)
                body = "\n".join(f"{k.replace('_', ' ')}: **{v}**" for k, v in sorted(d.items())
                                 if k != "seconds_run") or "nothing yet"
                embed.add_field(name=f"{n} (run time {fmt_duration(total)})", value=body[:1000])
            if not names:
                embed.description = "No stats yet"
            await inter.response.send_message(embed=embed)

        @tree.command(description="Reset an instance's stats (runs, crests, potions, run time)")
        @app_commands.autocomplete(instance=instance_ac)
        async def resetstats(inter: discord.Interaction, instance: str):
            if not allowed(inter):
                return await deny(inter)
            await inter.response.send_message(m.reset_stats(None if instance == "all" else instance))

        @tree.command(description="Recent crests, refills and problems")
        @app_commands.autocomplete(instance=instance_ac)
        async def history(inter: discord.Interaction, instance: str | None = None, count: int = 10):
            name = None if not instance or instance == "all" else instance
            items = m.history.recent(max(1, min(count, 25)), name)
            if not items:
                return await inter.response.send_message("No history yet")
            lines = [f"`{time.strftime('%m-%d %H:%M', time.localtime(e['t']))}` **{e['instance']}** "
                     f"{e['detail']}" for e in items]
            s = m.history.crest_summary(name)
            head = f"Crests kept **{s.get('kept', 0)}**, scrapped **{s.get('scrapped', 0)}**\n"
            await inter.response.send_message((head + "\n".join(lines))[:1900])

        @tree.command(description="Summary of the last 24 hours")
        async def summary(inter: discord.Interaction):
            text = await asyncio.to_thread(m.daily_summary, False)
            await inter.response.send_message(text[:1900])

        @tree.command(description="Crest 4+ / Burst / Lv4 drops: today, session, all-time, rates")
        @app_commands.autocomplete(instance=instance_ac)
        async def crests(inter: discord.Interaction, instance: str | None = None):
            from .crest_stats import format_summary
            name = None if not instance or instance == "all" else instance
            led = getattr(m, "crests", None)
            if led is None:
                return await inter.response.send_message("Crest tracking is not available")
            s = await asyncio.to_thread(led.summary, name)
            embed = discord.Embed(title=f"Crests - {name or 'all instances'}",
                                  description=format_summary(s, "Crest drops")[:4000],
                                  color=0xF1C40F)
            shot = led.shot_path(s["last_notable"])
            if shot:
                embed.set_image(url=f"attachment://{shot.name}")
                await inter.response.send_message(embed=embed, file=discord.File(str(shot), shot.name))
            else:
                await inter.response.send_message(embed=embed)

        @tree.command(description="List available scripts")
        async def scripts(inter: discord.Interaction):
            lines = [f"`{k}` - {label}" for k, label in m.scripts_available().items()]
            await inter.response.send_message("\n".join(lines) or "No scripts")

        @client.event
        async def on_ready():
            try:
                await tree.sync()
            except Exception as e:  # noqa: BLE001
                m.log("discord", f"Could not register slash commands: {e}")
            bot.ready.set()
            m.log("discord", f"Discord bot online as {client.user}")

        return client
