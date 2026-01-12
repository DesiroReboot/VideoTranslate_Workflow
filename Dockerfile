FROM python:3.11-slim

LABEL maintainer="VideoTranslate" \
      version="1.1" \
      description="Video translation system with AI services"

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . /app/

# 创建必要的目录
RUN mkdir -p /app/temp /app/output /app/logs

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# 设置权限
RUN chmod +x /app/entrypoint.sh

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# 暴露端口（如果有Web服务）
# EXPOSE 8000

# 入口点
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "main.py", "--help"]
