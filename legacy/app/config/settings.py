import os
from pathlib import Path
from pydantic_settings import BaseSettings

# Define base paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "app" / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
CURRICULUM_DATA_DIR = DATA_DIR / "curriculum"
EXPORTS_DIR = DATA_DIR / "exports"

# Create directories if they don't exist
for directory in [DATA_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR, CURRICULUM_DATA_DIR, EXPORTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "Skill Gap Radar AI"
    ENV: str = "development"
    
    # Server configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DASH_PORT: int = 8050
    
    # Database Settings
    DB_PATH: str = str(DATA_DIR / "skill_gap_radar.db")
    
    # NLP Settings
    SPACY_MODEL: str = "en_core_web_sm"
    
    # Predefined skill set to extract & track
    TARGET_SKILLS: list[str] = [
        "Python", "Java", "C++", "SQL", "Docker", "Kubernetes", "AWS", "Azure", "GCP", 
        "Spark", "PySpark", "Hadoop", "Airflow", "Terraform", "Linux", "Git", "REST API", 
        "LangChain", "LLMs", "TensorFlow", "PyTorch", "React", "Angular", "Node.js", 
        "MongoDB", "Redis", "Kafka", "Snowflake", "Databricks", "System Design", "CI/CD", 
        "DevOps", "Machine Learning", "Deep Learning", "NLP", "Generative AI"
    ]
    
    # Log Settings
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = str(BASE_DIR / "app.log")

    class Config:
        env_prefix = "RADAR_"
        case_sensitive = True

settings = Settings()
