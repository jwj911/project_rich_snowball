FROM python:3.11-slim

# 创建非 root 用户
RUN groupadd -r app && useradd -r -g app -m app

WORKDIR /app

# 安装系统依赖（编译某些 Python 包需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 修正权限
RUN chown -R app:app /app

# 切换到非 root 用户
USER app

# 暴露端口（与 main.py 默认值 8200 一致）
EXPOSE 8200

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8200/health || exit 1

# 开发/测试默认使用 uvicorn；生产环境建议使用 gunicorn + uvicorn.workers.UvicornWorker
# 示例：CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:8200"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8200"]
