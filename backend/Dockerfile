
# 基础镜像（轻量版Python）
FROM python:3.11-slim

# 工作目录
WORKDIR /app

# 安装系统依赖（opencv-python、pytesseract、pdf2image 等需要）
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    tesseract-ocr \
    poppler-utils \
    libreoffice-calc \
    libreoffice-writer \
    libreoffice-impress \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖清单
COPY config/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 预下载 EasyOCR 模型文件（在构建时下载，避免运行时缺失）
# 注意：EasyOCR 模型会下载到 ~/.EasyOCR/model/ 目录
RUN python -c "import easyocr; reader = easyocr.Reader(['en'], gpu=False, verbose=True, download_enabled=True); print('EasyOCR models downloaded successfully')" || echo "EasyOCR model download completed or skipped"

# 复制代码
COPY . .

# 暴露端口（Cloud Run 使用 PORT 环境变量，默认 8080）
EXPOSE 8080

# 设置 Python 路径，确保能导入项目模块
ENV PYTHONPATH=/app

# 确保启动脚本有执行权限（已通过 COPY . . 复制）
RUN chmod +x /app/start_server.sh

# 启动命令：明确使用 sh 执行脚本，避免 exec format error
CMD ["/bin/sh", "/app/start_server.sh"]