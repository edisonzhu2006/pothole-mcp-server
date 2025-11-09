import { Tool, CallToolResult } from '@modelcontextprotocol/sdk/types.js';
import { SupabaseClient } from '@supabase/supabase-js';

export const queryHazardsToolDefinition: Tool = {
    name: "query_hazards",
    description: "Queries the hazard database for different analytics.",
    inputSchema: {
        type: "object",
        properties: {
            kind: {
                type: "string",
                description: "The type of query to perform.",
                enum: [
                    "area_with_most_hazards",
                    "top_severe_in_area",
                    "counts_by_type",
                    "open_vs_resolved"
                ]
            },
            area: {
                type: "string",
                description: "The area to query for, when applicable."
            }
        },
        required: ["kind"]
    }
};

export const estimateRepairPlanToolDefinition: Tool = {
    name: "estimate_repair_plan",
    description: "Estimates a repair plan for a given hazard.",
    inputSchema: {
        type: "object",
        properties: {
            hazard_id: {
                type: "number",
                description: "The ID of the hazard to estimate the repair plan for."
            }
        },
        required: ["hazard_id"]
    }
};

export const projectWorseningToolDefinition: Tool = {
    name: "project_worsening",
    description: "Projects how a hazard will worsen over time.",
    inputSchema: {
        type: "object",
        properties: {
            hazard_id: {
                type: "number",
                description: "The ID of the hazard to project."
            },
            lat: {
                type: "number",
                description: "The latitude of the hazard."
            },
            lon: {
                type: "number",
                description: "The longitude of the hazard."
            }
        }
    }
};

export async function handleQueryHazardsTool(supabase: SupabaseClient, args: any): Promise<CallToolResult> {
    const { kind, area } = args;
    let data, error;

    switch (kind) {
        case "area_with_most_hazards":
            ({ data, error } = await supabase.rpc('area_with_most_hazards'));
            break;
        case "top_severe_in_area":
            ({ data, error } = await supabase.rpc('top_severe_in_area', { area_name: area }));
            break;
        case "counts_by_type":
            ({ data, error } = await supabase.rpc('counts_by_type'));
            break;
        case "open_vs_resolved":
            ({ data, error } = await supabase.rpc('open_vs_resolved'));
            break;
        default:
            return {
                content: [{ type: "text", text: "Invalid query kind." }],
                isError: true
            };
    }

    if (error) {
        return {
            content: [{ type: "text", text: `Error querying hazards: ${error.message}` }],
            isError: true
        };
    }

    return {
        content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
        isError: false
    };
}

const prof: { [key: string]: number } = {
    "Civil Engineer": 120,
    "Structural Engineer": 150,
    "Geotechnical Engineer": 130,
    "Pavement Specialist": 110,
    "Construction Manager": 100,
    "Safety Inspector": 90,
};

const sev_scale: { [key: number]: { profs: string[], eq: string[], mat: string[] } } = {
    1: { profs: ["Safety Inspector"], eq: ["Inspection vehicle"], mat: ["Traffic cones"] },
    2: { profs: ["Pavement Specialist"], eq: ["Crack sealing machine"], mat: ["Asphalt sealant"] },
    3: { profs: ["Pavement Specialist", "Construction Manager"], eq: ["Asphalt patch truck"], mat: ["Hot mix asphalt"] },
    4: { profs: ["Civil Engineer", "Pavement Specialist", "Construction Manager"], eq: ["Asphalt paver", "Roller"], mat: ["Asphalt binder", "Aggregate"] },
    5: { profs: ["Structural Engineer", "Geotechnical Engineer", "Civil Engineer", "Construction Manager"], eq: ["Excavator", "Dump truck", "Concrete mixer"], mat: ["Reinforced concrete", "Sub-base material"] },
};

function build_plan(hazard: any) {
    const severity = hazard.severity;
    const plan = sev_scale[severity];
    if (!plan) {
        return { error: "Invalid severity level." };
    }

    const personnel_costs = plan.profs.reduce((acc, p) => acc + prof[p], 0);
    const plan_details = {
        personnel: plan.profs,
        equipment: plan.eq,
        materials: plan.mat,
        estimated_cost: personnel_costs * 8, // Assuming an 8-hour workday
    };

    return plan_details;
}

export async function handleEstimateRepairPlanTool(supabase: SupabaseClient, args: any): Promise<CallToolResult> {
    const { hazard_id } = args;
    const { data, error } = await supabase.from('hazards').select('*').eq('id', hazard_id).single();

    if (error || !data) {
        return {
            content: [{ type: "text", text: `Error fetching hazard: ${error?.message || 'Hazard not found'}` }],
            isError: true
        };
    }

    const plan = build_plan(data);
    return {
        content: [{ type: "text", text: JSON.stringify(plan, null, 2) }],
        isError: false
    };
}

const prog_per_week = 0.1;
const weather_mult: { [key: string]: number } = {
    "clear": 1.0,
    "clouds": 1.1,
    "drizzle": 1.2,
    "rain": 1.5,
    "thunderstorm": 2.0,
    "snow": 2.5,
    "mist": 1.3,
};

export async function handleProjectWorseningTool(supabase: SupabaseClient, args: any): Promise<CallToolResult> {
    const { hazard_id, lat, lng } = args;
    let hazard;

    if (hazard_id) {
        const { data, error } = await supabase.from('hazards').select('*').eq('id', hazard_id).single();
        if (error || !data) {
            return {
                content: [{ type: "text", text: `Error fetching hazard: ${error?.message || 'Hazard not found'}` }],
                isError: true
            };
        }
        hazard = data;
    } else if (lat && lng) {
        // This is a simplified example. A real implementation would use PostGIS for spatial queries.
        const { data, error } = await supabase.from('hazards').select('*').order('id', { ascending: false }).limit(1).single();
        if (error || !data) {
            return {
                content: [{ type: "text", text: `Error fetching hazard: ${error?.message || 'Hazard not found'}` }],
                isError: true
            };
        }
        hazard = data;
    } else {
        return {
            content: [{ type: "text", text: "Either hazard_id or lat/lon must be provided." }],
            isError: true
        };
    }

    // Placeholder for weather API call
    const weather_condition = "rain";
    const multiplier = weather_mult[weather_condition] || 1.0;
    const weekly_progression = prog_per_week * multiplier;

    const projections: { [key: string]: number } = {};
    let current_severity = hazard.severity;
    for (let i = 1; i <= 12; i++) {
        current_severity += weekly_progression;
        projections[`week_${i}`] = Math.min(5, Math.round(current_severity * 10) / 10);
    }

    return {
        content: [{ type: "text", text: JSON.stringify(projections, null, 2) }],
        isError: false
    };
}