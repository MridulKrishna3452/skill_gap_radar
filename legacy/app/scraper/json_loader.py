import os
import json
from typing import List
from app.models.schemas import Job
from app.scraper.base import BaseScraper
from app.config.settings import RAW_DATA_DIR
from app.utils.helpers import logger

class JSONJobLoader(BaseScraper):
    def __init__(self, filepath: str = str(RAW_DATA_DIR / "sample_jobs.json")):
        self.filepath = filepath
        self._ensure_sample_file()

    def _ensure_sample_file(self):
        """Create a default sample JSON file if it does not exist."""
        if not os.path.exists(self.filepath):
            logger.info(f"JSON file not found at {self.filepath}. Creating mock dataset.")
            # Generate mock data using base class generator
            mock_jobs = self.generate_mock_jobs(count=8, source="JSONLoader")
            job_dicts = [j.model_dump() for j in mock_jobs]
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(job_dicts, f, indent=4)
            logger.info(f"Mock JSON dataset written to: {self.filepath}")

    def scrape(self) -> List[Job]:
        logger.info(f"Loading jobs from JSON: {self.filepath}")
        jobs = []
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for item in data:
                try:
                    job = Job(
                        title=item.get("title", "Unknown Title"),
                        company=item.get("company", "Unknown Company"),
                        location=item.get("location", "Remote"),
                        experience=item.get("experience", "Not specified"),
                        description=item.get("description", ""),
                        skills_raw=item.get("skills_raw", ""),
                        source=item.get("source", "JSONLoader"),
                        date_posted=item.get("date_posted", "2026-06-25"),
                        url=item.get("url", "https://example.com"),
                        salary=item.get("salary", "Not Disclosed"),
                        employment_type=item.get("employment_type", "Full-time"),
                        category=item.get("category", "Software Engineering")
                    )
                    jobs.append(job)
                except Exception as ex:
                    logger.warning(f"Error parsing item from JSON: {ex}")
            return jobs
        except Exception as e:
            logger.error(f"Failed to read JSON at {self.filepath}: {e}")
            return []
