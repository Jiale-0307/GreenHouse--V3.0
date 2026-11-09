FROM python:3.13-slim
# 仅影响构建时的软件包下载；国内服务器可传入受信任的 PyPI 镜像，锁定版本保持不变。
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Shanghai
WORKDIR /app
COPY backend/requirements.lock ./requirements.lock
RUN pip install --index-url "$PIP_INDEX_URL" --no-cache-dir -r requirements.lock && mkdir -p /app/contracts && useradd --uid 10001 --create-home appuser
COPY --chown=appuser:appuser backend/app ./app
COPY --chown=appuser:appuser docs/api/openapi.yaml ./contracts/frontend-openapi.json
USER appuser
EXPOSE 8080
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log"]
