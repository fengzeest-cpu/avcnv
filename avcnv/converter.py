import asyncio
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Callable

from models import MediaType

logger = logging.getLogger(__name__)

MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_BIN_DIRS = [
    MODULE_DIR / "bin",
    MODULE_DIR.parent / "bin",
    MODULE_DIR.parent.parent / "bin",
]
_BINARY_CACHE: Dict[str, str] = {}

# 全局进程管理器 - 用于存储当前正在运行的FFmpeg进程
_ACTIVE_PROCESSES: Dict[str, asyncio.subprocess.Process] = {}


# 支持的格式配置
SUPPORTED_FORMATS = {
    "audio": ["mp3", "wav", "aac", "flac", "ogg", "m4a", "wma"],
    "video": ["mp4", "avi", "mkv", "mov", "webm", "flv", "wmv", "mpeg"]
}

def _exe_name(base: str) -> str:
    if os.name == "nt" and not base.lower().endswith(".exe"):
        return f"{base}.exe"
    return base


def _resolve_binary(env_var: str, executable_name: str) -> str:
    cache_key = f"{env_var}:{executable_name}"
    if cache_key in _BINARY_CACHE:
        return _BINARY_CACHE[cache_key]

    exe_name = _exe_name(executable_name)
    candidates = []

    env_value = os.getenv(env_var)
    if env_value:
        candidates.append(Path(env_value))

    which_path = shutil.which(executable_name)
    if which_path:
        candidates.append(Path(which_path))

    for directory in DEFAULT_BIN_DIRS:
        candidates.append(directory / exe_name)

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_dir():
            path = path / exe_name
        if path.exists():
            resolved = str(path)
            _BINARY_CACHE[cache_key] = resolved
            logger.info(f"使用 {executable_name} 可执行文件: {resolved}")
            return resolved

    raise FileNotFoundError(
        f"未找到 {executable_name} 可执行文件，请将其加入 PATH 或设置环境变量 {env_var}"
    )


def get_ffmpeg_command() -> str:
    return _resolve_binary("FFMPEG_PATH", "ffmpeg")


def get_ffprobe_command() -> str:
    return _resolve_binary("FFPROBE_PATH", "ffprobe")


def terminate_task_processes(task_id: str):
    """
    终止指定任务的所有FFmpeg进程

    Args:
        task_id: 任务ID
    """
    if task_id in _ACTIVE_PROCESSES:
        process = _ACTIVE_PROCESSES[task_id]
        try:
            if process.returncode is None:  # 进程还在运行
                process.terminate()
                logger.info(f"已终止任务 {task_id} 的FFmpeg进程")
        except Exception as e:
            logger.error(f"终止进程失败: {e}")
        finally:
            # 从字典中移除
            del _ACTIVE_PROCESSES[task_id]


def get_media_type(file_path: str) -> Optional[MediaType]:
    """根据文件扩展名判断媒体类型"""
    ext = Path(file_path).suffix.lstrip('.').lower()

    if ext in SUPPORTED_FORMATS["audio"]:
        return MediaType.AUDIO
    elif ext in SUPPORTED_FORMATS["video"]:
        return MediaType.VIDEO

    return None


def is_supported_format(file_path: str) -> bool:
    """检查文件格式是否支持"""
    return get_media_type(file_path) is not None


def validate_format_conversion(source_filename: str, target_format: str) -> tuple[bool, str]:
    """
    验证格式转换是否合理
    """
    source_type = get_media_type(source_filename)

    # 获取目标格式的类型
    target_format_lower = target_format.lower()
    target_type = None
    if target_format_lower in SUPPORTED_FORMATS["audio"]:
        target_type = MediaType.AUDIO
    elif target_format_lower in SUPPORTED_FORMATS["video"]:
        target_type = MediaType.VIDEO
    else:
        return False, f"不支持的目标格式: {target_format}"

    # 检查源类型
    if source_type is None:
        return False, f"不支持的源文件格式: {source_filename}"

    # 音频转视频不合理
    if source_type == MediaType.AUDIO and target_type == MediaType.VIDEO:
        return False, f"不能将音频文件({source_filename})转换为视频格式({target_format})"
    
    return True, ""


def get_file_duration(file_path: str) -> float:
    """
    获取媒体文件时长(秒)
    用于计算转换进度百分比
    """
    try:
        cmd = [
            get_ffprobe_command(),
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(file_path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
        else:
            logger.warning(f"无法获取文件时长: {file_path}")
            return 0.0

    except FileNotFoundError as e:
        logger.error(f"获取文件时长失败: {e}")
        return 0.0
    except Exception as e:
        logger.error(f"获取文件时长失败: {e}")
        return 0.0


def parse_progress(stderr_line: str, duration: float) -> Optional[float]:
    """
    从FFmpeg的stderr输出解析进度
    返回进度百分比 (0-100)

    支持两种格式:
    1. 标准格式: time=00:01:23.45
    2. Progress格式: out_time_ms=83450000 (微秒)
    """
    if not duration or duration <= 0:
        return None

    # 尝试解析 progress 格式 (微秒)
    progress_match = re.search(r'out_time_ms=(\d+)', stderr_line)
    if progress_match:
        microseconds = int(progress_match.group(1))
        current_time = microseconds / 1000000.0  # 转换为秒
        progress = min((current_time / duration) * 100, 100)
        # logger.debug(f"解析进度(progress格式): time={current_time:.2f}s, duration={duration:.2f}s, progress={progress:.2f}%")
        return round(progress, 2)

    # 尝试解析标准时间格式
    time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)', stderr_line)
    if time_match:
        hours = int(time_match.group(1))
        minutes = int(time_match.group(2))
        seconds = float(time_match.group(3))

        current_time = hours * 3600 + minutes * 60 + seconds
        progress = min((current_time / duration) * 100, 100)

        # logger.debug(f"解析进度(标准格式): time={hours:02d}:{minutes:02d}:{seconds:05.2f}, duration={duration:.2f}, progress={progress:.2f}%")
        return round(progress, 2)

    return None


async def convert_audio(
    input_file: str,
    output_file: str,
    bitrate: Optional[str] = None,
    sample_rate: Optional[str] = None,
    channels: Optional[str] = None,
    codec: str = "aac",
    volume_adjust: Optional[str] = None,
    progress_callback: Optional[Callable[[float], None]] = None,
    task_id: Optional[str] = None
) -> bool:
    """
    异步音频转换

    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        bitrate: 音频比特率,如 '192k'
        sample_rate: 采样率,如 '44100'
        channels: 声道数,如 '2'
        codec: 音频编码器
        volume_adjust: 音量调整倍数,如 '1.5'
        progress_callback: 进度回调函数

    Returns:
        转换是否成功
    """
    try:
        # 根据输出文件格式自动选择合适的编码器
        output_ext = Path(output_file).suffix.lstrip('.').lower()

        # 检查是否使用copy模式
        is_copy_mode = codec == 'copy'
        has_audio_params = bitrate or sample_rate or channels or volume_adjust

        # 如果是copy模式，检查格式兼容性
        if is_copy_mode:
            # 获取输入文件的编码格式
            input_ext = Path(input_file).suffix.lstrip('.').lower()

            # 定义不兼容的copy组合（源格式 -> 目标格式）
            # 这些组合必须重新编码
            incompatible_combinations = [
                # WMA不能直接copy到MP3/AAC/FLAC/WAV
                ('wma', 'mp3'), ('wma', 'aac'), ('wma', 'flac'), ('wma', 'wav'),
                # M4A/AAC不能直接copy到MP3/WMA
                ('m4a', 'mp3'), ('m4a', 'wma'), ('aac', 'mp3'), ('aac', 'wma'),
                # MP3不能直接copy到AAC/WMA/FLAC
                ('mp3', 'aac'), ('mp3', 'wma'), ('mp3', 'flac'),
                # FLAC不能直接copy到MP3/AAC/WMA
                ('flac', 'mp3'), ('flac', 'aac'), ('flac', 'wma'),
                # WAV不能直接copy到压缩格式（WAV是PCM，需要编码）
                ('wav', 'mp3'), ('wav', 'aac'), ('wav', 'wma'), ('wav', 'flac'),
            ]

            if (input_ext, output_ext) in incompatible_combinations:
                logger.warning(f"检测到不兼容的copy操作: {input_ext} -> {output_ext}，自动切换到重新编码")
                is_copy_mode = False
                # 根据目标格式选择编码器
                if output_ext == 'mp3':
                    codec = 'libmp3lame'
                elif output_ext in ['aac', 'm4a']:
                    codec = 'aac'
                elif output_ext == 'flac':
                    codec = 'flac'
                else:
                    codec = 'aac'  # 默认使用aac

        # 如果不是copy模式，根据输出格式自动选择编码器
        if not is_copy_mode:
            if output_ext == 'mp3':
                codec = 'libmp3lame'
            elif output_ext in ['m4a', 'aac']:
                codec = 'aac'

        # 如果选择了copy模式但设置了音频参数，则强制使用编码
        if is_copy_mode and has_audio_params:
            logger.warning(f"检测到copy模式但设置了音频参数，自动切换到编码器")
            is_copy_mode = False
            if output_ext == 'mp3':
                codec = 'libmp3lame'
            elif output_ext in ['m4a', 'aac']:
                codec = 'aac'
            else:
                codec = 'aac'

        # 构建FFmpeg命令
        cmd = [get_ffmpeg_command(), '-i', str(input_file)]

        # 音频编码器
        cmd.extend(['-c:a', codec])

        # 只在非copy模式下应用音频参数
        if not is_copy_mode:
            # 音频比特率
            if bitrate:
                cmd.extend(['-b:a', bitrate])

            # 采样率
            if sample_rate:
                cmd.extend(['-ar', sample_rate])

            # 声道数
            if channels:
                cmd.extend(['-ac', channels])

            # 音量调整
            if volume_adjust:
                cmd.extend(['-af', f'volume={volume_adjust}'])

        # 强制实时进度输出
        cmd.extend(['-progress', 'pipe:2'])

        # 覆盖输出文件
        cmd.extend(['-y', str(output_file)])

        logger.info(f"执行音频转换命令: {' '.join(cmd)}")

        # 获取文件时长用于计算进度
        duration = get_file_duration(input_file)

        # 执行转换
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # 存储进程以便外部可以终止
        if task_id:
            _ACTIVE_PROCESSES[task_id] = process

        # 实时读取stderr获取进度
        stderr_lines = []  # 收集所有输出
        while True:
            line = await process.stderr.readline()
            if not line:
                break

            stderr_lines.append(line)  # 保存原始行

            # 尝试多种编码方式解码（Windows 中文路径支持）
            line_str = None
            for encoding in ['utf-8', 'gbk', 'cp936', 'latin1']:
                try:
                    line_str = line.decode(encoding)
                    break
                except (UnicodeDecodeError, AttributeError):
                    continue

            if not line_str:
                line_str = line.decode('utf-8', errors='ignore')

            # 解析进度并回调
            if progress_callback and duration > 0:
                progress = parse_progress(line_str, duration)
                if progress is not None:
                    progress_callback(progress)

        # 等待进程结束
        await process.wait()

        # 检查进程是否被主动终止
        was_terminated = task_id and task_id not in _ACTIVE_PROCESSES

        # 清理进程记录
        if task_id and task_id in _ACTIVE_PROCESSES:
            del _ACTIVE_PROCESSES[task_id]

        if process.returncode == 0:
            logger.info(f"音频转换成功: {output_file}")
            if progress_callback:
                progress_callback(100.0)
            return True
        elif was_terminated:
            # 进程被主动终止（暂停），不算失败，返回 None 表示被中断
            logger.info(f"音频转换被主动终止: {output_file}")
            return None
        else:
            # 解码收集的 stderr 输出
            stderr_bytes = b''.join(stderr_lines)
            error_msg = None
            for encoding in ['utf-8', 'gbk', 'cp936']:
                try:
                    error_msg = stderr_bytes.decode(encoding)
                    break
                except (UnicodeDecodeError, AttributeError):
                    continue
            if not error_msg:
                error_msg = stderr_bytes.decode('utf-8', errors='ignore')

            logger.error(f"音频转换失败,返回码: {process.returncode}")
            logger.error(f"FFmpeg 完整输出:\n{error_msg}")
            return False

    except FileNotFoundError as e:
        # 清理进程记录
        if task_id and task_id in _ACTIVE_PROCESSES:
            del _ACTIVE_PROCESSES[task_id]
        logger.error(f"音频转换异常: {e}")
        raise
    except Exception as e:
        # 清理进程记录
        if task_id and task_id in _ACTIVE_PROCESSES:
            del _ACTIVE_PROCESSES[task_id]
        logger.error(f"音频转换异常: {e}")
        return False


async def convert_video(
    input_file: str,
    output_file: str,
    resolution: Optional[str] = None,
    video_bitrate: Optional[str] = None,
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    audio_bitrate: Optional[str] = None,
    frame_rate: Optional[str] = None,
    progress_callback: Optional[Callable[[float], None]] = None,
    task_id: Optional[str] = None
) -> bool:
    """
    异步视频转换

    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        resolution: 分辨率,如 '1920x1080'
        video_bitrate: 视频比特率,如 '2M'
        video_codec: 视频编码器
        audio_codec: 音频编码器
        audio_bitrate: 音频比特率
        frame_rate: 帧率,如 '30'
        progress_callback: 进度回调函数

    Returns:
        转换是否成功
    """
    try:
        # 获取输入和输出文件扩展名
        input_ext = Path(input_file).suffix.lstrip('.').lower()
        output_ext = Path(output_file).suffix.lstrip('.').lower()

        # 检查是否使用copy模式，如果有重新编码参数则强制使用编码器
        is_copy_mode = video_codec == 'copy'
        has_video_params = resolution or video_bitrate or frame_rate

        # 如果是copy模式，检查格式兼容性
        if is_copy_mode:
            # 定义不兼容的视频copy组合（源格式 -> 目标格式）
            # 不同容器格式的编码可能不兼容
            incompatible_video_combinations = [
                # AVI通常使用不同的编码，转换到其他格式最好重新编码
                ('avi', 'mp4'), ('avi', 'mkv'), ('avi', 'mov'),
                # MOV的某些编码不能直接复制到其他容器
                ('mov', 'avi'),
                # 不同容器之间的编码兼容性问题
                ('wmv', 'mp4'), ('wmv', 'mkv'), ('wmv', 'mov'), ('wmv', 'avi'),
            ]

            if (input_ext, output_ext) in incompatible_video_combinations:
                logger.warning(f"检测到可能不兼容的视频copy操作: {input_ext} -> {output_ext}，建议重新编码以确保兼容性")
                # 对于视频，我们给个警告但不强制，因为有些情况下copy是可行的
                # 如果用户设置了其他参数，则强制重新编码

        # 如果选择了copy模式但设置了视频参数，则强制使用libx264编码
        if is_copy_mode and has_video_params:
            logger.warning(f"检测到copy模式但设置了视频参数，自动切换到libx264编码器")
            video_codec = 'libx264'
            is_copy_mode = False

        # 构建FFmpeg命令
        cmd = [get_ffmpeg_command(), '-i', str(input_file)]

        # 视频编码器
        cmd.extend(['-c:v', video_codec])

        # 只在非copy模式下应用视频参数
        if not is_copy_mode:
            # 分辨率
            if resolution:
                cmd.extend(['-s', resolution])

            # 视频比特率
            if video_bitrate:
                cmd.extend(['-b:v', video_bitrate])

            # 帧率
            if frame_rate:
                cmd.extend(['-r', frame_rate])

        # 音频编码器
        cmd.extend(['-c:a', audio_codec])

        # 音频比特率（如果音频不是copy模式）
        if audio_codec != 'copy' and audio_bitrate:
            cmd.extend(['-b:a', audio_bitrate])

        # 强制实时进度输出
        cmd.extend(['-progress', 'pipe:2'])

        # 覆盖输出文件
        cmd.extend(['-y', str(output_file)])

        logger.info(f"执行视频转换命令: {' '.join(cmd)}")

        # 获取文件时长用于计算进度
        duration = get_file_duration(input_file)

        # 执行转换
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # 存储进程以便外部可以终止
        if task_id:
            _ACTIVE_PROCESSES[task_id] = process

        # 实时读取stderr获取进度
        stderr_lines = []  # 收集所有输出
        while True:
            line = await process.stderr.readline()
            if not line:
                break

            stderr_lines.append(line)  # 保存原始行

            # 尝试多种编码方式解码（Windows 中文路径支持）
            line_str = None
            for encoding in ['utf-8', 'gbk', 'cp936', 'latin1']:
                try:
                    line_str = line.decode(encoding)
                    break
                except (UnicodeDecodeError, AttributeError):
                    continue

            if not line_str:
                line_str = line.decode('utf-8', errors='ignore')

            # 解析进度并回调
            if progress_callback and duration > 0:
                progress = parse_progress(line_str, duration)
                if progress is not None:
                    progress_callback(progress)

        # 等待进程结束
        await process.wait()

        # 检查进程是否被主动终止
        was_terminated = task_id and task_id not in _ACTIVE_PROCESSES

        # 清理进程记录
        if task_id and task_id in _ACTIVE_PROCESSES:
            del _ACTIVE_PROCESSES[task_id]

        if process.returncode == 0:
            logger.info(f"视频转换成功: {output_file}")
            if progress_callback:
                progress_callback(100.0)
            return True
        elif was_terminated:
            # 进程被主动终止（暂停），不算失败，返回 None 表示被中断
            logger.info(f"视频转换被主动终止: {output_file}")
            return None
        else:
            # 解码收集的 stderr 输出
            stderr_bytes = b''.join(stderr_lines)
            error_msg = None
            for encoding in ['utf-8', 'gbk', 'cp936']:
                try:
                    error_msg = stderr_bytes.decode(encoding)
                    break
                except (UnicodeDecodeError, AttributeError):
                    continue
            if not error_msg:
                error_msg = stderr_bytes.decode('utf-8', errors='ignore')

            logger.error(f"视频转换失败,返回码: {process.returncode}")
            logger.error(f"FFmpeg 完整输出:\n{error_msg}")
            return False

    except FileNotFoundError as e:
        # 清理进程记录
        if task_id and task_id in _ACTIVE_PROCESSES:
            del _ACTIVE_PROCESSES[task_id]
        logger.error(f"视频转换异常: {e}")
        raise
    except Exception as e:
        # 清理进程记录
        if task_id and task_id in _ACTIVE_PROCESSES:
            del _ACTIVE_PROCESSES[task_id]
        logger.error(f"视频转换异常: {e}")
        return False


async def convert_file(
    input_file: str,
    output_file: str,
    options: Dict,
    progress_callback: Optional[Callable[[float], None]] = None,
    task_id: Optional[str] = None
) -> bool:
    """
    异步转换单个文件(自动识别音频/视频)

    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        options: 转换参数字典
        progress_callback: 进度回调函数
        task_id: 任务ID

    Returns:
        转换是否成功
    """
    media_type = get_media_type(input_file)

    if media_type == MediaType.AUDIO:
        return await convert_audio(
            input_file=input_file,
            output_file=output_file,
            bitrate=options.get('audio_bitrate'),
            sample_rate=options.get('sample_rate'),
            channels=options.get('audio_channels'),
            codec=options.get('audio_codec', 'aac'),
            volume_adjust=options.get('volume_adjust'),
            progress_callback=progress_callback,
            task_id=task_id
        )
    elif media_type == MediaType.VIDEO:
        return await convert_video(
            input_file=input_file,
            output_file=output_file,
            resolution=options.get('resolution'),
            video_bitrate=options.get('video_bitrate'),
            video_codec=options.get('video_codec', 'libx264'),
            audio_codec=options.get('audio_codec', 'aac'),
            audio_bitrate=options.get('audio_bitrate'),
            frame_rate=options.get('frame_rate'),
            progress_callback=progress_callback,
            task_id=task_id
        )
    else:
        logger.error(f"不支持的文件格式: {input_file}")
        return False
