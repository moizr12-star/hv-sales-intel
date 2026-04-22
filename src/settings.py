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

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
