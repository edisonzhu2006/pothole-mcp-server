from mcp.server.fastmcp import FastMCP
from supabase import create_client, Client
from pathlib import Path
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from collections import Counter
from collections import Counter

# env
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")
load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ["SUPABASE_KEY"]
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

mcp = FastMCP("hazard-mcp")

# ---------- helpers (type-aware, severity-scaled) ----------
PROFILES = {
  "pothole": {"base_h":1.0,"labor":90,"equip":65,"traffic":55,"mat":240,
              "crew":[{"role":"Lead/Safety","count":1},{"role":"Laborer","count":1},{"role":"Truck","count":1}],
              "steps":["Traffic control","Prepare/clean","Place material","Compact","Cleanup"]},
  "flooding":{"base_h":1.3,"labor":90,"equip":70,"traffic":55,"mat":60,
              "crew":[{"role":"Lead/Safety","count":1},{"role":"Pump Op","count":1}],
              "steps":["Traffic control","Assess blockage","Pump/clear","Mitigate","Cleanup"]},
  "debris":{"base_h":0.8,"labor":85,"equip":55,"traffic":50,"mat":40,
            "crew":[{"role":"Lead/Safety","count":1},{"role":"Laborer","count":1}],
            "steps":["Traffic control","Remove debris","Haul/Stage","Sweep","Reopen"]},
  "damaged_signage":{"base_h":0.9,"labor":85,"equip":50,"traffic":50,"mat":180,
            "crew":[{"role":"Lead/Safety","count":1},{"role":"Installer","count":1}],
            "steps":["Traffic control","Remove hardware","Install/align","Verify sightlines","Cleanup"]},
}
def prof(t: Optional[str]): return PROFILES.get((t or "").lower(), PROFILES["pothole"])
def sev_scale(s: int): s=max(0,min(10,int(s or 3))); return max(0.6,min(3.0,0.6+0.25*s))
def build_plan(h: Dict[str,Any]) -> Dict[str,Any]:
    p=prof(h.get("hazard_type")); scale=sev_scale(h.get("severity"))
    hours=p["base_h"]*scale; mobil=120
    mat=p["mat"]*(0.6+0.4*scale)
    labor=p["labor"]*hours; equip=p["equip"]*max(0.6,0.5*hours); traffic=p["traffic"]*max(0.5,0.6*hours)
    sub=mat+labor+equip+traffic+mobil; cont=0.12*sub; ohp=0.15*sub; total=round(sub+cont+ohp,2)
    step_t=round(max(0.15, hours/max(1,len(p["steps"]))),2)
    steps=[{"step":i+1,"name":n,"duration_hr":step_t} for i,n in enumerate(p["steps"])]
    return {
      "assumptions":{"hazard_type":(h.get("hazard_type") or "").lower(),"severity":int(h.get("severity") or 3),"scale":round(scale,2)},
      "costs":{"material":round(mat,2),"labor":round(labor,2),"equipment":round(equip,2),
               "traffic_control":round(traffic,2),"mobilization":mobil,"contingency_12pct":round(cont,2),
               "overhead_profit_15pct":round(ohp,2),"total_estimate":total},
      "crew":p["crew"],"tools_materials":p["steps"],"plan_steps":steps,
      "schedule":{"on_site_hours":round(hours+0.3,2),"lane_closure_hours":round(max(0.75,0.6*hours),2),"target_completion":"same-day"},
      "context":{"id":h.get("id"),"location":h.get("location"),"status":h.get("status"),
                 "description_excerpt":(h.get("description") or "")[:140],"images_count":len(h.get("images") or [])}
    }

def prog_per_week(sev:int, t:Optional[str]):
    base=0.02*max(0,min(10,int(sev or 3))); mult={"pothole":1.4,"flooding":1.25,"debris":0.85,"damaged_signage":0.75}.get((t or "").lower(),1.1)
    return min(0.25, base*mult)
def weather_mult(precip_mm:float=0.0, ft:int=0): return 1.0 + min(0.5,precip_mm/200.0) + min(0.4,0.05*ft)

# ------------------ TOOL 1: analytics ------------------
@mcp.tool()
def query_hazards(kind: str, location: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """
    Answer analytics over hazards.
    - `area_with_most_hazards`: returns top X locations with most hazards. Use `limit` for X. Use `location` to filter by a region (e.g., a city or state).
    - `top_severe_in_area`: returns top severe hazards for an exact `location`.
    - `counts_by_type`: returns hazard counts by type. Can be filtered by `location`.
    - `open_vs_resolved`: returns open vs resolved counts. Can be filtered by `location`.
    """
    k = (kind or "").lower()
    if k == "area_with_most_hazards":
        query = sb.table("hazards").select("location")
        if location:
            query = query.ilike("location", f"%{location}%")
        all_hazards = query.execute().data
        if not all_hazards:
            return {"question": k, "result": []}
        location_counts = Counter(h["location"] for h in all_hazards if h.get("location"))
        most_common = location_counts.most_common(limit)
        rows = [{"location": loc, "count": count} for loc, count in most_common]
        return {"question": k, "location_filter": location, "result": rows}
    if k == "top_severe_in_area":
        if not location:
            raise ValueError("location is required")
        rows = (
            sb.table("hazards")
            .select("*")
            .eq("location", location)
            .order("severity", desc=True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        return {"question": k, "location": location, "result": rows}
    if k == "counts_by_type":
        q = sb.table("hazards").select("hazard_type")
        if location:
            q = q.eq("location", location)
        all_hazards = q.execute().data
        if not all_hazards:
            return {"question": k, "location": location, "result": []}
        type_counts = Counter(h["hazard_type"] for h in all_hazards if h.get("hazard_type"))
        rows = [{"hazard_type": t, "count": c} for t, c in type_counts.items()]
        return {"question": k, "location": location, "result": rows}
    if k == "open_vs_resolved":
        q = sb.table("hazards").select("status")
        if location:
            q = q.eq("location", location)
        all_hazards = q.execute().data
        if not all_hazards:
            return {"question": k, "location": location, "result": []}
        status_counts = Counter(h["status"] for h in all_hazards if h.get("status"))
        rows = [{"status": s, "count": c} for s, c in status_counts.items()]
        return {"question": k, "location": location, "result": rows}
    raise ValueError("Unknown kind")

# ------------------ TOOL 2: repair plan ----------------
@mcp.tool()
def estimate_repair_plan(hazard_id: str) -> Dict[str,Any]:
    """Return a type-aware cost estimate and fully detailed plan for a hazard UUID."""
    recs = sb.table("hazards").select("*").eq("id", hazard_id).limit(1).execute().data
    if not recs: raise ValueError(f"Hazard {hazard_id} not found")
    h = recs[0]
    return {"hazard": h, "repair_plan": build_plan(h)}

# ------------- TOOL 3: projections (hazard/area) -------
@mcp.tool()
def project_worsening(hazard_id: Optional[str] = None, location: Optional[str] = None,
                      horizon_days: int = 30, precip_mm: float = 0.0,
                      freeze_thaw_cycles: int = 0) -> Dict[str,Any]:
    """Project severity into the future for a hazard ID or a whole location."""
    if not hazard_id and not location: raise ValueError("Provide hazard_id or location")
    w = weather_mult(precip_mm, freeze_thaw_cycles); weeks = max(0.0, horizon_days/7.0)
    if hazard_id:
        recs = sb.table("hazards").select("*").eq("id", hazard_id).limit(1).execute().data
        if not recs: raise ValueError(f"Hazard {hazard_id} not found")
        h = recs[0]; sev0=int(h.get("severity") or 3); p=prog_per_week(sev0, h.get("hazard_type"))
        sev_proj = min(10.0, sev0*(1.0+p*weeks)*w)
        age_days = None
        if h.get("created_at"):
            try:
                dt = datetime.fromisoformat(h["created_at"].replace("Z","+00:00"))
                age_days = (datetime.now(timezone.utc)-dt).days
            except Exception: pass
        return {"mode":"hazard","hazard_id":hazard_id,"horizon_days":horizon_days,
                "inputs":{"severity_now":sev0,"progression_per_week":round(p,4),"weather_multiplier":round(w,3),"age_days":age_days},
                "projection":{"projected_severity":round(sev_proj,2),"recommended_action_window_days":14 if sev_proj>=7 else 30}}
    # area
    rows = sb.table("hazards").select("*").eq("location", location).limit(5000).execute().data
    if not rows: return {"mode":"area","location":location,"horizon_days":horizon_days,"projection":"no hazards found"}
    now_sum=proj_sum=0.0; urgent=0; samples=[]
    for h in rows:
        sev0=int(h.get("severity") or 3); p=prog_per_week(sev0, h.get("hazard_type"))
        sev_proj=min(10.0, sev0*(1.0+p*weeks)*w)
        now_sum+=sev0; proj_sum+=sev_proj
        if sev_proj>=7: urgent+=1
        if len(samples)<50: samples.append({"id":h["id"],"hazard_type":h.get("hazard_type"),"severity_now":sev0,"severity_projected":round(sev_proj,2)})
    n=max(1,len(rows))
    return {"mode":"area","location":location,"horizon_days":horizon_days,
            "inputs":{"weather_multiplier":round(w,3),"freeze_thaw_cycles":freeze_thaw_cycles,"precip_mm":precip_mm},
            "summary":{"hazard_count":len(rows),"avg_severity_now":round(now_sum/n,2),"avg_severity_projected":round(proj_sum/n,2),"urgent_>=7_count":urgent},
            "samples":samples}

def main():
    mcp.run()
