from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum


class FileSource(str, Enum):
    """文件来源枚举"""
    UPLOAD = "upload"
    LOCAL = "local"
    OUTPUT = "output"


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MediaType(str, Enum):
    """媒体类型枚举"""
    AUDIO = "audio"
    VIDEO = "video"


class ConvertRequest(BaseModel):
    """转换请求模型"""
    files: List[str] = Field(..., description="文件路径列表")
    source: FileSource = Field(..., description="文件来源")
    output_format: str = Field(..., description="输出格式")

    # 视频参数
    resolution: Optional[str] = Field(None, description="分辨率,如 1920x1080")
    video_bitrate: Optional[str] = Field(None, description="视频比特率,如 2M")
    video_codec: Optional[str] = Field("libx264", description="视频编码器")
    frame_rate: Optional[str] = Field(None, description="帧率,如 30")

    # 音频参数
    audio_bitrate: Optional[str] = Field(None, description="音频比特率,如 192k")
    sample_rate: Optional[str] = Field(None, description="采样率,如 44100")
    audio_channels: Optional[str] = Field(None, description="声道数,如 2")
    audio_codec: Optional[str] = Field("aac", description="音频编码器")
    volume_adjust: Optional[str] = Field(None, description="音量调整,如 1.5")


class FileStatus(BaseModel):
    """单个文件转换状态"""
    filename: str = Field(..., description="文件名")
    status: TaskStatus = Field(..., description="任务状态")
    progress: float = Field(0.0, description="进度百分比 0-100")
    error: Optional[str] = Field(None, description="错误信息")
    output_file: Optional[str] = Field(None, description="输出文件路径")
    output_size: Optional[int] = Field(None, description="输出文件大小(字节)")


class BatchConvertResponse(BaseModel):
    """批量转换响应模型"""
    task_id: str = Field(..., description="任务ID")
    total_files: int = Field(..., description="总文件数")
    files: List[FileStatus] = Field(..., description="文件状态列表")
    overall_progress: float = Field(0.0, description="总体进度百分比 0-100")


class FileInfo(BaseModel):
    """文件信息模型"""
    filename: str = Field(..., description="文件名")
    path: str = Field(..., description="文件路径")
    size: int = Field(..., description="文件大小(字节)")
    media_type: Optional[MediaType] = Field(None, description="媒体类型")
    last_modified: Optional[float] = Field(None, description="最后修改时间戳(秒)")


class UploadResponse(BaseModel):
    """上传响应模型"""
    success: bool = Field(..., description="是否成功")
    filename: str = Field(..., description="文件名")
    message: str = Field(..., description="消息")


class ErrorResponse(BaseModel):
    """错误响应模型"""
    error: str = Field(..., description="错误信息")
    detail: Optional[str] = Field(None, description="详细信息")
