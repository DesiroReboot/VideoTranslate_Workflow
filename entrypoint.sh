#!/bin/bash
set -e

echo "===================================="
echo "VideoTranslate Docker Container"
echo "===================================="
echo

# 检查必需的环境变量
check_env_var() {
    if [ -z "${!1}" ]; then
        echo "警告: 环境变量 $1 未设置"
        return 1
    fi
    return 0
}

# 检查API密钥
echo "检查API密钥..."
check_env_var "DASHSCOPE_API_KEY" || echo "  提示: 请设置 DASHSCOPE_API_KEY 环境变量"
check_env_var "ZHIPU_API_KEY" || echo "  提示: 请设置 ZHIPU_API_KEY 环境变量"
check_env_var "DEEPSEEK_API_KEY" || echo "  提示: 请设置 DEEPSEEK_API_KEY 环境变量"
echo

# 创建必要的目录
echo "初始化目录..."
mkdir -p /app/temp
mkdir -p /app/output
mkdir -p /app/logs
mkdir -p /app/temp/checkpoints
echo "目录初始化完成"
echo

# 清理旧的临时文件（可选）
if [ "${CLEANUP_ON_START}" = "true" ]; then
    echo "清理旧的临时文件..."
    find /app/temp -type f -mtime +1 -delete 2>/dev/null || true
    echo "清理完成"
    echo
fi

# 设置权限
chmod -R 755 /app/temp 2>/dev/null || true
chmod -R 755 /app/output 2>/dev/null || true
chmod -R 755 /app/logs 2>/dev/null || true

# 显示环境信息
echo "环境信息:"
echo "  Python版本: $(python --version)"
echo "  工作目录: $(pwd)"
echo "  容器ID: $(hostname)"
echo

# 如果没有传入命令，显示帮助信息
if [ $# -eq 0 ]; then
    echo "使用方法:"
    echo "  docker run -e DASHSCOPE_API_KEY=xxx video-translate \"<URL>\" <language>"
    echo "  docker run -e DASHSCOPE_API_KEY=xxx video-translate \"<video_path>\" <language> --style humorous"
    echo "  docker-compose up"
    echo
    echo "示例:"
    echo "  docker run -e DASHSCOPE_API_KEY=xxx video-translate \"https://www.bilibili.com/video/BVxxx\" English"
    echo "  docker run -e DASHSCOPE_API_KEY=xxx video-translate \"video.mp4\" Japanese --style educational"
    echo
    exec python main.py --help
fi

# 执行传入的命令
echo "执行命令: $@"
echo "===================================="
echo

exec "$@"
