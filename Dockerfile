# 使用 Python 3.12 作为基础镜像
FROM uv:python3.12-alpine

# 设置工作目录
WORKDIR /app

# 复制项目文件到容器中
COPY . /app

# 安装 uv
RUN uv sync --frozen

# 运行 app.py
CMD ["uv", "run", "mexc.py"]