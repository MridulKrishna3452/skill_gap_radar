from typing import List, Dict, Any
from app.database.connection import db_manager
from app.analytics.gap_analysis import GapAnalysisEngine
from app.models.schemas import Recommendation
from app.utils.helpers import logger

class RecommendationEngine:
    def __init__(self):
        # Define standard skill requirements for core roles
        self.role_requirements = {
            "Data Engineer": ["Python", "SQL", "Spark", "PySpark", "Hadoop", "Airflow", "Databricks", "Snowflake", "Kafka"],
            "AI Engineer": ["Python", "PyTorch", "TensorFlow", "LLMs", "LangChain", "NLP", "Deep Learning", "Machine Learning", "Generative AI"],
            "DevOps Engineer": ["Docker", "Kubernetes", "Terraform", "CI/CD", "Linux", "Git", "AWS", "System Design"],
            "Cloud Engineer": ["AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "Linux", "System Design"],
            "Software Engineer": ["Python", "Java", "C++", "SQL", "Git", "React", "Node.js", "REST API", "System Design", "MongoDB", "Redis"]
        }

        # Detailed metadata for learning roadmaps per skill
        self.skill_learning_details = {
            "Python": {
                "difficulty": "Beginner", "time": "3 weeks",
                "roadmap": ["Syntax and Core Types", "Object-Oriented Programming", "File I/O and Decorators", "Testing and Debugging"]
            },
            "SQL": {
                "difficulty": "Beginner", "time": "2 weeks",
                "roadmap": ["Basic Queries (SELECT, WHERE)", "Joins and Aggregations", "Subqueries & Window Functions", "Index Optimization"]
            },
            "Docker": {
                "difficulty": "Intermediate", "time": "2 weeks",
                "roadmap": ["Containers vs VMs", "Writing Dockerfiles", "Volume and Network Mapping", "Multi-container with Compose"]
            },
            "Kubernetes": {
                "difficulty": "Advanced", "time": "4 weeks",
                "roadmap": ["K8s Architecture (Pods, Nodes)", "Deployments and Services", "ConfigMaps and Secrets", "Helm Charts & Ingress Controllers"]
            },
            "AWS": {
                "difficulty": "Intermediate", "time": "4 weeks",
                "roadmap": ["IAM Security and VPCs", "EC2 Compute and S3 Storage", "Serverless with Lambda & RDS", "CloudWatch Monitoring"]
            },
            "Azure": {
                "difficulty": "Intermediate", "time": "4 weeks",
                "roadmap": ["Azure Active Directory & VNets", "Virtual Machines & Blob Storage", "Azure Functions & SQL Database", "Resource Manager Templates"]
            },
            "GCP": {
                "difficulty": "Intermediate", "time": "4 weeks",
                "roadmap": ["IAM & VPC Networks", "Compute Engine & Cloud Storage", "BigQuery Analytics & Cloud Functions", "Google Kubernetes Engine"]
            },
            "Spark": {
                "difficulty": "Advanced", "time": "3 weeks",
                "roadmap": ["Spark Architecture (Driver/Executors)", "Resilient Distributed Datasets (RDD)", "DataFrames & Spark SQL", "Optimizing Shuffles & Partitions"]
            },
            "PySpark": {
                "difficulty": "Intermediate", "time": "2 weeks",
                "roadmap": ["PySpark Shell and Setup", "Data Ingestion & Cleaning", "SQL Queries in PySpark", "Spark MLlib overview"]
            },
            "Hadoop": {
                "difficulty": "Intermediate", "time": "2 weeks",
                "roadmap": ["HDFS Architecture & Commands", "MapReduce Java/Python scripts", "YARN Resource Management", "Hive & Pig Query integrations"]
            },
            "Airflow": {
                "difficulty": "Intermediate", "time": "2 weeks",
                "roadmap": ["DAG structure and operators", "Scheduling & Triggering DAGs", "Variables and Connections", "Airflow Tasks & Executors"]
            },
            "Terraform": {
                "difficulty": "Intermediate", "time": "3 weeks",
                "roadmap": ["Infrastructure as Code concepts", "Providers and Resources", "State Management & Locking", "Modules and Workspaces"]
            },
            "Linux": {
                "difficulty": "Beginner", "time": "2 weeks",
                "roadmap": ["Terminal commands & File system", "User Permissions & SSH keys", "Bash shell scripting", "Process management & Cron jobs"]
            },
            "Git": {
                "difficulty": "Beginner", "time": "1 week",
                "roadmap": ["Git Init, Add, Commit", "Branching and Merging", "Resolving Conflicts", "GitHub Pull Requests & workflows"]
            },
            "REST API": {
                "difficulty": "Intermediate", "time": "2 weeks",
                "roadmap": ["HTTP Methods (GET, POST)", "JSON payloads & status codes", "API Routing & Middleware", "Authentication (JWT / API Keys)"]
            },
            "LangChain": {
                "difficulty": "Intermediate", "time": "2 weeks",
                "roadmap": ["Prompts, Models, Output Parsers", "Chains and Expression Language", "Retrieval Augmented Generation (RAG)", "Building Agents and Memory"]
            },
            "LLMs": {
                "difficulty": "Advanced", "time": "3 weeks",
                "roadmap": ["Transformer Architectures", "Tokenization & Context Windows", "Prompt Engineering techniques", "Parameter-Efficient Fine-Tuning"]
            },
            "TensorFlow": {
                "difficulty": "Advanced", "time": "4 weeks",
                "roadmap": ["Tensors and Operations", "Keras Sequential API", "Custom Layers and Training Loops", "TensorBoard Visualization"]
            },
            "PyTorch": {
                "difficulty": "Advanced", "time": "4 weeks",
                "roadmap": ["Tensors and autograd", "nn.Module architecture", "DataLoaders & Custom Datasets", "Distributed model training"]
            },
            "React": {
                "difficulty": "Intermediate", "time": "3 weeks",
                "roadmap": ["JSX and Components", "State and Props (useState, useEffect)", "Context API and Redux", "React Router & Form Handling"]
            },
            "Angular": {
                "difficulty": "Advanced", "time": "4 weeks",
                "roadmap": ["TypeScript & Components", "Directives and Pipes", "Services & Dependency Injection", "RxJS Observables & Routing"]
            },
            "Node.js": {
                "difficulty": "Intermediate", "time": "3 weeks",
                "roadmap": ["Node.js Event Loop", "Express framework routing", "Asynchronous coding (Promises, async/await)", "NPM package management"]
            },
            "MongoDB": {
                "difficulty": "Intermediate", "time": "2 weeks",
                "roadmap": ["NoSQL Document schemas", "CRUD queries & Aggregations", "Indexing & Sharding", "Mongoose ORM integration"]
            },
            "Redis": {
                "difficulty": "Intermediate", "time": "1 week",
                "roadmap": ["Caching strategies", "Redis Data Structures", "Pub/Sub Messaging", "Redis Persistence & Clustering"]
            },
            "Kafka": {
                "difficulty": "Advanced", "time": "3 weeks",
                "roadmap": ["Event streaming concepts", "Producers, Consumers, Brokers", "Kafka Topics & Partitions", "Kafka Streams & Connect"]
            },
            "Snowflake": {
                "difficulty": "Intermediate", "time": "2 weeks",
                "roadmap": ["Snowflake Architecture", "Virtual Warehouses scaling", "Data Sharing & Snowpipe", "Time Travel and Cloning"]
            },
            "Databricks": {
                "difficulty": "Intermediate", "time": "2 weeks",
                "roadmap": ["Databricks Notebooks & Workspace", "Delta Lake Lakehouse tables", "PySpark optimization", "Databricks Jobs workflows"]
            },
            "System Design": {
                "difficulty": "Advanced", "time": "4 weeks",
                "roadmap": ["Scalability & High Availability", "Load Balancing & Reverse Proxies", "Database Sharding & Replication", "Microservices Architecture"]
            },
            "CI/CD": {
                "difficulty": "Intermediate", "time": "2 weeks",
                "roadmap": ["CI/CD Principles", "GitHub Actions workflows", "Build runners and artifacts", "Automated deployment triggers"]
            },
            "DevOps": {
                "difficulty": "Advanced", "time": "4 weeks",
                "roadmap": ["Infrastructure automation", "Monitoring and Alerting", "Container orchestration", "Security auditing & compliance"]
            },
            "Machine Learning": {
                "difficulty": "Intermediate", "time": "4 weeks",
                "roadmap": ["Feature Engineering & Scaling", "Scikit-Learn models", "Cross-validation & Hyperparameters", "Metrics: Precision, Recall, ROC"]
            },
            "Deep Learning": {
                "difficulty": "Advanced", "time": "4 weeks",
                "roadmap": ["Feedforward Networks", "CNNs for Computer Vision", "RNNs & LSTMs for sequences", "Generative Adversarial Networks"]
            },
            "NLP": {
                "difficulty": "Intermediate", "time": "3 weeks",
                "roadmap": ["Tokenization & Lemmatization", "Named Entity Recognition (NER)", "TF-IDF and Vector models", "HuggingFace Transformers"]
            },
            "Generative AI": {
                "difficulty": "Advanced", "time": "4 weeks",
                "roadmap": ["RAG Architecture", "Vector Databases (Chroma/Pinecone)", "Semantic search & chunking", "AI Agent frameworks"]
            }
        }

    def generate_recommendations_for_role(self, role: str) -> List[Recommendation]:
        """Compute missing skills dynamically and build recommendations for a selected career goal."""
        if role not in self.role_requirements:
            logger.warning(f"Role '{role}' is not supported for recommendations.")
            return []
            
        required_skills = self.role_requirements[role]
        
        # Get taught skills
        taught_skills = GapAnalysisEngine.extract_skills_from_curriculum()
        taught_skills_set = set(t.lower() for t in taught_skills)
        
        # Get demand metrics from database
        df_skills = db_manager.get_skills_df()
        skill_demands = {}
        if not df_skills.empty:
            skill_demands = dict(zip(df_skills["name"], df_skills["frequency"]))
            
        recommendations = []
        for r_skill in required_skills:
            # Check if skill is taught
            is_taught = r_skill.lower() in taught_skills_set
            
            # If not taught, generate recommendation
            if not is_taught:
                # Priority: base on industry demand
                demand_freq = skill_demands.get(r_skill, 0)
                # Assign priority based on popularity
                if demand_freq > 15:
                    priority = "High"
                elif demand_freq > 5:
                    priority = "Medium"
                else:
                    priority = "Low"
                    
                # Fetch learning details
                details = self.skill_learning_details.get(r_skill, {
                    "difficulty": "Intermediate",
                    "time": "3 weeks",
                    "roadmap": ["Fundamentals", "Intermediate Application", "Advanced Projects", "Build portfolio work"]
                })
                
                rec = Recommendation(
                    career_goal=role,
                    missing_skill=r_skill,
                    priority=priority,
                    difficulty=details["difficulty"],
                    estimated_learning_time=details["time"],
                    learning_roadmap=details["roadmap"]
                )
                recommendations.append(rec)
                
        # If there are no missing skills (curriculum covers everything), suggest enrichment topics
        if not recommendations:
            logger.info(f"All skills for {role} are covered by the curriculum. Suggesting advanced concepts.")
            
        return recommendations

    def seed_recommendations_db(self):
        """Populate database recommendations table for all standard roles."""
        all_recs = []
        for role in self.role_requirements.keys():
            recs = self.generate_recommendations_for_role(role)
            all_recs.extend(recs)
            
        if all_recs:
            db_manager.insert_recommendations(all_recs)
            logger.info(f"Seeded {len(all_recs)} recommendations into database.")
            
# Global singleton instance
rec_engine = RecommendationEngine()
