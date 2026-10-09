"""应用配置：从环境变量 / .env 文件读取（pydantic-settings 管理）。

环境变量：
    DATABASE_PATH   SQLite 文件路径（默认 ./data/paper_radar.db）
    ADMIN_USERNAME  初始管理员账号（默认 admin@paper-radar.local）
    ADMIN_PASSWORD  初始管理员密码（默认 admin12345，低于 8 位启动时报错）
    JWT_SECRET      JWT 签名密钥（缺省则首次启动随机生成并存入 Setting 表；
                    设置后优先于 Setting 表的值，且会使旧 token 失效）
    TIMEZONE        应用时区（默认 Asia/Shanghai）
    DOCS_ENABLED    是否暴露 /docs、/redoc 与 /openapi.json（默认 false，生产环境建议关闭）
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    database_path: str = "./data/paper_radar.db"
    admin_username: str = "admin@paper-radar.local"
    admin_password: str = "admin12345"
    jwt_secret: str | None = None
    timezone: str = "Asia/Shanghai"
    docs_enabled: bool = False  # 设为 true 则暴露 /docs、/redoc 与 /openapi.json

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = AppSettings()
