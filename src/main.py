from __future__ import annotations
import os, math, asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openmcp import MCPServer, tool
from supabase import create_client, Client

load_dotenv()
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_ANON_KEY"]
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

server = MCPServer("hazard-mcp")

# --------------------------------------------------------------------
# Hazard profiles: ONLY use fields you have: hazard_type + severity.
# You can tune numbers later per city/vendor. Everything else derives
# from severity so it works for ANY hazard record in your table.
# --------------------------------------------------------------------
HAZARD_PROFILES: Dict[str, Dict[str, Any]] = {
    # road surface failure (default bucket if unknown)
    "pothole": {
        "crew": [{"role": "Lead/Safety", "count": 1},
                 {"role": "Patcher/Laborer", "count": 1},
                 {"role": "Truck Operator", "count": 1}],
        "base_hours": 1.0,            # scaled by severity
        "equipment_hourly": 65.0,
        "labor_hourly": 90.0,
        "traffic_ctrl_hourly": 55.0,
        "material_baseline": 240.0,   # material proxy (m³-equivalent) – we don't have size fields
        "materials": ["Hot mix/cold patch", "Tack (as needed)", "Broom/shovel", "Cones/signage"],
        "steps": ["Traffic control setup", "Prepare/clean defect", "Place material", "Compact & finish", "Cleanup & reopen"],
    },
    # water pooling/blocked drainage
    "flooding": {
        "crew": [{"role": "Lead/Safety", "count": 1},
                 {"role": "Pump Operator", "count": 1}],
        "base_hours": 1.3,
        "equipment_hourly": 70.0,
        "labor_hourly": 90.0,
        "traffic_ctrl_hourly": 55.0,
        "material_baseline": 60.0,
        "materials": ["Portable pump/hose", "Sandbags as needed", "Cones/signage"],
        "steps": ["Traffic control", "Assess blockage", "Pump/clear inlet", "Place temp mitigation", "Cleanup/monitor"],
    },
    # fallen tree/branch/objects
    "debris": {
        "crew": [{"role": "Lead/Safety", "count": 1},
                 {"role": "Laborer", "count": 1}],
        "base_hours": 0.8,
        "equipment_hourly": 55.0,
        "labor_hourly": 85.0,
        "traffic_ctrl_hourly": 50.0,
        "material_baseline": 40.0,
        "materials": ["Chainsaw (if needed)", "Broom/shovel", "Trash bags", "Cones/signage"],
        "steps": ["Traffic control", "Segment and remove debris", "Load/haul or stage", "Sweep/cleanup", "Reopen"],
    },
    # bent/missing sign, signal face issues
    "damaged_signage": {
        "crew": [{"role": "Lead/Safety", "count": 1},
                 {"role": "Installer", "count": 1}],
        "base_hours": 0.9,
        "equipment_hourly": 50.0,
        "labor_hourly": 85.0,
        "traffic_ctrl_hourly": 50.0,
        "material_baseline": 180.0,   # sign/hardware proxy
        "materials": ["Sign panel/post", "Hardware/anchors", "Cones/signage"],
        "steps": ["Traffic control", "Remove damaged hardware", "Install/align new sign", "Tighten & verify sightlines", "Cleanup"],
    },
}

def _get_profile(hazard_type: Optional[str]) -> Dict[str, Any]:
    t = (hazard_type or "").strip().lower()
    return HAZARD_PROFILES.get(t, HAZARD_PROFILES["pothole"])  # default profile

def _severity_scale(sev: int) -> float:
    """Map severity 0–10 → multiplier (light to heavy). Uses only severity."""
    s = max(0, min(10, int(sev)))
    # gentle growth at low, steeper at high; cap to avoid explosions
    return max(0.6, min(3.0, 0.6 + 0.25 * s))

def _build_plan_for(h: Dict[str, Any]) -> Dict[str, Any]:
    prof = _get_profile(h.get("hazard_type"))
    sev = int(h.get("severity") or 3)
    scale = _severity_scale(sev)

    labor = prof["labor_hourly"]
    equip = prof["equipment_hourly"]
    traffic = prof["traffic_ctrl_hourly"]
    base_hours = prof["base_hours"] * scale
    mobilization = 120.0

    # We don't have geometry; use severity to scale a material baseline:
    material_cost = prof["material_baseline"] * (0.6 + 0.4 * scale)

    labor_cost = labor * base_hours
    equipment_cost = equip * max(0.6, 0.5 * base_hours)
    traffic_ctrl_cost = traffic * max(0.5, 0.6 * base_hours)

    subtotal = material_cost + labor_cost + equipment_cost + traffic_ctrl_cost + mobilization
    contingency = 0.12 * subtotal
    ohp = 0.15 * subtotal
    total = round(subtotal + contingency + ohp, 2)

    # split steps into timed blocks proportionally
    step_names = prof["steps"]
    step_time = round(max(0.15, base_hours / max(1, len(step_names))), 2)
    steps = [{"step": i+1, "name": n, "duration_hr": step_time} for i, n in enumerate(step_names)]

    return {
        "assumptions": {
            "hazard_type": (h.get("hazard_type") or "").lower(),
            "severity": sev,
            "scaling": round(scale, 2),
        },
        "costs": {
            "material": round(material_cost, 2),
            "labor": round(labor_cost, 2),
            "equipment": round(equipment_cost, 2),
            "traffic_control": round(traffic_ctrl_cost, 2),
            "mobilization": mobilization,
            "contingency_12pct": round(contingency, 2),
            "overhead_profit_15pct": round(ohp, 2),
            "total_estimate": total,
        },
        "crew": prof["crew"],
        "tools_materials": prof["materials"],
        "plan_steps": steps,
        "schedule": {
            "on_site_hours": round(base_hours + 0.3, 2),
            "lane_closure_hours": round(max(0.75, 0.6 * base_hours), 2),
            "target_completion": "same-day",
        },
        "context": {
            "id": h.get("id"),
            "location": h.get("location"),
            "status": h.get("status"),
            "description_excerpt": (h.get("description") or "")[:140],
            "images_count": len(h.get("images") or []),
        },
        "notes": "Type-aware, severity-scaled estimate using only fields present in your table.",
    }

# ---- progression model (uses hazard_type + severity only; optional weather params at call time)
TYPE_WORSENING = {
    "pothole": 1.40,
    "flooding": 1.25,
    "debris": 0.85,
    "damaged_signage": 0.75,
}
def _progression_per_week(severity: int, hazard_type: Optional[str]) -> float:
    base = 0.02 * max(0, min(10, severity))
    mult = TYPE_WORSENING.get((hazard_type or "").lower(), 1.1)
    return min(0.25, base * mult)  # cap 25%/wk

def _weather_multiplier(precip_mm: float = 0.0, freeze_thaw_cycles: int = 0) -> float:
    return 1.0 + min(0.5, precip_mm / 200.0) + min(0.4, 0.05 * freeze_thaw_cycles)

# =========================================================
# TOOL 1 — Analytics (location / status / type; DB-only)
# =========================================================
@server.binding()
class AnalyticsTools:
    @tool(description="Answer analytics over hazards. kinds: 'area_with_most_hazards', 'top_severe_in_area', 'counts_by_type', 'open_vs_resolved'. Uses 'location' as area.")
    def query_hazards(kind: str, location: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        k = (kind or "").lower()

        if k == "area_with_most_hazards":
            rows = (sb.table("hazards")
                      .select("location, count:id")
                      .group("location")
                      .order("count", desc=True)
                      .limit(1)
                      .execute().data)
            return {"question": k, "result": rows}

        if k == "top_severe_in_area":
            if not location:
                raise ValueError("location is required for top_severe_in_area")
            rows = (sb.table("hazards")
                      .select("*")
                      .eq("location", location)
                      .order("severity", desc=True)
                      .order("created_at", desc=True)
                      .limit(limit)
                      .execute().data)
            return {"question": k, "location": location, "result": rows}

        if k == "counts_by_type":
            q = sb.table("hazards").select("hazard_type, count:id").group("hazard_type")
            if location:
                q = q.eq("location", location)
            return {"question": k, "location": location, "result": q.execute().data}

        if k == "open_vs_resolved":
            q = sb.table("hazards").select("status, count:id").group("status")
            if location:
                q = q.eq("location", location)
            return {"question": k, "location": location, "result": q.execute().data}

        raise ValueError("Unknown kind. Use: area_with_most_hazards | top_severe_in_area | counts_by_type | open_vs_resolved")

# =========================================================
# TOOL 2 — Repair plan & cost (type-aware; DB-only)
# =========================================================
@server.binding()
class RepairTools:
    @tool(description="Build a type-aware cost estimate and fully detailed repair plan for a hazard by UUID. Uses only your DB fields.")
    def estimate_repair_plan(hazard_id: str) -> Dict[str, Any]:
        recs = sb.table("hazards").select("*").eq("id", hazard_id).limit(1).execute().data
        if not recs:
            raise ValueError(f"Hazard {hazard_id} not found")
        h = recs[0]
        return {"hazard": h, "repair_plan": _build_plan_for(h)}

# =========================================================
# TOOL 3 — Future projection (hazard or area; DB-only)
# =========================================================
@server.binding()
class ProjectionTools:
    @tool(description="Project worsening for a single hazard (id) or an area (location). Optional weather inputs: precip_mm, freeze_thaw_cycles. Uses only your DB columns.")
    def project_worsening(
        hazard_id: Optional[str] = None,
        location: Optional[str] = None,
        horizon_days: int = 30,
        precip_mm: float = 0.0,
        freeze_thaw_cycles: int = 0
    ) -> Dict[str, Any]:
        if not hazard_id and not location:
            raise ValueError("Provide hazard_id or location")

        weather_mult = _weather_multiplier(precip_mm, freeze_thaw_cycles)
        weeks = max(0.0, horizon_days / 7.0)

        if hazard_id:
            recs = sb.table("hazards").select("*").eq("id", hazard_id).limit(1).execute().data
            if not recs:
                raise ValueError(f"Hazard {hazard_id} not found")
            h = recs[0]
            sev0 = int(h.get("severity") or 3)
            p = _progression_per_week(sev0, h.get("hazard_type"))
            sev_proj = min(10.0, sev0 * (1.0 + p * weeks) * weather_mult)

            # age from created_at (if present)
            age_days = None
            created_at = h.get("created_at")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    age_days = (datetime.now(timezone.utc) - dt).days
                except Exception:
                    pass

            return {
                "mode": "hazard",
                "hazard_id": hazard_id,
                "horizon_days": horizon_days,
                "inputs": {
                    "severity_now": sev0,
                    "progression_per_week": round(p, 4),
                    "weather_multiplier": round(weather_mult, 3),
                    "age_days": age_days,
                },
                "projection": {
                    "projected_severity": round(sev_proj, 2),
                    "risk_note": "Type-aware heuristic using severity & optional weather.",
                    "recommended_action_window_days": 14 if sev_proj >= 7 else 30,
                },
            }

        # Area aggregation by location
        rows = (sb.table("hazards").select("*").eq("location", location).limit(5000).execute().data)
        if not rows:
            return {"mode": "area", "location": location, "horizon_days": horizon_days, "projection": "no hazards found"}

        sev_now_sum = 0.0
        sev_proj_sum = 0.0
        urgent = 0
        samples: List[Dict[str, Any]] = []

        for h in rows:
            sev0 = int(h.get("severity") or 3)
            p = _progression_per_week(sev0, h.get("hazard_type"))
            sev_proj = min(10.0, sev0 * (1.0 + p * weeks) * weather_mult)
            sev_now_sum += sev0
            sev_proj_sum += sev_proj
            if sev_proj >= 7.0:
                urgent += 1
            if len(samples) < 50:
                samples.append({"id": h["id"], "hazard_type": h.get("hazard_type"),
                                "severity_now": sev0, "severity_projected": round(sev_proj, 2)})

        n = max(1, len(rows))
        return {
            "mode": "area",
            "location": location,
            "horizon_days": horizon_days,
            "inputs": {"weather_multiplier": round(weather_mult, 3),
                       "freeze_thaw_cycles": freeze_thaw_cycles, "precip_mm": precip_mm},
            "summary": {
                "hazard_count": len(rows),
                "avg_severity_now": round(sev_now_sum / n, 2),
                "avg_severity_projected": round(sev_proj_sum / n, 2),
                "urgent_>=7_count": urgent,
            },
            "samples": samples,
        }

# -------- Serve --------
async def main():
    print("🚀 Hazard MCP (analytics • repair • projection)")
    print("🔧 Tools: query_hazards, estimate_repair_plan, project_worsening")
    await server.serve(transport="streamable-http", verbose=False, log_level="critical")

if __name__ == "__main__":
    asyncio.run(main())
