# 使用 Python 3.12 作为基础镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 复制项目文件到容器中
COPY . /app

# 安装 uv
RUN pip install uv

# 使用 uv 从 pyproject.toml 安装依赖
RUN uv pip install .

# 运行 app.py
CMD ["python", "mexc.py"]