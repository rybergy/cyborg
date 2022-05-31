from __future__ import annotations
import asyncio
from asyncio.futures import Future
from asyncio.locks import Lock
import logging
from pathlib import Path
from typing import Awaitable, Callable, List, Optional, TypeVar, Union
from attr import dataclass, field
import re

import discord

from discord.ext import commands
from discord.ext.commands.errors import CommandError
from pytube import YouTube, Search
from async_timeout import timeout

from cyborg.config import Config
from plumbum.cmd import ffmpeg

ffmpeg_options = {"options": "-vn"}
URL_REGEX = re.compile(
    r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?\/=]*)"
)
PLAY_USAGE = """!play usage:
!play <url> [loud <loudness>] [speed <speed>]
!play "<search_query>" [loud <loudness>] [speed <speed>]"""


class CachedDownloader:

    _config: Config

    def __init__(self, config: Config):
        self._config = config

    async def download_from_yt(self, yt: YouTube) -> Path:
        logger = logging.getLogger(__name__)

        raw_dir = self._config.cache_dir / "raw"
        raw_dir.mkdir(exist_ok=True, parents=True)

        stream = yt.streams.filter(only_audio=True)[0]

        # Store raw downloaded videos in cache_dir/raw with filename: <video_id>.mp3
        # extension = stream.default_filename.rsplit(".")[-1]
        mp3_filepath = self._config.cache_dir / "raw" / f"{yt.video_id}.mp3"
        mp4_filepath = self._config.cache_dir / "raw" / f"{yt.video_id}.mp4"

        if mp3_filepath.exists():
            logger.info(f"File for video {yt.title} already exists at {mp3_filepath}")

        else:
            logger.info(f"Downloading video {yt.title} to {mp4_filepath}")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: stream.download(
                    output_path=raw_dir, filename=mp4_filepath.name
                ),
            )

            logger.info(f"Converting {mp4_filepath} to {mp3_filepath}")
            # Convert mp3 to mp4
            await loop.run_in_executor(
                None, lambda: ffmpeg["-y", "-i", mp4_filepath, mp3_filepath]()
            )

        return mp3_filepath


class Nightcorer:

    _config: Config

    def __init__(self, config: Config):
        self._config = config

    async def nightcoreify(self, input_path: Path, speed: float) -> Path:
        logger = logging.getLogger(__name__)

        processed_dir = self._config.cache_dir / "processed"
        processed_dir.mkdir(exist_ok=True, parents=True)

        formatted_speed = str(round(speed * 100))
        output_path = (
            processed_dir / f"{input_path.stem}-nc{formatted_speed}{input_path.suffix}"
        )

        if output_path.exists():
            logger.info(
                f"Nightcored file {output_path} already exists, using cached version"
            )

        else:
            logger.info(
                f"Nightcored file at {output_path} doesn't exist, generating..."
            )

            # loop = asyncio.get_event_loop()
            # loop.run_in_executor(
            #     None,
            #     lambda: ffmpeg[
            #         "-y",
            #         "-i",
            #         input_path,
            #         "-af",
            #         f"asetrate=44100*{speed},aresample=44100",
            #         output_path,
            #     ](),
            # )
            ffmpeg[
                "-y",
                "-i",
                input_path,
                "-af",
                f"asetrate=44100*{speed},aresample=44100",
                output_path,
            ]()

        return output_path


class Loudnesser:

    _config: Config

    def __init__(self, config: Config):
        self._config = config

    async def loudify(self, input_path: Path, magnitude: float) -> Path:
        logger = logging.getLogger(__name__)

        processed_dir = self._config.cache_dir / "processed"
        processed_dir.mkdir(exist_ok=True, parents=True)

        formatted_speed = str(round(magnitude))
        output_path = (
            processed_dir
            / f"{input_path.stem}-loud{formatted_speed}{input_path.suffix}"
        )

        if output_path.exists():
            logger.info(
                f"Loudnessed file {output_path} already exists, using cached version"
            )

        else:
            logger.info(
                f"Loudnessed file at {output_path} doesn't exist, generating..."
            )
            # loop = asyncio.get_event_loop()
            # loop.run_in_executor(
            #     None,
            #     lambda: ffmpeg[
            #         "-y",
            #         "-i",
            #         input_path,
            #         "-filter:a",
            #         f"volume={formatted_speed}",
            #         output_path,
            #     ](),
            # )
            ffmpeg[
                "-y",
                "-i",
                input_path,
                "-filter:a",
                f"volume={formatted_speed}",
                output_path,
            ]()
            logger.info("Generated")

        return output_path


@dataclass
class SongArgs:

    song: YouTube
    loudness: Optional[float]
    speed: Optional[float]

    @staticmethod
    def from_args(*args: str) -> SongArgs:
        if not args:
            raise CommandError(PLAY_USAGE)

        video_spec = args[0]

        song = None
        loudness = None
        speed = None

        # Check if the first arg is a link - if not we have to search
        if URL_REGEX.match(video_spec) is not None:
            song = YouTube(video_spec)

        else:
            search = Search(video_spec)

            if not search.results:
                raise CommandError(f"No search results found for '{video_spec}'!")

            song = search.results[0]

        def expect_param(i_val: int) -> float:
            if i_val >= len(args):
                raise CommandError(PLAY_USAGE)

            try:
                return float(args[i_val])
            except ValueError:
                raise CommandError("Invalid value specified for parameter!")

        i = 1
        while i < len(args):
            param = args[i]

            if param in ("speed", "nc"):
                speed = expect_param(i + 1)
                i += 1

            elif param in ("loud", "loudness", "earrape"):
                loudness = expect_param(i + 1)
                i += 1

            i += 1

        return SongArgs(song=song, loudness=loudness, speed=speed)


@dataclass
class QueuedSong:
    song: YouTube
    downloader: CachedDownloader
    post_process: Optional[Callable[[Path], Awaitable[Path]]]

    _filepath: Optional[Path] = field(init=False, default=None)

    async def retrieve(self) -> None:
        raw_song_path = await self.downloader.download_from_yt(self.song)
        if self.post_process is not None:
            raw_song_path = await self.post_process(raw_song_path)
        self._filepath = raw_song_path

    async def wait(self, *, timeout_s: float = 10, interval_s: float = 1) -> bool:
        async with timeout(timeout_s) as cm:
            while self._filepath is None:
                await asyncio.sleep(interval_s)

        return not cm.expired

    @property
    def filepath(self) -> Path:
        if self._filepath is None:
            raise RuntimeError("Internal error: filepath is None")
        return self._filepath


class Queue:

    _queue: List[QueuedSong]
    _index: int

    def __init__(self) -> None:
        self._init()

    def _init(self) -> None:
        self._queue = []
        self._index = 0

    def put(self, song: QueuedSong):
        self._queue.append(song)

    # TODO probably race condition lol
    def now_playing(self) -> Optional[QueuedSong]:
        if self._index >= len(self._queue):
            return None

        return self._queue[self._index]

    def list_all(self) -> List[QueuedSong]:
        return self._queue[self._index :]

    def next_song(self) -> None:
        self._index += 1

    def clear(self) -> None:
        self._init()


class Music(commands.Cog):

    _bot: commands.Bot
    _config: Config
    _downloader: CachedDownloader
    _nightcorer: Nightcorer
    _loudnesser: Loudnesser
    _queue: Queue
    _timer: Future
    _ctx: Optional[commands.Context]
    _playing: bool

    def __init__(self, bot: commands.Bot, config: Config):
        self._bot = bot
        self._config = config
        self._downloader = CachedDownloader(config)
        self._nightcorer = Nightcorer(config)
        self._loudnesser = Loudnesser(config)
        self._queue = Queue()
        self._timer = asyncio.ensure_future(self._poll_queue())
        self._ctx = None
        self._playing = False

    async def _poll_queue(self):
        logger = logging.getLogger(__name__)
        while True:
            logger.info(f"Polling voice client")
            logger.info(f"Playing: {self._playing}")

            if self._ctx is not None and not self._playing:
                await self._play_next_song(self._ctx)

            await asyncio.sleep(1)

    async def _play_next_song(self, ctx: commands.Context) -> bool:
        logger = logging.getLogger(__name__)

        song = self._queue.now_playing()

        if song is not None:
            success = await song.wait(timeout_s=30)
            if success:
                self._playing = True
                player = discord.FFmpegPCMAudio(song.filepath, **ffmpeg_options)
                ctx.voice_client.play(player, after=self._advance_queue)
                await ctx.send(f"Now playing: **{song.song.title}**")

            else:
                logger.info(f"Timed out processing {song.song.title}.")
                ctx.send(f"Timed out processing {song.song.title}.")
                self._queue.next_song()

        else:
            logger.info("No song in the queue currently")

    def _advance_queue(self, *_) -> None:
        if self._ctx is not None and self._playing:
            self._playing = False
            self._ctx.voice_client.stop()
        self._queue.next_song()

    @commands.command()
    async def join(self, ctx: commands.Context, *, channel: discord.VoiceChannel):
        """Joins a voice channel"""

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    @commands.command()
    async def play(self, ctx: commands.Context, *args):
        logger = logging.getLogger(__name__)

        logger.info("Downloading song")
        song_args = SongArgs.from_args(*args)

        await ctx.send(f"Queued **{song_args.song.title}**")

        async def post_process(path: Path) -> Path:
            song_path = path

            if song_args.speed:
                logger.info("Nightcoring song")
                song_path = await self._nightcorer.nightcoreify(path, song_args.speed)

            if song_args.loudness:
                logger.info("Loudening song")
                song_path = await self._loudnesser.loudify(
                    song_path, song_args.loudness
                )

            return song_path

        queued = QueuedSong(
            song=song_args.song,
            downloader=self._downloader,
            post_process=post_process,
        )

        self._queue.put(queued)

        await queued.retrieve()

    @commands.command()
    async def np(self, ctx: commands.Context, *_):
        np = self._queue.now_playing()
        if np is None:
            await ctx.send("There is nothing playing!")
        else:
            await ctx.send(f"Now playing: **{np.song.title}**")

    @commands.command()
    async def queue(self, ctx: commands.Context, *_):
        songs = self._queue.list_all()

        if len(songs) == 0:
            await ctx.send(f"There are no songs in the queue!")

        else:
            out = f"**-> 1. {songs[0].song.title}**"

            for index, song in enumerate(songs[1:]):
                out += f"\n{index + 2}. {song.song.title}"

            await ctx.send(out)

    @commands.command()
    async def skip(self, ctx: commands.Context, *_):
        np = self._queue.now_playing()
        if np is None:
            await ctx.send("There is nothing playing!")
        else:
            ctx.voice_client.stop()
            # self._advance_queue()
            await ctx.send(f"Skipped **{np.song.title}**.")

    @commands.command()
    async def clear(self, ctx: commands.Context, *_):
        self._queue.clear()
        await ctx.send(f"Cleared the queue.")

    @commands.command()
    async def volume(self, ctx: commands.Context, volume: int):
        """Changes the player's volume"""

        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send("Changed volume to {}%".format(volume))

    @commands.command()
    async def stop(self, ctx: commands.Context):
        """Stops and disconnects the bot from voice"""
        await ctx.voice_client.disconnect()

    @commands.command()
    async def reset(self, ctx: commands.Context):
        self._queue = Queue()
        await ctx.send("Reset bot state.")

    @play.before_invoke
    @np.before_invoke
    @queue.before_invoke
    @skip.before_invoke
    @clear.before_invoke
    @volume.before_invoke
    async def ensure_voice(self, ctx: commands.Context):
        self._ctx = ctx
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                raise commands.CommandError("You are not connected to a voice channel.")
