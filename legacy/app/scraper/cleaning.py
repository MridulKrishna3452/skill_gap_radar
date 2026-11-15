import re
from app.models.schemas import Job
from app.utils.helpers import clean_html

def normalize_company(name: str) -> str:
    """Standardize company name by stripping common corporate endings."""
    if not name:
        return "Unknown Company"
    name = re.sub(r'\b(private\s+limited|pvt\s+ltd|pvt\.?\s*ltd\.?|limited|ltd|inc|corp|llc|incorporation|corporation)\b\.?', '', name, flags=re.IGNORECASE)
    # Remove multiple spaces and strip
    name = re.sub(r'\s+', ' ', name).strip()
    # Titlecase
    return name.title() if name else "Unknown Company"

def normalize_location(loc: str) -> str:
    """Map common variation of locations to standardized forms."""
    if not loc:
        return "Remote"
    loc_lower = loc.lower().strip()
    
    if "bangalore" in loc_lower or "bengaluru" in loc_lower:
        return "Bengaluru"
    elif "noida" in loc_lower:
        return "Noida"
    elif "delhi" in loc_lower or "ncr" in loc_lower:
        return "Delhi NCR"
    elif "mumbai" in loc_lower:
        return "Mumbai"
    elif "hyderabad" in loc_lower:
        return "Hyderabad"
    elif "pune" in loc_lower:
        return "Pune"
    elif "remote" in loc_lower or "work from home" in loc_lower or "wfh" in loc_lower:
        return "Remote"
    
    return loc.title()

def standardize_skills_string(skills_raw: str) -> str:
    """Format raw skill lists into uniform comma-separated terms."""
    if not skills_raw:
        return ""
    # Map synonyms/variations to standard terms
    mappings = {
        r'\bpython\s*3?\b': "Python",
        r'\breact\s*(js|\.js)?\b': "React",
        r'\bnode\s*(js|\.js)?\b': "Node.js",
        r'\bangular\s*(js|\.js)?\b': "Angular",
        r'\bk8s\b': "Kubernetes",
        r'\baws\b': "AWS",
        r'\bgcp\b': "GCP",
        r'\bllms\b': "LLMs",
        r'\bmachine learning\b': "Machine Learning",
        r'\bdeep learning\b': "Deep Learning",
        r'\bnlp\b': "NLP",
        r'\bgenerative\s*ai\b': "Generative AI",
        r'\bci[\s\/]*cd\b': "CI/CD",
        r'\bdevops\b': "DevOps"
    }
    
    # Split skills by comma, slash, or semicolon
    raw_list = re.split(r'[,;/]', skills_raw)
    standard_list = []
    
    for item in raw_list:
        cleaned_item = item.strip().lower()
        if not cleaned_item:
            continue
            
        matched = False
        for pattern, replacement in mappings.items():
            if re.search(pattern, cleaned_item, re.IGNORECASE):
                standard_list.append(replacement)
                matched = True
                break
        
        if not matched:
            standard_list.append(item.strip().title())
            
    # Deduplicate and rejoin
    seen = set()
    deduped = [x for x in standard_list if not (x.lower() in seen or seen.add(x.lower()))]
    return ", ".join(deduped)

def clean_job(job: Job) -> Job:
    """Perform structural cleaning and normalization on a Job object."""
    # Clean description HTML tags
    cleaned_description = clean_html(job.description)
    
    # Normalize company, location, skills
    normalized_company = normalize_company(job.company)
    normalized_loc = normalize_location(job.location)
    cleaned_skills_raw = standardize_skills_string(job.skills_raw)
    
    # Standardize salary
    salary = job.salary or "Not Disclosed"
    if not salary.strip() or salary.lower() in ["none", "null", "nan", ""]:
        salary = "Not Disclosed"
        
    return Job(
        title=job.title.strip().title(),
        company=normalized_company,
        location=normalized_loc,
        experience=job.experience.strip() if job.experience else "Not specified",
        description=cleaned_description,
        skills_raw=cleaned_skills_raw,
        source=job.source,
        date_posted=job.date_posted,
        url=job.url.strip(),
        salary=salary,
        employment_type=job.employment_type.strip() if job.employment_type else "Full-time",
        category=job.category
    )
