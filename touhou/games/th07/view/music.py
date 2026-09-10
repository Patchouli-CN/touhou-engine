"""BGM 链: BgmPlayer(三档音源 + thbgm.dat WAV 循环段) + StageBgm(对局换曲驱动)。

播放口径照 Supervisor::PlayAudio/StopAudio/FadeOutMusic(Supervisor.cpp:1313-1467):
music_mode=Off 一律无声; WAV 档从 thbgm.dat 按 fmt 索引取 PCM 包 RIFF 播,
intro 播一遍后 [intro,total) 段无限循环(dsutil.cpp:1071-1112, mixer.music
不支持段内循环, 每帧 poll() 轮询到段尾 play(start=循环点) 回卷, 接缝 ≤1 帧);
MIDI 档播封包内 .mid 整曲循环; WAV 档 fmt 未收录/读取失败回退 MIDI
(旧 sound_player 同口径)。逻辑状态(current/paused)无声卡也记账, 供测试断言。
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pygame

from ....engine import Event
from ....engine.msg import MsgMusicChange, MsgMusicFadeout
from ....schemas.archive import Archive, load_entry
from ....schemas.stage import StdFile, parse_std
from ....schemas.thbgm import (
    THBGM_HEADER_SIZE,
    ThbgmTrack,
    build_wav,
    check_thbgm_header,
    parse_fmt,
)
from ..config import MUSIC_OFF, MUSIC_WAV
from ..world import Th07World

#: 标题曲(MainMenu.cpp:636 LoadAudio(8, "bgm/th07_01.mid"))
TITLE_BGM = "bgm/th07_01.mid"

_THBGM_GAME_ID = 0x700  # thbgm.dat 头校验的作品 id(Supervisor.cpp:1183-1230)
_REWIND_MARGIN_MS = 30  # WAV 循环段尾提前回卷余量(轮询粒度补偿)


def _stem(name: str) -> str:
    """曲目路径取 stem("bgm/th07_02.mid" → "th07_02"); 空/空白路径 → ""。"""
    base = name.replace("\\", "/").split("/")[-1].strip()
    return base.rsplit(".", 1)[0] if "." in base else base


class BgmPlayer:
    """BGM 播放器: music_mode 三档消费 + thbgm.dat WAV 循环段 + 暂停/淡出。

    archive = 主数据包(.mid/thbgm.fmt 从这取); bgm_path = thbgm.dat 路径
    (None 或头校验不过则 WAV 档整体回退 MIDI)。mixer 不可用/dummy 声卡时
    静默(dummy 下 mixer.music 原生调用间歇死锁, 旧 sound_player 实测),
    逻辑状态照常记账。
    """

    def __init__(
        self,
        archive: Archive | None,
        bgm_path: str | Path | None = None,
        *,
        mode: int = MUSIC_WAV,
    ) -> None:
        self._archive = archive
        self._bgm_path = Path(bgm_path) if bgm_path is not None else None
        self._mode = mode
        self.current = ""  # 在播曲目 stem("" = 停)
        self.paused = False
        self._tracks: dict[str, ThbgmTrack] | None = None  # None = fmt 未试载
        self._wav: ThbgmTrack | None = None  # 当前 WAV 曲(循环轮询用)
        self._wav_pass_ms = 0.0  # 本播段长度 ms(首遍=全曲, 之后=循环段)

    @property
    def mode(self) -> int:
        """当前音源档(cfg.music_mode)。"""
        return self._mode

    def set_mode(self, mode: int) -> None:
        """切音源档; 伴随的 StopAudio/重载由调用方做(MainMenu.cpp:617-637)。"""
        self._mode = mode

    # ---- 播放控制 ----
    def play(self, name: str) -> None:
        """播指定曲(PlayAudio, Supervisor.cpp:1367-1397); Off 档直接无声返回。"""
        if self._mode == MUSIC_OFF:
            return
        stem = _stem(name)
        if not stem:
            return
        self.paused = False
        ok = False
        if self._mode == MUSIC_WAV:
            # 扩展名换 .wav 按 stem 查 fmt(Supervisor.cpp:1383-1389)
            track = self._fmt().get(stem + ".wav")
            if track is not None:
                ok = self._play_wav(track)
        if not ok:
            ok = self._play_midi(stem)
        if not ok:
            self._wav = None
        self.current = stem if ok else ""

    def ensure(self, name: str) -> None:
        """只在未在播同名曲时起播(标题曲重入不重启, MainMenu.cpp:199-202/2656)。"""
        if self.current != _stem(name):
            self.play(name)

    def stop(self) -> None:
        """StopAudio(Supervisor.cpp:1400-1428)。"""
        if self._audio_ok():
            try:
                pygame.mixer.music.stop()
            except pygame.error:
                pass
        self.current = ""
        self.paused = False
        self._wav = None

    def fadeout(self, seconds: float) -> None:
        """FadeOutMusic(Supervisor.cpp:1431-1467); 参数单位秒。"""
        if self._audio_ok():
            try:
                pygame.mixer.music.fadeout(int(seconds * 1000))
            except pygame.error:
                pass
        self.current = ""
        self.paused = False
        self._wav = None

    def pause(self) -> None:
        """暂停; 原版仅 WAV 音源响应 AUDIO_PAUSE(SoundPlayer.cpp:839-853)。"""
        if self._mode != MUSIC_WAV or not self.current or self.paused:
            return
        if self._audio_ok():
            try:
                pygame.mixer.music.pause()
            except pygame.error:
                pass
        self.paused = True

    def unpause(self) -> None:
        """恢复(AUDIO_UNPAUSE, SoundPlayer.cpp:854-866)。"""
        if not self.paused:
            return
        if self._audio_ok():
            try:
                pygame.mixer.music.unpause()
            except pygame.error:
                pass
        self.paused = False

    # ---- 每帧 ----
    def poll(self) -> None:
        """WAV 循环点回卷轮询(runner 每帧调, 与 scene 无关)。"""
        track = self._wav
        if track is None or self.paused or not self._audio_ok():
            return
        try:
            if not pygame.mixer.music.get_busy():
                self._rewind(track)
                return
            pos = pygame.mixer.music.get_pos()
            if pos >= 0 and pos >= self._wav_pass_ms - _REWIND_MARGIN_MS:
                self._rewind(track)
        except pygame.error:
            pass

    def _rewind(self, track: ThbgmTrack) -> None:
        """段尾从循环点重播([intro,total) 段无限循环, dsutil.cpp:1071-1112)。"""
        pygame.mixer.music.play(0, start=track.intro_seconds)
        self._wav_pass_ms = track.loop_seconds * 1000.0

    # ---- 音源装载 ----
    def _play_wav(self, track: ThbgmTrack) -> bool:
        if not self._audio_ok():
            # 无声环境: 不读几十 MB PCM, 只记逻辑态
            self._wav = track
            self._wav_pass_ms = track.total_seconds * 1000.0
            return True
        try:
            assert self._bgm_path is not None
            with open(self._bgm_path, "rb") as f:  # 整曲单段载入, 内存至多当前一首
                f.seek(track.start_offset)
                pcm = f.read(track.total_length)
            if len(pcm) < track.total_length:
                return False
            pygame.mixer.music.load(io.BytesIO(build_wav(track, pcm)))
            pygame.mixer.music.play(0)
        except (OSError, pygame.error):
            return False
        self._wav = track
        self._wav_pass_ms = track.total_seconds * 1000.0
        return True

    def _play_midi(self, stem: str) -> bool:
        data = self._midi_bytes(stem)
        if data is None:
            return False
        if self._audio_ok():
            try:
                pygame.mixer.music.load(io.BytesIO(data))
                pygame.mixer.music.play(-1)  # 整曲循环
            except pygame.error:
                return False
        self._wav = None
        return True

    def _midi_bytes(self, stem: str) -> bytes | None:
        if self._archive is None:
            return None
        try:
            return load_entry(self._archive, stem + ".mid")
        except KeyError:
            return None

    def _fmt(self) -> dict[str, ThbgmTrack]:
        """thbgm.fmt 懒解析(LoadFmt, Supervisor.cpp:732); 失败留空走 MIDI。"""
        if self._tracks is None:
            self._tracks = {}
            if self._archive is not None and self._bgm_path is not None:
                try:
                    header = self._bgm_path.read_bytes()[:THBGM_HEADER_SIZE]
                except OSError:
                    header = b""
                if check_thbgm_header(header, game_id=_THBGM_GAME_ID):
                    try:
                        self._tracks = parse_fmt(load_entry(self._archive, "thbgm.fmt"))
                    except (KeyError, ValueError):
                        pass
        return self._tracks

    @staticmethod
    def _audio_ok() -> bool:
        """Mixer 可用且非 dummy 声卡(dummy 下 music 原生调用间歇死锁)。"""
        if os.environ.get("SDL_AUDIODRIVER") == "dummy":
            return False
        return pygame.mixer.get_init() is not None


class StageBgm:
    """对局 BGM 驱动: 关头主曲/MSG_MUSIC 换曲/ECL 音乐指令 → BgmPlayer。

    std 的 bgm_paths[0]=面曲 [1]=boss 曲(GameManager.cpp:778-787 装载);
    6 面例外: 关头 StopAudio, Gui 计 300 帧后才起面曲(GameManager.cpp:786,
    Gui.cpp:141-144)。按 world 订阅事件流 + 每帧 step 驱动。
    """

    def __init__(self, player: BgmPlayer, archive: Archive | None) -> None:
        self._player = player
        self._archive = archive
        self._stds: dict[int, StdFile | None] = {}
        self._stage_no = 0
        self._stage6_at = -1  # 6 面面曲起播帧(world.frame 口径)

    def on_event(self, ev: Event) -> None:
        """事件流订阅: MSG_MUSIC 换曲/MSG_FADEOUT_MUSIC 淡出 4 秒(Gui.cpp:974-980/1022)。"""
        if isinstance(ev, MsgMusicChange):
            self._play_track(self._stage_no, ev.music_idx)
        elif isinstance(ev, MsgMusicFadeout):
            self._player.fadeout(4.0)

    def step(self, world: Th07World) -> None:
        """每帧: ECL 音乐指令(world.frame_bgm) → 关号边沿换面曲 → 6 面延迟起播。"""
        player = self._player
        for cmd, arg in world.frame_bgm:
            if cmd == "play":
                player.play(arg)
            elif cmd == "fadeout":
                player.fadeout(arg)
        if world.stage_no != self._stage_no:
            self._stage_no = world.stage_no
            if world.stage_no == 6:
                player.stop()  # GameManager.cpp:786
                self._stage6_at = world.frame + 300
            else:
                self._stage6_at = -1
                self._play_track(world.stage_no, 0)  # GameManager.cpp:782
        if self._stage6_at >= 0 and world.frame >= self._stage6_at:
            self._stage6_at = -1
            self._play_track(6, 0)  # Gui.cpp:141-144

    def _play_track(self, stage_no: int, idx: int) -> None:
        """播 std bgm_paths[idx](PlayLoadedAudio 口径, 槽越界/空白槽静默)。"""
        std = self._std(stage_no)
        if std is None or not 0 <= idx < len(std.bgm_paths):
            return
        path = std.bgm_paths[idx].strip()
        if path:
            self._player.play(path)

    def _std(self, stage_no: int) -> StdFile | None:
        """Std 懒解析带缓存; 无数据/解析失败 = 该关无 BGM(静默降级)。"""
        if stage_no not in self._stds:
            std = None
            if self._archive is not None:
                try:
                    std = parse_std(load_entry(self._archive, f"stage{stage_no}.std"))
                except (KeyError, ValueError):
                    pass
            self._stds[stage_no] = std
        return self._stds[stage_no]
