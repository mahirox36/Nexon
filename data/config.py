import os

DB_URL = os.environ.get("DATABASE_URL", "postgres://usernwame:password@localhost:5432/bot")
TORTOISE_ORM = {
    "connections": {
        "default": DB_URL
    },
    "apps": {
        "models": {
            "models": ["nexon.data.models", "aerich.models"],  # Make sure the path is correct here
            "default_connection": "default",
        }
    }
}