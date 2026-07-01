from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Agent GNS3"
    environment: str = "development"

    # Database (quan hệ) - mục 3.2.2: PostgreSQL cho dữ liệu quan hệ
    database_url: str = "postgresql+psycopg2://agent:agent@localhost:5432/agent_gns3"

    # InfluxDB cho time-series (metrics)
    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = "dev-token"
    influxdb_org: str = "agent-org"
    influxdb_bucket: str = "network_metrics"

    # GNS3 controller REST API
    gns3_url: str = "http://localhost:3080"
    gns3_user: str = "admin"
    gns3_password: str = "admin"
    gns3_project_id: str | None = None

    # LLM: Ollama (Qwen nội bộ) hoặc Claude API - mục 4, linh hoạt local/cloud
    llm_provider: str = "ollama"  # "ollama" | "anthropic"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Thông tin đăng nhập mặc định cho thiết bị lab (Netmiko) - mục 2.5
    device_ssh_username: str = "admin"
    device_ssh_password: str = "admin"
    device_ssh_secret: str = ""
    device_default_type: str = "cisco_ios"
    device_ssh_timeout: int = 10

    # Agent / Guardrails - mục 3.3.2
    agent_max_retries: int = 3
    agent_require_approval_for_high_risk: bool = True
    collector_interval_seconds: int = 10

    # Lớp An ninh: syslog UDP listener (mục 3.3.1, 3.3.4)
    syslog_udp_host: str = "0.0.0.0"
    syslog_udp_port: int = 5514
    # Thiết bị biên (ví dụ R1) dùng làm nơi thực thi block_ip khi phát hiện tấn công qua syslog.
    security_edge_device_id: str | None = None

    # Auth
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 8

    # Anomaly detection - mục 3.3.1
    anomaly_score_threshold: float = -0.1


@lru_cache
def get_settings() -> Settings:
    return Settings()
