import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any
from app.database.connection import db_manager
from app.models.schemas import Trend
from app.utils.helpers import logger

class TrendAnalysisEngine:
    @staticmethod
    def calculate_and_save_trends():
        """Analyze jobs dataset by dates, count weekly/monthly skill demand, and compute growth rates."""
        logger.info("Recalculating skill trends from jobs dataset...")
        df_jobs = db_manager.get_jobs_df()
        if df_jobs.empty:
            logger.warning("No jobs in database to compute trends.")
            return

        # Explode skills list for each job
        records = []
        for _, row in df_jobs.iterrows():
            date_str = row["date_posted"]
            try:
                # Standardize date format to YYYY-MM
                dt = pd.to_datetime(date_str)
                month_period = dt.strftime("%Y-%m")
            except Exception:
                month_period = datetime.now().strftime("%Y-%m")
                
            skills_str = row["extracted_skills"]
            if not skills_str:
                continue
                
            try:
                skills_list = json.loads(skills_str)
            except Exception:
                skills_list = []
                
            for skill in skills_list:
                records.append({
                    "skill": skill,
                    "period": month_period
                })
                
        if not records:
            logger.info("No extracted skills found in jobs table to calculate trends.")
            return
            
        df = pd.DataFrame(records)
        # Group by skill and period (month)
        df_grouped = df.groupby(["skill", "period"]).size().reset_index(name="frequency")
        
        # Sort by skill and period to compute growth rate
        df_grouped = df_grouped.sort_values(by=["skill", "period"])
        
        trends_to_save = []
        # Calculate growth rate month-over-month
        for skill_name, group in df_grouped.groupby("skill"):
            group = group.reset_index(drop=True)
            for i in range(len(group)):
                current_freq = group.loc[i, "frequency"]
                period = group.loc[i, "period"]
                
                # Growth rate: (Current - Previous) / Previous
                if i > 0:
                    prev_freq = group.loc[i-1, "frequency"]
                    growth_rate = ((current_freq - prev_freq) / prev_freq) if prev_freq > 0 else 0.0
                else:
                    growth_rate = 0.0
                    
                trends_to_save.append(Trend(
                    skill_name=str(skill_name),
                    period=str(period),
                    frequency=int(current_freq),
                    growth_rate=float(growth_rate)
                ))
                
        db_manager.insert_trends(trends_to_save)
        logger.info(f"Calculated and saved {len(trends_to_save)} trend data points.")

    def get_trends_summary(self) -> Dict[str, Any]:
        """Query trends table and return top growing, declining, and emerging skills."""
        df_trends = db_manager.get_trends_df()
        if df_trends.empty:
            # Generate mock trends data for representation
            self.calculate_and_save_trends()
            df_trends = db_manager.get_trends_df()
            
        if df_trends.empty:
            return {"growing": [], "declining": [], "emerging": []}
            
        # Get most recent period
        periods = sorted(df_trends["period"].unique())
        if len(periods) == 0:
            return {"growing": [], "declining": [], "emerging": []}
            
        recent_period = periods[-1]
        df_recent = df_trends[df_trends["period"] == recent_period]
        
        # Growing: Sort by positive growth rate
        growing = df_recent[df_recent["growth_rate"] > 0].sort_values(by="growth_rate", ascending=False).head(5)
        # Declining: Sort by negative growth rate
        declining = df_recent[df_recent["growth_rate"] < 0].sort_values(by="growth_rate", ascending=True).head(5)
        # Emerging: Frequency > 0 in recent period but had very low or zero frequency previously
        # We classify skills with growth_rate >= 0.5 or new skills as emerging
        emerging = df_recent[df_recent["growth_rate"] >= 0.3].sort_values(by="frequency", ascending=False).head(5)
        
        return {
            "growing": growing.to_dict(orient="records"),
            "declining": declining.to_dict(orient="records"),
            "emerging": emerging.to_dict(orient="records"),
            "all_trends": df_trends
        }
