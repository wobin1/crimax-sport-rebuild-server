from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    allowed_origins: str = "http://localhost:3000"

    # Apply pending SQL migrations on startup. Turn off where a deploy step
    # runs scripts/migrate.py before new instances boot.
    auto_migrate: bool = True
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    # Public frontend origin used in invite / reset links
    frontend_url: str = "http://localhost:3000"

    # Zoho Mail REST API (OAuth2 self-client / refresh token)
    emails_enabled: bool = False
    email_from_name: str = "Crimax Sports"
    zoho_client_id: str | None = None
    zoho_client_secret: str | None = None
    zoho_refresh_token: str | None = None
    # The Zoho mailbox that mail is sent from (e.g. no-reply@yourdomain.com)
    zoho_from_address: str | None = None
    # Optional: skip the accounts lookup by pinning the sending accountId
    zoho_account_id: str | None = None
    # Data-center specific hosts (.com, .eu, .in, .com.au, .jp)
    zoho_accounts_url: str = "https://accounts.zoho.com"
    zoho_mail_api_url: str = "https://mail.zoho.com"

    invite_expire_hours: int = 72
    password_reset_ttl_minutes: int = 30

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def mail_configured(self) -> bool:
        return bool(
            self.zoho_client_id
            and self.zoho_client_secret
            and self.zoho_refresh_token
            and self.zoho_from_address
        )

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
