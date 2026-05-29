FROM nginx:1.28.0

# nginx 镜像基于 Debian，安装 Python3 和 opencv 运行时依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        libgl1-mesa-glx \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 包（--break-system-packages 绕过 Debian PEP 668 限制）
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# 启动脚本
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /app
ENTRYPOINT ["/entrypoint.sh"]
