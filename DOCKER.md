# Docker部署指南

VideoTranslate支持通过Docker容器化部署，简化环境配置和跨平台运行。

## 前置要求

- Docker 20.10+
- Docker Compose 2.0+

## 快速开始

### 1. 准备配置文件

创建 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，设置必要的API密钥：

```env
# 阿里云API密钥（必需）
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# 智谱AI API密钥（可选）
ZHIPU_API_KEY=your_zhipu_api_key_here

# DeepSeek API密钥（可选）
DEEPSEEK_API_KEY=your_deepseek_api_key_here

# OSS配置（可选）
OSS_ACCESS_KEY_ID=your_oss_access_key_id
OSS_ACCESS_KEY_SECRET=your_oss_access_key_secret
OSS_BUCKET_NAME=your_bucket_name

# 启动时清理旧文件
CLEANUP_ON_START=true
```

### 2. 构建镜像

```bash
docker build -t video-translate .
```

### 3. 运行容器

#### 使用Docker命令

翻译B站视频：

```bash
docker run -e DASHSCOPE_API_KEY=xxx \
  -v $(pwd)/output:/app/output \
  video-translate "https://www.bilibili.com/video/BVxxx" English
```

翻译本地视频：

```bash
docker run -e DASHSCOPE_API_KEY=xxx \
  -v $(pwd)/output:/app/output \
  -v $(pwd):/app/input:ro \
  video-translate "/app/input/video.mp4" Japanese --style humorous
```

#### 使用Docker Compose

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 4. 交互式模式

使用交互式模式进行实时操作：

```bash
docker-compose --profile interactive run --rm video-translate-interactive
```

## 高级配置

### GPU加速

如果需要GPU加速（用于加速视频处理），请确保安装了NVIDIA Docker运行时：

```bash
# 修改docker-compose.yml，取消GPU相关配置的注释
docker-compose up -d
```

### 批量处理

使用批量处理模式：

```bash
# 创建batch_tasks目录
mkdir -p batch_tasks

# 添加批量任务配置（JSON格式）
cat > batch_tasks/tasks.json << EOF
{
  "tasks": [
    {"url": "https://www.bilibili.com/video/BV1", "language": "English"},
    {"url": "https://www.bilibili.com/video/BV2", "language": "Japanese"}
  ]
}
EOF

# 运行批量处理
docker-compose --profile batch run --rm video-translate-batch
```

### 自定义配置

使用自定义配置文件：

```bash
docker run -e DASHSCOPE_API_KEY=xxx \
  -v $(pwd)/config.json:/app/config.json:ro \
  -v $(pwd)/output:/app/output \
  video-translate "https://www.bilibili.com/video/BVxxx" English --config /app/config.json
```

## 目录结构

```
.
├── Dockerfile              # Docker镜像定义
├── docker-compose.yml      # Docker Compose配置
├── .dockerignore          # Docker忽略文件
├── entrypoint.sh          # 容器入口脚本
├── .env                   # 环境变量配置
├── output/                # 输出目录（挂载）
├── temp/                  # 临时文件目录（挂载）
└── logs/                  # 日志目录（挂载）
```

## 环境变量

| 变量名 | 说明 | 必需 | 默认值 |
|--------|------|------|--------|
| `DASHSCOPE_API_KEY` | 阿里云API密钥 | 是 | - |
| `ZHIPU_API_KEY` | 智谱AI API密钥 | 否 | - |
| `DEEPSEEK_API_KEY` | DeepSeek API密钥 | 否 | - |
| `OSS_ACCESS_KEY_ID` | OSS访问密钥ID | 否 | - |
| `OSS_ACCESS_KEY_SECRET` | OSS访问密钥 | 否 | - |
| `OSS_BUCKET_NAME` | OSS存储桶名称 | 否 | - |
| `CLEANUP_ON_START` | 启动时清理旧文件 | 否 | false |

## 常见问题

### 1. 容器启动失败

检查Docker日志：

```bash
docker logs video-translate
```

确保已设置必需的环境变量。

### 2. 权限问题

在Linux/macOS上，可能需要调整文件权限：

```bash
chmod -R 755 output temp logs
```

### 3. 网络问题

确保容器可以访问外部网络：

```bash
docker run --rm video-translate ping -c 3 8.8.8.8
```

### 4. 存储空间不足

清理Docker缓存：

```bash
docker system prune -a
```

### 5. API调用失败

检查API密钥是否正确配置，并确保账户有足够的配额。

## 性能优化

### 1. 使用多阶段构建

Dockerfile已采用多阶段构建，减小镜像体积。

### 2. 启用缓存

Docker会缓存层，后续构建会更快。

### 3. 资源限制

限制容器资源使用：

```yaml
# docker-compose.yml
services:
  video-translate:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

## 生产环境部署

### 1. 使用私有镜像仓库

推送到私有仓库：

```bash
docker tag video-translate your-registry.com/video-translate:v1.1
docker push your-registry.com/video-translate:v1.1
```

### 2. 使用HTTPS

确保API调用使用HTTPS，并在生产环境中使用TLS证书。

### 3. 日志管理

配置日志驱动：

```yaml
services:
  video-translate:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## 更新

拉取最新代码并重新构建：

```bash
git pull
docker-compose build --no-cache
docker-compose up -d
```

## 技术支持

如有问题，请检查：
1. Docker版本是否符合要求
2. 环境变量是否正确配置
3. 网络连接是否正常
4. 存储空间是否充足
