import os
import re
import spacy
from spacy.matcher import PhraseMatcher
from typing import List, Dict, Any, Tuple
from app.config.settings import settings
from app.models.schemas import Skill, Job
from app.utils.helpers import logger

class NLPPipeline:
    def __init__(self):
        self.nlp = self._load_spacy_model()
        self.matcher = PhraseMatcher(self.nlp.vocab, attr="LOWER")
        self._initialize_matcher()

    def _load_spacy_model(self) -> spacy.language.Language:
        """Load SpaCy model, downloading it if not present."""
        model_name = settings.SPACY_MODEL
        try:
            logger.info(f"Loading SpaCy model: {model_name}")
            return spacy.load(model_name)
        except OSError:
            logger.warning(f"SpaCy model '{model_name}' not found. Downloading it...")
            try:
                spacy.cli.download(model_name)
                return spacy.load(model_name)
            except Exception as e:
                logger.error(f"Failed to download SpaCy model: {e}. Falling back to blank English model.")
                return spacy.blank("en")

    def _initialize_matcher(self):
        """Build phrase patterns for target technologies from settings."""
        # Custom mapping for matching variations
        self.skill_variations = {
            "Python": ["python", "python3", "python 3", "py"],
            "Java": ["java", "java SE", "jdk"],
            "C++": ["c++", "cpp", "c plus plus"],
            "SQL": ["sql", "mysql", "postgresql", "postgres", "sqlite", "oracle", "t-sql", "plsql"],
            "Docker": ["docker", "dockerfile", "docker-compose"],
            "Kubernetes": ["kubernetes", "k8s", "k3s", "helm"],
            "AWS": ["aws", "amazon web services", "s3", "ec2", "rds", "lambda"],
            "Azure": ["azure", "microsoft azure", "aks"],
            "GCP": ["gcp", "google cloud", "google cloud platform", "bigquery"],
            "Spark": ["spark", "apache spark", "sparksql"],
            "PySpark": ["pyspark"],
            "Hadoop": ["hadoop", "mapreduce", "hdfs"],
            "Airflow": ["airflow", "apache airflow"],
            "Terraform": ["terraform"],
            "Linux": ["linux", "ubuntu", "debian", "redhat", "centos", "bash", "shell scripting"],
            "Git": ["git", "github", "gitlab", "bitbucket"],
            "REST API": ["rest api", "restful api", "rest apis", "restful apis", "fastapi", "flask", "django rest framework"],
            "LangChain": ["langchain"],
            "LLMs": ["llm", "llms", "large language models", "gpt", "claude", "llama"],
            "TensorFlow": ["tensorflow", "tf"],
            "PyTorch": ["pytorch", "torch"],
            "React": ["react", "reactjs", "react.js"],
            "Angular": ["angular", "angularjs", "angular.js"],
            "Node.js": ["node.js", "nodejs", "node js"],
            "MongoDB": ["mongodb", "mongo"],
            "Redis": ["redis"],
            "Kafka": ["kafka", "apache kafka"],
            "Snowflake": ["snowflake"],
            "Databricks": ["databricks"],
            "System Design": ["system design", "distributed systems", "microservices", "software architecture"],
            "CI/CD": ["ci/cd", "continuous integration", "continuous deployment", "github actions", "jenkins"],
            "DevOps": ["devops", "site reliability engineering", "sre", "infrastructure as code"],
            "Machine Learning": ["machine learning", "ml", "scikit-learn", "xgboost"],
            "Deep Learning": ["deep learning", "dl", "neural networks", "keras"],
            "NLP": ["nlp", "natural language processing", "spacy", "nltk", "transformers", "huggingface"],
            "Generative AI": ["generative ai", "genai", "gen-ai", "rag", "vector databases", "chromadb", "pinecone"]
        }

        # Add target skills and variations to matcher
        for skill_name, phrases in self.skill_variations.items():
            patterns = [self.nlp.make_doc(text) for text in phrases]
            self.matcher.add(skill_name, patterns)

    def extract_skills(self, text: str) -> List[Tuple[str, float]]:
        """
        Analyze text using SpaCy and Matcher, returning list of (Skill, Confidence) tuples.
        Confidence is based on phrase match quality.
        """
        if not text:
            return []
            
        doc = self.nlp(text)
        matches = self.matcher(doc)
        
        extracted = {}
        for match_id, start, end in matches:
            skill_name = self.nlp.vocab.strings[match_id]
            # Match span
            span = doc[start:end]
            
            # Basic confidence scoring logic:
            # Full exact matches get 0.9. Variations get 0.85.
            confidence = 0.90 if span.text.lower() == skill_name.lower() else 0.85
            
            if skill_name in extracted:
                # Update confidence (take the max)
                extracted[skill_name] = max(extracted[skill_name], confidence)
            else:
                extracted[skill_name] = confidence
                
        return [(name, conf) for name, conf in extracted.items()]

    def process_job(self, job: Job) -> List[Skill]:
        """Process a job posting, return extracted Skills with source and frequency."""
        # 1. Parse raw skills field (highest confidence)
        raw_skills = [s.strip() for s in job.skills_raw.split(",") if s.strip()]
        
        extracted_skills = {}
        
        # Check raw skills matches against target list
        for r_skill in raw_skills:
            for skill_name, variations in self.skill_variations.items():
                if r_skill.lower() in [v.lower() for v in variations]:
                    extracted_skills[skill_name] = Skill(
                        name=skill_name,
                        frequency=1,
                        confidence=1.0,  # Explicitly listed skills get maximum confidence
                        source=job.source
                    )
                    
        # 2. Extract from Title (high confidence)
        title_skills = self.extract_skills(job.title)
        for skill_name, conf in title_skills:
            if skill_name in extracted_skills:
                # Upgrade confidence to 1.0 since it was in title
                extracted_skills[skill_name].confidence = 1.0
            else:
                extracted_skills[skill_name] = Skill(
                    name=skill_name,
                    frequency=1,
                    confidence=0.95,
                    source=job.source
                )
                
        # 3. Extract from Description (standard confidence)
        desc_skills = self.extract_skills(job.description)
        for skill_name, conf in desc_skills:
            if skill_name not in extracted_skills:
                extracted_skills[skill_name] = Skill(
                    name=skill_name,
                    frequency=1,
                    confidence=conf,
                    source=job.source
                )
                
        return list(extracted_skills.values())

# Global singleton pipeline instance
nlp_pipeline = NLPPipeline()
