import os
import re
import fitz  # PyMuPDF
from typing import List, Dict, Any
from app.models.schemas import Curriculum
from app.database.connection import db_manager
from app.config.settings import CURRICULUM_DATA_DIR
from app.utils.helpers import logger

class CurriculumParser:
    def __init__(self, output_dir: str = str(CURRICULUM_DATA_DIR)):
        self.output_dir = output_dir

    def create_sample_syllabus_pdf(self, filename: str = "sample_syllabus.pdf") -> str:
        """Create a sample syllabus PDF file using PyMuPDF if it doesn't exist."""
        filepath = os.path.join(self.output_dir, filename)
        if os.path.exists(filepath):
            return filepath
            
        logger.info(f"Creating sample syllabus PDF at: {filepath}")
        doc = fitz.open()
        
        # Course details
        syllabus_data = [
            {
                "subject": "CS 301: Advanced Data Engineering",
                "units": [
                    {
                        "unit": "Unit 1: Relational Data Processing",
                        "topics": "SQL databases, indexing, query optimization, PostgreSQL, normalization, transactions.",
                        "outcomes": "Write complex SQL queries and design normalized database schemas."
                    },
                    {
                        "unit": "Unit 2: Distributed Systems Foundations",
                        "topics": "Apache Hadoop, HDFS architecture, MapReduce programming paradigm, Linux shell, Git version control.",
                        "outcomes": "Deploy simple Hadoop mapreduce jobs and manage files on HDFS."
                    },
                    {
                        "unit": "Unit 3: Large-Scale Processing",
                        "topics": "Apache Spark, RDDs, DataFrames API, PySpark, cluster computing, memory management.",
                        "outcomes": "Implement PySpark scripts to analyze multi-gigabyte datasets."
                    }
                ]
            },
            {
                "subject": "CS 402: Intelligent Systems & AI",
                "units": [
                    {
                        "unit": "Unit 1: Machine Learning Foundations",
                        "topics": "Supervised learning, linear regression, logistic regression, decision trees, Python programming language.",
                        "outcomes": "Train and evaluate core ML models in Python using NumPy and Pandas."
                    },
                    {
                        "unit": "Unit 2: Deep Learning & NLP",
                        "topics": "Neural networks, backpropagation, convolutional networks, NLP core concepts, SpaCy, word embeddings.",
                        "outcomes": "Build NLP parsing models and feedforward networks."
                    }
                ]
            }
        ]
        
        # Draw on pages
        y_pos = 50
        page = doc.new_page()
        page.insert_text((50, y_pos), "UNIVERSITY OF TECHNOLOGY & SCIENCES", fontsize=16, color=(0.1, 0.3, 0.6))
        page.insert_text((50, y_pos + 20), "Department of Computer Science - B.Tech Curriculum", fontsize=12, color=(0.4, 0.4, 0.4))
        y_pos += 60
        
        for course in syllabus_data:
            if y_pos > 650:
                page = doc.new_page()
                y_pos = 50
                
            page.insert_text((50, y_pos), f"Course: {course['subject']}", fontsize=14, color=(0.2, 0.2, 0.2))
            y_pos += 25
            
            for u in course["units"]:
                if y_pos > 650:
                    page = doc.new_page()
                    y_pos = 50
                    
                page.insert_text((60, y_pos), u["unit"], fontsize=11, color=(0.1, 0.5, 0.1))
                y_pos += 15
                
                # Wrap text helper
                topics_wrapped = f"Topics: {u['topics']}"
                page.insert_text((70, y_pos), topics_wrapped, fontsize=10, color=(0.3, 0.3, 0.3))
                y_pos += 15
                
                outcomes_wrapped = f"Outcomes: {u['outcomes']}"
                page.insert_text((70, y_pos), outcomes_wrapped, fontsize=10, color=(0.3, 0.3, 0.3))
                y_pos += 25
                
            y_pos += 15
            
        doc.save(filepath)
        doc.close()
        logger.info(f"Sample syllabus PDF created at {filepath}")
        return filepath

    def parse_pdf(self, filepath: str, university: str = "UTS", course: str = "B.Tech CSE") -> List[Curriculum]:
        """Extract subjects, units, topics, and outcomes from a syllabus PDF using PyMuPDF."""
        logger.info(f"Parsing PDF curriculum: {filepath}")
        
        # Initialize default items
        items = []
        
        try:
            doc = fitz.open(filepath)
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            
            # Simple line-by-line regex parsing
            lines = full_text.split("\n")
            current_subject = "General Syllabus"
            current_unit = "General"
            
            # Simple state machine to parse subjects, units, topics, and outcomes
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                # Match Course / Subject header
                subject_match = re.match(r"(?:Course|Subject):\s*(.*)", line, re.IGNORECASE)
                if not subject_match and ("CS " in line or "CSE " in line or "Course:" in line):
                    # Guessing it's a subject line
                    if len(line) < 60:
                        current_subject = line
                        continue
                elif subject_match:
                    current_subject = subject_match.group(1).strip()
                    continue
                    
                # Match Unit
                unit_match = re.match(r"(Unit\s+\d+|Unit\s+[IVX]+|\bModule\s+\d+\b):?\s*(.*)", line, re.IGNORECASE)
                if unit_match:
                    current_unit = unit_match.group(0).strip()
                    continue
                
                # Match Topics / Outcomes
                if line.lower().startswith("topics:"):
                    topics = line[7:].strip()
                    
                    # Look ahead for outcomes on next line
                    outcomes = ""
                    if i + 1 < len(lines) and lines[i+1].strip().lower().startswith("outcomes:"):
                        outcomes = lines[i+1][9:].strip()
                        
                    items.append(Curriculum(
                        university=university,
                        course=course,
                        subject=current_subject,
                        unit=current_unit,
                        topic=topics,
                        learning_outcomes=outcomes
                    ))
            
            doc.close()
            
            # If nothing was parsed (e.g. different PDF format), perform fallback paragraph parsing
            if not items:
                logger.warning("Line-by-line parsing did not yield curriculum items. Using fallback paragraph scanner.")
                # Look for sentences containing key words
                paragraphs = full_text.split("\n\n")
                for para in paragraphs:
                    para = para.strip().replace("\n", " ")
                    if len(para) > 30 and ("topics" in para.lower() or "syllabus" in para.lower() or "unit" in para.lower()):
                        items.append(Curriculum(
                            university=university,
                            course=course,
                            subject=current_subject,
                            unit="Overview",
                            topic=para[:200],
                            learning_outcomes=para[200:400] if len(para) > 200 else ""
                        ))
                        
            return items
            
        except Exception as e:
            logger.error(f"Error parsing PDF syllabus {filepath}: {e}")
            return []

    def parse_and_store(self, filepath: str, university: str = "UTS", course: str = "B.Tech CSE") -> int:
        """Parse curriculum PDF and insert records into database."""
        items = self.parse_pdf(filepath, university, course)
        if items:
            count = db_manager.insert_curriculum_items(items)
            # Log university parsed
            from app.models.schemas import University
            db_manager.insert_university(University(name=university, location="India"))
            return count
        return 0
