import os
import pandas as pd
from typing import List
from app.models.schemas import Job
from app.scraper.base import BaseScraper
from app.config.settings import RAW_DATA_DIR
from app.utils.helpers import logger

class CSVJobLoader(BaseScraper):
    def __init__(self, filepath: str = str(RAW_DATA_DIR / "sample_jobs.csv")):
        self.filepath = filepath
        self._ensure_sample_file()

    def _ensure_sample_file(self):
        """Create a default sample CSV file if it does not exist."""
        if not os.path.exists(self.filepath):
            logger.info(f"CSV file not found at {self.filepath}. Creating mock dataset.")
            # Generate mock data using base class generator
            mock_jobs = self.generate_mock_jobs(count=12, source="CSVLoader")
            job_dicts = [j.model_dump() for j in mock_jobs]
            df = pd.DataFrame(job_dicts)
            df.to_csv(self.filepath, index=False)
            logger.info(f"Mock CSV dataset written to: {self.filepath}")

    def scrape(self) -> List[Job]:
        logger.info(f"Loading jobs from CSV: {self.filepath}")
        jobs = []
        try:
            df = pd.read_csv(self.filepath)
            # Ensure columns are filled
            df = df.fillna("")
            
            for _, row in df.iterrows():
                try:
                    job = Job(
                        title=str(row.get("title", "Unknown Title")),
                        company=str(row.get("company", "Unknown Company")),
                        location=str(row.get("location", "Remote")),
                        experience=str(row.get("experience", "Not specified")),
                        description=str(row.get("description", "")),
                        skills_raw=str(row.get("skills_raw", "")),
                        source=str(row.get("source", "CSVLoader")),
                        date_posted=str(row.get("date_posted", "2026-06-25")),
                        url=str(row.get("url", "https://example.com")),
                        salary=str(row.get("salary", "Not Disclosed")),
                        employment_type=str(row.get("employment_type", "Full-time")),
                        category=str(row.get("category", "Software Engineering"))
                    )
                    jobs.append(job)
                except Exception as ex:
                    logger.warning(f"Error parsing row from CSV: {ex}")
            return jobs
        except Exception as e:
            logger.error(f"Failed to read CSV at {self.filepath}: {e}")
            return []
