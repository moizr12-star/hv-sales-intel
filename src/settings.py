from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_maps_api_key: str = ""
    supabase_url: str = ""
    supabase_key: str = ""                    # anon key (legacy name preserved)
    supabase_service_role_key: str = ""       # admin client for auth verification
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Bootstrap admin (seeded on startup if profiles has zero admins)
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    # Microsoft Graph (email outreach)
    ms_tenant_id: str = ""
    ms_client_id: str = ""
    ms_client_secret: str = ""
    ms_refresh_token: str = ""
    ms_sender_email: str = ""
    email_reply_lookback_days: int = 30

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
