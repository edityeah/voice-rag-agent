"""Load .env before any submodule reads environment variables."""
from dotenv import load_dotenv

load_dotenv()
