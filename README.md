# AVCNV 音视频格式转换器
<img width="1593" height="771" alt="1766453296351" src="https://github.com/user-attachments/assets/5f4860ff-c95e-4426-bac6-84df953ee291" />

基于 FastAPI + FFmpeg 的 Web 音视频格式转换服务，支持批量转换、实时进度显示、本地文件管理等功能。

## ✨ 主要特性

- 🎬 **多格式支持**: 支持 MP4, AVI, MKV, MOV, MP3, WAV, AAC, FLAC 等常见格式
- 📦 **批量转换**: 一次性转换多个文件，自动队列管理
- 📊 **实时进度**: 转换进度实时显示，支持暂停和恢复
- 🎛️ **高级选项**: 自定义分辨率、比特率、编码器、采样率，GPU参与转码等参数
- 💾 **批量下载**: 支持选中多个文件批量下载
- 🐳 **项目部署**: compose部署


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
      - ./uploads:/app/uploads   #映射自己对应的NAS文件夹
      - ./localfiles:/app/localfiles
      - ./outputs:/app/outputs
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
- 视频编码器: H.264, H.265/HEVC, 或复制（不重新编码）
- 分辨率: 1080p, 720p, 480p, 360p
- 视频比特率: 5000k, 2500k, 1000k
- 帧率: 60fps, 30fps, 24fps
- 音频比特率: 192k, 128k, 96k

音频选项:
- 音频编码器: AAC, MP3, FLAC, 或复制
- 音频比特率: 320k, 256k, 192k, 128k, 96k
- 采样率: 48000Hz, 44100Hz, 32000Hz, 22050Hz
- 声道: 立体声, 单声道
- 音量调整: +200%, +150%, -50%

**2026-1-6：软件优化**：
- 增加精度音频参数调整
- 增加GPU硬件编码支持（仅支持集成GPU）
- 优化使用逻辑及美化部分显示


MIT License © 2025 风泽

**享受使用！** 🎉
