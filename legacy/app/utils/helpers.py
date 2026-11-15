import logging
import re
import sys
from bs4 import BeautifulSoup
from app.config.settings import settings

def setup_logging():
    """Configure logging for the application using settings."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(settings.LOG_FILE, encoding="utf-8")
        ]
    )
    
    # Suppress verbose loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    
    logger = logging.getLogger("SkillGapRadar")
    logger.info("Logging initialized.")
    return logger

logger = setup_logging()

def clean_html(text: str) -> str:
    """Remove HTML tags and clean whitespaces from a string."""
    if not text:
        return ""
    # Strip HTML tags
    soup = BeautifulSoup(text, "html.parser")
    cleaned = soup.get_text(separator=" ")
    # Remove multiple whitespaces and trim
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def normalize_text(text: str) -> str:
    """Convert text to lowercase and strip special characters except some symbols."""
    if not text:
        return ""
    text = text.lower().strip()
    # Replace common separators with spaces
    text = re.sub(r'[\/\-\,]', ' ', text)
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    return text
