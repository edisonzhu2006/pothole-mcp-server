/**
 * Type definitions for Pothole Detection MCP
 */

/**
 * Arguments for the query_hazards tool
 * @interface QueryHazardsArgs
 */
export interface QueryHazardsArgs {
    kind: 'area_with_most_hazards' | 'top_severe_in_area' | 'counts_by_type' | 'open_vs_resolved';
    lat?: number;
    lng?: number;
    radius?: number;
    limit?: number;
}

/**
 * Arguments for the estimate_repair_plan tool
 * @interface EstimateRepairPlanArgs
 */
export interface EstimateRepairPlanArgs {
    hazard_id: string;
}

/**
 * Arguments for the project_worsening tool
 * @interface ProjectWorseningArgs
 */
export interface ProjectWorseningArgs {
    hazard_id?: string;
    lat?: number;
    lng?: number;
}