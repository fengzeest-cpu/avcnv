from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, FileResponse
from typing import List
import os
import uuid
import logging
from pathlib import Path
import aiofiles

from models import (
    ConvertRequest, BatchConvertResponse, FileStatus, TaskStatus,
    FileInfo, UploadResponse, ErrorResponse, MediaType, FileSource
)
from converter import convert_file, is_supported_format, get_media_type, terminate_task_processes, validate_format_conversion

logger = logging.getLogger(__name__)

router = APIRouter()

# 配置路径 - 自动检测环境
# 如果在 Docker 中运行，使用 /app，否则使用项目根目录
if Path("/app").exists() and Path("/app/main.py").exists():
    # Docker 环境
    BASE_DIR = Path("/app")
else:
    # 本地开发环境 - 使用项目根目录
    BASE_DIR = Path(__file__).resolve().parent

UPLOAD_DIR = BASE_DIR / "uploads"
LOCAL_DIR = BASE_DIR / "localfiles"
OUTPUT_DIR = BASE_DIR / "outputs"

# 确保目录存在
for dir_path in [UPLOAD_DIR, LOCAL_DIR, OUTPUT_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

logger.info(f"使用基础目录: {BASE_DIR}")
logger.info(f"上传目录: {UPLOAD_DIR}")
logger.info(f"本地文件目录: {LOCAL_DIR}")
logger.info(f"输出目录: {OUTPUT_DIR}")

# 最大文件大小 (字节)
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "104857600"))  # 默认100MB

# 任务存储(内存)
tasks: dict = {}


def get_file_path(filename: str, source: FileSource) -> Path:
    """根据文件来源获取完整路径"""
    if source == FileSource.UPLOAD:
        return UPLOAD_DIR / filename
    elif source == FileSource.LOCAL:
        return LOCAL_DIR / filename
    elif source == FileSource.OUTPUT:
        return OUTPUT_DIR / filename
    else:
        raise ValueError(f"未知的文件来源: {source}")


def _resolve_conflict(path: Path, strategy: str) -> Path | None:
    """根据策略处理重名文件，返回最终路径；skip 时返回 None"""
    strategy = strategy.lower()
    if not path.exists():
        return path

    if strategy == "skip":
        return None
    if strategy == "overwrite":
        return path
    if strategy == "rename":
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        counter = 1
        while True:
            candidate = parent / f"{stem}{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1
    # 默认覆盖
    return path


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...), strategy: str = "overwrite"):
    """
    上传单个文件
    """
    try:
        # 确保上传目录存在
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        # 检查文件大小
        file_content = await file.read()
        file_size = len(file_content)

        logger.info(f"接收到文件上传请求: {file.filename}, 大小: {file_size} 字节")

        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"文件大小超过限制 {MAX_FILE_SIZE / 1024 / 1024}MB"
            )

        # 检查文件格式
        if not is_supported_format(file.filename):
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式: {file.filename}"
            )

        # 冲突处理
        target_path = _resolve_conflict(UPLOAD_DIR / file.filename, strategy)
        if target_path is None:
            return UploadResponse(success=False, filename=file.filename, message="已跳过（同名文件）")

        logger.info(f"保存文件到: {target_path} (策略: {strategy})")

        async with aiofiles.open(target_path, 'wb') as f:
            await f.write(file_content)

        # 验证文件是否保存成功
        if target_path.exists():
            actual_size = target_path.stat().st_size
            logger.info(f"文件上传成功: {target_path.name}, 保存大小: {actual_size} 字节")
        else:
            logger.error(f"文件保存失败: {target_path} 不存在")

        return UploadResponse(
            success=True,
            filename=target_path.name,
            message="文件上传成功"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-multiple")
async def upload_multiple_files(files: List[UploadFile] = File(...), strategy: str = "overwrite"):
    """
    批量上传文件
    """
    # 确保上传目录存在
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    for file in files:
        try:
            # 检查文件大小
            file_content = await file.read()
            file_size = len(file_content)

            if file_size > MAX_FILE_SIZE:
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "message": f"文件大小超过限制 {MAX_FILE_SIZE / 1024 / 1024}MB"
                })
                continue

            # 检查文件格式
            if not is_supported_format(file.filename):
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "message": f"不支持的文件格式"
                })
                continue

            target_path = _resolve_conflict(UPLOAD_DIR / file.filename, strategy)
            if target_path is None:
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "message": "已跳过（同名文件）"
                })
                continue

            async with aiofiles.open(target_path, 'wb') as f:
                await f.write(file_content)

            results.append({
                "filename": target_path.name,
                "success": True,
                "message": "上传成功"
            })

            logger.info(f"文件上传成功: {target_path.name}, 大小: {file_size} 字节, 路径: {target_path}")

        except Exception as e:
            logger.error(f"文件上传失败 {file.filename}: {e}")
            results.append({
                "filename": file.filename,
                "success": False,
                "message": str(e)
            })

    return {"results": results}


@router.get("/local-files", response_model=List[FileInfo])
async def list_local_files():
    """
    列出本地文件目录中的可用文件（包括子目录）
    """
    try:
        files = []

        if not LOCAL_DIR.exists():
            LOCAL_DIR.mkdir(parents=True, exist_ok=True)
            return files

        # 递归遍历所有文件（包括子目录）
        for file_path in LOCAL_DIR.rglob('*'):
            if file_path.is_file():
                # 检查是否为支持的格式
                if is_supported_format(file_path.name):
                    # 使用相对于LOCAL_DIR的路径作为filename
                    relative_path = file_path.relative_to(LOCAL_DIR)
                    file_info = FileInfo(
                        filename=str(relative_path).replace('\\', '/'),  # 统一使用/分隔符
                        path=str(file_path),
                        size=file_path.stat().st_size,
                        media_type=get_media_type(file_path.name),
                        last_modified=file_path.stat().st_mtime
                    )
                    files.append(file_info)

        logger.info(f"找到 {len(files)} 个本地文件")
        return files

    except Exception as e:
        logger.error(f"列出本地文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/uploaded-files", response_model=List[FileInfo])
async def list_uploaded_files():
    """
    列出已上传的文件
    """
    try:
        files = []

        if not UPLOAD_DIR.exists():
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            return files

        # 遍历上传目录中的所有文件
        for file_path in UPLOAD_DIR.iterdir():
            if file_path.is_file() and file_path.name != '.gitkeep':
                # 检查是否为支持的格式
                if is_supported_format(file_path.name):
                    file_info = FileInfo(
                        filename=file_path.name,
                        path=str(file_path),
                        size=file_path.stat().st_size,
                        media_type=get_media_type(file_path.name),
                        last_modified=file_path.stat().st_mtime
                    )
                    files.append(file_info)

        logger.info(f"找到 {len(files)} 个已上传文件")
        return files

    except Exception as e:
        logger.error(f"列出已上传文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/output-files", response_model=List[FileInfo])
async def list_output_files():
    """
    列出已完成的输出文件
    """
    try:
        files = []

        if not OUTPUT_DIR.exists():
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            return files

        # 递归遍历输出目录中的所有文件（包括子目录）
        def scan_directory(directory: Path, base_dir: Path):
            for item in directory.iterdir():
                if item.is_file() and item.name != '.gitkeep':
                    # 检查是否为支持的格式
                    if is_supported_format(item.name):
                        # 获取相对于 OUTPUT_DIR 的路径
                        relative_path = item.relative_to(base_dir)
                        file_info = FileInfo(
                            filename=str(relative_path).replace('\\', '/'),
                            path=str(item),
                            size=item.stat().st_size,
                            media_type=get_media_type(item.name),
                            last_modified=item.stat().st_mtime
                        )
                        files.append(file_info)
                elif item.is_dir():
                    # 递归扫描子目录
                    scan_directory(item, base_dir)

        scan_directory(OUTPUT_DIR, OUTPUT_DIR)

        logger.info(f"找到 {len(files)} 个输出文件")
        return files

    except Exception as e:
        logger.error(f"列出输出文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_batch_convert(task_id: str, request: ConvertRequest):
    """
    后台任务: 批量转换文件
    """
    try:
        task_data = tasks[task_id]

        # 重置停止标志，允许任务继续执行
        task_data["stopped"] = False

        for idx, filename in enumerate(request.files):
            # 检查是否被停止
            if task_data.get("stopped", False):
                logger.info(f"任务 {task_id} 已被停止")
                break

            # 跳过已完成的文件
            if task_data["files"][idx]["status"] == TaskStatus.COMPLETED:
                logger.info(f"跳过已完成的文件: {filename}")
                continue

            try:
                # 更新文件状态为处理中
                task_data["files"][idx]["status"] = TaskStatus.PROCESSING
                task_data["files"][idx]["progress"] = 0.0

                # 获取输入文件路径
                input_path = get_file_path(filename, request.source)

                if not input_path.exists():
                    # 添加详细的调试信息
                    logger.error(f"文件不存在: {filename}")
                    logger.error(f"尝试的路径: {input_path}")
                    logger.error(f"路径是否存在: {input_path.exists()}")
                    logger.error(f"父目录是否存在: {input_path.parent.exists()}")
                    if input_path.parent.exists():
                        logger.error(f"父目录内容: {list(input_path.parent.iterdir())}")
                    raise FileNotFoundError(f"文件不存在: {filename}")

                # 生成输出文件路径,保留子目录结构
                # filename 可能包含子目录,如 "001仙逆/003仙逆 第0003章 测试.wma"
                file_path_obj = Path(filename)
                output_filename = f"{file_path_obj.stem}.{request.output_format}"

                # 如果有父目录,在输出目录中也创建相同的结构
                if file_path_obj.parent != Path('.'):
                    output_subdir = OUTPUT_DIR / file_path_obj.parent
                    output_subdir.mkdir(parents=True, exist_ok=True)
                    output_path = output_subdir / output_filename
                else:
                    output_path = OUTPUT_DIR / output_filename

                # 定义进度回调
                def progress_callback(progress: float):
                    task_data["files"][idx]["progress"] = progress
                    # 计算总体进度
                    total_progress = sum(f["progress"] for f in task_data["files"]) / len(task_data["files"])
                    task_data["overall_progress"] = round(total_progress, 2)

                # 转换选项
                options = {
                    "resolution": request.resolution,
                    "video_bitrate": request.video_bitrate,
                    "video_codec": request.video_codec,
                    "frame_rate": request.frame_rate,
                    "audio_bitrate": request.audio_bitrate,
                    "sample_rate": request.sample_rate,
                    "audio_channels": request.audio_channels,
                    "audio_codec": request.audio_codec,
                    "volume_adjust": request.volume_adjust,
                }

                # 执行转换
                success = await convert_file(
                    input_file=str(input_path),
                    output_file=str(output_path),
                    options=options,
                    progress_callback=progress_callback,
                    task_id=task_id
                )

                if success is True:
                    # 转换成功
                    task_data["files"][idx]["status"] = TaskStatus.COMPLETED
                    task_data["files"][idx]["progress"] = 100.0
                    task_data["files"][idx]["output_file"] = str(output_path)

                    # 获取输出文件大小
                    try:
                        if output_path.exists():
                            task_data["files"][idx]["output_size"] = output_path.stat().st_size
                    except Exception as size_err:
                        logger.warning(f"获取输出文件大小失败: {size_err}")

                    logger.info(f"文件转换成功: {filename} -> {output_filename}")
                elif success is None:
                    # 转换被中断（暂停）- 保持为 PENDING 状态，进度归零
                    task_data["files"][idx]["status"] = TaskStatus.PENDING
                    task_data["files"][idx]["progress"] = 0.0
                    logger.info(f"文件转换被暂停: {filename}")
                    break  # 退出循环
                else:
                    # 转换失败
                    task_data["files"][idx]["status"] = TaskStatus.FAILED
                    task_data["files"][idx]["error"] = "转换失败"
                    logger.error(f"文件转换失败: {filename}")

            except Exception as e:
                task_data["files"][idx]["status"] = TaskStatus.FAILED
                task_data["files"][idx]["error"] = str(e)
                logger.error(f"处理文件异常 {filename}: {e}")

        # 计算最终总体进度
        total_progress = sum(f["progress"] for f in task_data["files"]) / len(task_data["files"])
        task_data["overall_progress"] = round(total_progress, 2)

        logger.info(f"批量转换任务完成: {task_id}")

    except Exception as e:
        logger.error(f"批量转换任务异常 {task_id}: {e}")


@router.post("/convert", response_model=BatchConvertResponse)
async def convert(request: ConvertRequest, background_tasks: BackgroundTasks):
    """
    开始批量转换
    """
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 初始化任务数据
        file_statuses = []
        for filename in request.files:
            file_status = {
                "filename": filename,
                "status": TaskStatus.PENDING,
                "progress": 0.0,
                "error": None,
                "output_file": None,
                "output_size": None
            }
            file_statuses.append(file_status)

        task_data = {
            "task_id": task_id,
            "total_files": len(request.files),
            "files": file_statuses,
            "overall_progress": 0.0,
            "stopped": False,
            "paused": False,
            "source": request.source.value  # 保存原始来源
        }

        tasks[task_id] = task_data

        # 添加后台任务
        background_tasks.add_task(process_batch_convert, task_id, request)

        logger.info(f"创建批量转换任务: {task_id}, 文件数: {len(request.files)}")

        # 返回初始状态
        return BatchConvertResponse(
            task_id=task_id,
            total_files=task_data["total_files"],
            files=[FileStatus(**f) for f in task_data["files"]],
            overall_progress=task_data["overall_progress"]
        )

    except Exception as e:
        logger.error(f"创建转换任务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{task_id}", response_model=BatchConvertResponse)
async def get_status(task_id: str):
    """
    查询任务状态
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_data = tasks[task_id]

    return BatchConvertResponse(
        task_id=task_id,
        total_files=task_data["total_files"],
        files=[FileStatus(**f) for f in task_data["files"]],
        overall_progress=task_data["overall_progress"]
    )


@router.post("/pause/{task_id}")
async def pause_task(task_id: str):
    """
    暂停任务 - 立即终止FFmpeg进程并重置正在处理的文件
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 终止FFmpeg进程
    terminate_task_processes(task_id)

    # 标记任务为停止状态
    tasks[task_id]["stopped"] = True
    tasks[task_id]["paused"] = False

    # 记录暂停前的状态
    logger.info(f"暂停前文件状态:")
    for file_data in tasks[task_id]["files"]:
        logger.info(f"  {file_data['filename']}: {file_data['status']} - {file_data['progress']}%")

    # 只将正在处理的文件状态重置为pending，进度归零
    # 已完成和未开始的文件保持原状
    for file_data in tasks[task_id]["files"]:
        if file_data["status"] == TaskStatus.PROCESSING:
            logger.info(f"重置正在处理的文件: {file_data['filename']}")
            file_data["status"] = TaskStatus.PENDING
            file_data["progress"] = 0.0

    # 记录暂停后的状态
    logger.info(f"暂停后文件状态:")
    for file_data in tasks[task_id]["files"]:
        logger.info(f"  {file_data['filename']}: {file_data['status']} - {file_data['progress']}%")

    # 重新计算总体进度
    total_progress = sum(f["progress"] for f in tasks[task_id]["files"]) / len(tasks[task_id]["files"])
    tasks[task_id]["overall_progress"] = round(total_progress, 2)

    logger.info(f"任务 {task_id} 已暂停，正在处理的文件已重置")

    return {"status": "paused", "task_id": task_id}


@router.post("/resume/{task_id}")
async def resume_task(task_id: str, background_tasks: BackgroundTasks, request: Request = None):
    """
    恢复任务 - 继续执行被暂停的任务
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_data = tasks[task_id]

    # 尝试从请求体获取当前队列的文件名列表
    current_filenames = None
    if request:
        try:
            body = await request.json()
            current_filenames = body.get("filenames")
            if current_filenames:
                logger.info(f"前端发送的当前队列文件: {current_filenames}")
        except:
            pass

    # 如果前端发送了当前队列,同步文件列表（删除已移除的,添加新增的）
    if current_filenames is not None:
        # 获取后端现有的文件名
        backend_filenames = [f["filename"] for f in task_data["files"]]

        # 1. 过滤掉已删除的文件
        original_count = len(task_data["files"])
        task_data["files"] = [
            f for f in task_data["files"]
            if f["filename"] in current_filenames
        ]
        removed_count = original_count - len(task_data["files"])
        if removed_count > 0:
            logger.info(f"从任务中移除了 {removed_count} 个已删除的文件")

        # 2. 添加新增的文件
        new_filenames = [f for f in current_filenames if f not in backend_filenames]
        if new_filenames:
            logger.info(f"发现新增文件: {new_filenames}")
            for new_filename in new_filenames:
                # 为新文件创建状态记录
                file_status = {
                    "filename": new_filename,
                    "status": TaskStatus.PENDING,
                    "progress": 0.0,
                    "error": None,
                    "output_file": None
                }
                task_data["files"].append(file_status)
            logger.info(f"已添加 {len(new_filenames)} 个新文件到任务")

        logger.info(f"当前任务文件列表: {[f['filename'] for f in task_data['files']]}")

        # 更新总文件数
        task_data["total_files"] = len(task_data["files"])

    # 重置停止标志
    task_data["stopped"] = False
    task_data["paused"] = False

    # 获取原始来源（从任务数据中读取，而不是推断）
    if "source" in task_data:
        source = FileSource(task_data["source"])
        logger.info(f"从任务数据读取来源: {source}")
    else:
        # 兼容旧任务：从第一个文件推断来源
        first_file = task_data["files"][0]["filename"]
        upload_path = UPLOAD_DIR / first_file
        local_path = LOCAL_DIR / first_file

        logger.info(f"检测文件来源: {first_file}")
        logger.info(f"uploads 路径: {upload_path}, 存在: {upload_path.exists()}")
        logger.info(f"localfiles 路径: {local_path}, 存在: {local_path.exists()}")

        if upload_path.exists():
            source = FileSource.UPLOAD
            logger.info(f"选择来源: UPLOAD")
        elif local_path.exists():
            source = FileSource.LOCAL
            logger.info(f"选择来源: LOCAL")
        else:
            raise HTTPException(status_code=404, detail="找不到文件来源")

    # 从已完成的文件中推断输出格式
    output_format = "mp4"  # 默认值
    for file_data in task_data["files"]:
        if file_data.get("output_file"):
            # 从输出文件路径提取格式
            output_format = Path(file_data["output_file"]).suffix.lstrip('.')
            logger.info(f"从输出文件推断格式: {output_format}")
            break

    # 构建请求对象
    file_list = [f["filename"] for f in task_data["files"]]
    convert_request = ConvertRequest(
        files=file_list,
        source=source,
        output_format=output_format,
        resolution=None,
        video_bitrate=None,
        audio_bitrate=None,
        sample_rate=None,
        audio_channels=None,
        video_codec="libx264",
        audio_codec="aac"
    )

    # 启动后台任务继续转换
    background_tasks.add_task(process_batch_convert, task_id, convert_request)

    logger.info(f"恢复任务: {task_id}")

    return {"status": "resumed", "task_id": task_id}


@router.post("/stop/{task_id}")
async def stop_task(task_id: str):
    """
    停止任务
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    tasks[task_id]["stopped"] = True
    tasks[task_id]["paused"] = False  # 如果正在暂停，也要取消暂停标志以便退出循环
    logger.info(f"任务 {task_id} 已停止")

    return {"status": "stopped", "task_id": task_id}


@router.delete("/cleanup/{filename}")
async def cleanup_file(filename: str, source: str = "upload"):
    """
    清理临时文件
    """
    try:
        file_source = FileSource(source)
        file_path = get_file_path(filename, file_source)

        if file_path.exists():
            file_path.unlink()
            logger.info(f"文件已删除: {filename}")
            return {"success": True, "message": "文件已删除"}
        else:
            raise HTTPException(status_code=404, detail="文件不存在")

    except ValueError:
        raise HTTPException(status_code=400, detail="无效的文件来源")
    except Exception as e:
        logger.error(f"删除文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/outputs", response_model=List[FileInfo])
async def list_output_files():
    """
    列出输出文件
    """
    try:
        files = []

        if not OUTPUT_DIR.exists():
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            return files

        for file_path in OUTPUT_DIR.iterdir():
            if file_path.is_file():
                file_info = FileInfo(
                    filename=file_path.name,
                    path=str(file_path),
                    size=file_path.stat().st_size,
                    media_type=get_media_type(file_path.name),
                    last_modified=file_path.stat().st_mtime
                )
                files.append(file_info)

        return files

    except Exception as e:
        logger.error(f"列出输出文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{filename:path}")
async def download_file(filename: str):
    """
    下载转换后的文件
    """
    try:
        # 处理可能包含子目录的文件名
        file_path = OUTPUT_DIR / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        # 检查文件路径是否在OUTPUT_DIR内（安全检查）
        if not str(file_path.resolve()).startswith(str(OUTPUT_DIR.resolve())):
            raise HTTPException(status_code=403, detail="无权访问该文件")

        # 获取文件名（不含路径）用于下载
        download_name = Path(filename).name

        return FileResponse(
            path=str(file_path),
            filename=download_name,
            media_type='application/octet-stream'
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/paths")
async def debug_paths():
    """
    调试端点：显示目录信息
    """
    import os

    def check_dir(path: Path):
        return {
            "path": str(path),
            "exists": path.exists(),
            "is_dir": path.is_dir() if path.exists() else False,
            "writable": os.access(str(path), os.W_OK) if path.exists() else False,
            "files_count": len(list(path.iterdir())) if path.exists() and path.is_dir() else 0,
            "files": [f.name for f in path.iterdir()] if path.exists() and path.is_dir() else []
        }

    return {
        "upload_dir": check_dir(UPLOAD_DIR),
        "local_dir": check_dir(LOCAL_DIR),
        "output_dir": check_dir(OUTPUT_DIR),
        "base_dir": check_dir(BASE_DIR)
    }
