FROM python:3.11-slim

# 安装FFmpeg和curl(用于健康检查)
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 验证FFmpeg安装
RUN ffmpeg -version

# 设置工作目录
WORKDIR /app

# 复制依赖文件并安装
COPY avcnv /app
RUN pip install -r requirements.txt

# 创建必要的目录
RUN mkdir -p /app/uploads /app/localfiles /app/outputs

# 声明数据卷（Docker会自动为这些目录创建卷）
VOLUME ["/app/uploads", "/app/localfiles", "/app/outputs"]

# 暴露端口
EXPOSE 5123

# 设置时区为中国时间
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 启动命令 - 禁用访问日志减少日志输出
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5123", "--log-level", "info", "--no-access-log"]
