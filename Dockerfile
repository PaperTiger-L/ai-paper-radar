# AI Paper Radar — 多阶段构建
# 阶段一：构建前端（React + TS + Tailwind）
FROM node:20-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 阶段二：后端运行（FastAPI + SQLite）
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_PATH=/app/data/paper_radar.db
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
# 把前端构建产物放进后端静态目录，由 FastAPI 统一服务
# 注意：必须用绝对路径。WORKDIR 是 /app，写相对路径 ./app/static/admin
# 实际落到 /app/app/static/admin（两层 app），容易误导排查，故显式写全。
COPY --from=frontend-build /build/frontend/dist /app/app/static/admin
VOLUME /app/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
