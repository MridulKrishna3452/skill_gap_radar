import abc
import random
from typing import List, Dict, Any
from datetime import datetime, timedelta
from app.models.schemas import Job
from app.utils.helpers import logger

class BaseScraper(abc.ABC):
    """Abstract Base Class for all job scrapers and loaders."""
    
    @abc.abstractmethod
    def scrape(self) -> List[Job]:
        """Scrape or load job posts and return list of Job schemas."""
        pass
    
    def generate_mock_jobs(self, count: int = 10, source: str = "MockSource") -> List[Job]:
        """Generate realistic job descriptions for fallback or offline runs."""
        logger.info(f"Generating {count} mock jobs for source: {source}")
        
        job_templates = [
            {
                "titles": ["Python Backend Engineer", "Junior Data Engineer", "Data Engineer - ETL Pipelines"],
                "categories": ["Software Engineering", "Data Engineering", "Data Engineering"],
                "experiences": ["1-3 years", "0-2 years", "2-5 years"],
                "skills": "Python, SQL, REST API, Docker, Git, Postgres, Airflow, Spark",
                "descriptions": [
                    "We are looking for a Python Backend Engineer to build robust REST APIs. You will work with Django, PostgreSQL, Docker, and write clean unit tests.",
                    "Join our team as a Junior Data Engineer. You will help construct ETL data pipelines using PySpark and Apache Airflow, and query SQL databases.",
                    "Looking for a Data Engineer to design, build, and optimize our data pipelines. Experience with Apache Spark, Airflow, SQL, and AWS GCP Snowflake is required."
                ]
            },
            {
                "titles": ["DevOps Engineer", "Cloud Engineer - AWS", "SRE / DevOps specialist"],
                "categories": ["DevOps", "Cloud Engineering", "DevOps"],
                "experiences": ["2-4 years", "1-3 years", "3-6 years"],
                "skills": "Docker, Kubernetes, AWS, Terraform, CI/CD, Linux, Git, Jenkins, Shell Scripting",
                "descriptions": [
                    "We need a DevOps Engineer to manage our Kubernetes clusters. You will implement CI/CD pipelines, configure Terraform on AWS, and write Linux scripts.",
                    "Looking for a Cloud Engineer to migrate applications to AWS. You will provision infrastructure with Terraform, Dockerize applications, and manage Linux VMs.",
                    "As an SRE/DevOps Engineer, you will maintain service uptime. Required: Kubernetes, CI/CD, Prometheus, Docker, Linux administration, and Shell scripting."
                ]
            },
            {
                "titles": ["AI Engineer - Generative AI", "Machine Learning Specialist", "NLP Engineer"],
                "categories": ["AI Engineering", "Machine Learning", "AI Engineering"],
                "experiences": ["2-5 years", "3-5 years", "1-3 years"],
                "skills": "Python, PyTorch, TensorFlow, LLMs, LangChain, NLP, Deep Learning, Machine Learning, Git",
                "descriptions": [
                    "Looking for an AI Engineer to build generative AI features. Experience with PyTorch, LLMs (GPT/Claude), LangChain, and vector databases is essential.",
                    "We are hiring a Machine Learning Specialist. You will train deep learning and ML models in TensorFlow and deploy them to GCP production environments.",
                    "Join us as an NLP Engineer. You will build NLP pipelines using SpaCy, fine-tune transformer models with PyTorch, and develop text classification models."
                ]
            },
            {
                "titles": ["Full Stack Developer (React/Node)", "Frontend Developer - React", "Web Developer - Angular/Node"],
                "categories": ["Software Engineering", "Software Engineering", "Software Engineering"],
                "experiences": ["2-4 years", "1-2 years", "2-5 years"],
                "skills": "React, Node.js, JavaScript, REST API, Git, MongoDB, Redis, CSS, Express",
                "descriptions": [
                    "Hiring a Full Stack Developer to build interactive UI in React and scalable servers in Node.js. Experience with MongoDB and Redis is a plus.",
                    "We are seeking a Frontend Developer proficient in React, CSS, JavaScript, and HTML. Experience building responsive dashboards and using Git is required.",
                    "Looking for a Web Developer to join our team. Essential skills include Angular, Node.js, REST APIs, Git, and SQL databases."
                ]
            }
        ]

        locations = ["Bengaluru", "Noida", "Mumbai", "Hyderabad", "Pune", "Remote"]
        companies = ["TechNexus Solutions", "Quantum Analytics", "CloudScale Systems", "DataFlow Corp", "NeuralDev Labs", "AlphaSoft Inc"]
        employment_types = ["Full-time", "Contract", "Internship"]
        salaries = ["6,000,000 - 1,200,000 INR", "400,000 - 700,000 INR", "1,500,000 - 2,200,000 INR", "Not Disclosed"]
        
        mock_jobs = []
        for i in range(count):
            template = random.choice(job_templates)
            idx = random.randint(0, len(template["titles"]) - 1)
            
            title = template["titles"][idx]
            category = template["categories"][idx]
            exp = template["experiences"][idx]
            desc = template["descriptions"][idx]
            skills_raw = template["skills"]
            
            # Random date within last 30 days
            days_ago = random.randint(0, 30)
            date_posted = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            
            job = Job(
                title=title,
                company=random.choice(companies),
                location=random.choice(locations),
                experience=exp,
                description=desc,
                skills_raw=skills_raw,
                source=source,
                date_posted=date_posted,
                url=f"https://www.example.com/{source.lower()}/job/{10000 + i}",
                salary=random.choice(salaries),
                employment_type=random.choice(employment_types),
                category=category
            )
            mock_jobs.append(job)
            
        return mock_jobs
