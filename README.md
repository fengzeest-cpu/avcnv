# AVCNV 音视频格式转换器

基于 FastAPI + FFmpeg 的 Web 音视频格式转换服务，支持批量转换、实时进度显示、本地文件管理等功能。

## ✨ 主要特性

- 🎬 **多格式支持**: 支持 MP4, AVI, MKV, MOV, MP3, WAV, AAC, FLAC 等常见格式
- 📦 **批量转换**: 一次性转换多个文件，自动队列管理
- 📊 **实时进度**: 转换进度实时显示，支持暂停和恢复
- 🎛️ **高级选项**: 自定义分辨率、比特率、编码器、采样率等参数
- 💾 **批量下载**: 支持选中多个文件批量下载
- 🐳 **项目部署**: 支持本地运行（需安装python和ffmpeg）及docker部署


## 📁 项目结构

```

avcnv/
├── main.py              # FastAPI 主应用
├── routes.py            # API 路由定义
├── converter.py         # FFmpeg 转换逻辑
├── models.py            # 数据模型
├── requirements.txt     # Python 依赖
├── static/              # 静态资源
│   ├── css/
│   │   ├── bootstrap.min.css
│   │   ├── bootstrap-icons.min.css
│   │   └── style.css
│   ├── js/
│   │   ├── bootstrap.bundle.min.js
│   │   └── app.js
│   └── fonts/
│       ├── bootstrap-icons.woff2
│       └── bootstrap-icons.woff
├── templates/           # HTML 模板
│   └── index.html
├── uploads/             # 上传文件目录
├── local_files/         # 本地文件目录
└── outputs/             # 输出文件目录

avcnv/
├── Dockerfile           # Docker 镜像配置 （编译时放在avcnv文件夹同目录）
```


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
        - ./uploads:/app/uploads          #上传文件存储-映射至自己需要的文件夹
        - ./localfiles:/app/localfiles    #本地文件读取-映射至自己需要的文件夹
        - ./outputs:/app/outputs          #输出文件存储-映射至自己需要的文件夹
      environment:
        - MAX_FILE_SIZE=104857600         #限制上传文件大小
        - LOG_LEVEL=INFO
      restart: unless-stopped
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


MIT License © 2025 风泽

**享受使用！** 🎉
