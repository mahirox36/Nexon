import os
from dotenv import load_dotenv

load_dotenv() 



DB_URL = os.environ.get("DATABASE_URL", "postgres://usernwame:password@localhost:5432/bot")
TORTOISE_ORM = {
    "connections": {
        "default": DB_URL
    },
    "apps": {
        "models": {
            "models": ["nexon.data.models", "aerich.models"],
            "default_connection": "default",
        }
    }
}