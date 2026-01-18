# AVCNV 音视频格式转换器
<img width="1593" height="771" alt="1766453296351" src="https://github.com/user-attachments/assets/5f4860ff-c95e-4426-bac6-84df953ee291" />

AVCNV是基于FFmpeg 的音视频格式转换工具
目前只支持部署到Docker，主要应用于NAS中批量对音频、视频格式编码、裁剪等

## 🎯 使用说明

### 1. docker部署
**docker-compose.yml**:
```
version: '3.8'

services:
  web:
    image: evilhsu/avcnv:latest
    container_name: avcnv
    ports:
      - "5123:5123"
    volumes:
      - ./uploads:/app/uploads          #./uploads映射为自己对应的NAS文件夹
      - ./localfiles:/app/localfiles    #./localfiles映射为自己对应的NAS文件夹
      - ./outputs:/app/outputs          #./outputs映射为自己对应的NAS文件夹
    environment:
      - LOG_LEVEL=INFO
      # 增加集成GPU的硬件支持 
      # iHD (Intel新) / i965 (Intel旧) / radeonsi (AMD) 根据对应CPU来填写  如GPU:Intel UHD Graphics P630 就填写 iHD
      - LIBVA_DRIVER_NAME=iHD
    devices:
      - /dev/dri:/dev/dri
    restart: always
```

### 2. 转换选项

**输出格式**:
- 视频: MP4, AVI, MKV, MOV
- 音频: MP3, WAV, AAC, FLAC

**高级选项（可选）**:

视频选项:
- 视频编码器: H.264, H.265/HEVC, 或保持原样（不重新编码）
- 分辨率: 1080p, 720p, 480p, 360p
- 视频比特率: 5000k, 2500k, 1000k
- 帧率: 60fps, 30fps, 24fps
- 音频比特率: 192k, 128k, 96k

音频选项:
- 音频编码器: AAC, MP3, FLAC, 或保持原样
- 音频比特率: 320k, 256k, 192k, 128k, 96k
- 采样率: 48000Hz, 44100Hz, 32000Hz, 22050Hz
- 声道: 立体声, 单声道
- 音频精度: 8-bit,16-bit,24-bit,32-bit,32-bit float,64-bit
- 音量调整: +200%, +150%, -50%

**2026-1-6：软件优化**：
- 增加精度音频参数调整
- 增加GPU硬件编码支持（仅支持集成GPU）
- 优化使用逻辑及美化部分显示

**2026-1-18：软件优化**：
- 增加网易云音乐的文件解码
- 解决WEBM转码失败问题
- 增加音频文件并发模式（提升音频解码效率）

MIT License © 2025 风泽

**享受使用！** 🎉
