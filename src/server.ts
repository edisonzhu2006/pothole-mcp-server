import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import {
    CallToolRequestSchema,
    ErrorCode,
    ListToolsRequestSchema,
    McpError,
} from '@modelcontextprotocol/sdk/types.js';
import { createSupabaseClient } from './client.js';
import {
    queryHazardsToolDefinition,
    estimateRepairPlanToolDefinition,
    projectWorseningToolDefinition,
    handleQueryHazardsTool,
    handleEstimateRepairPlanTool,
    handleProjectWorseningTool
} from './tools/index.js';

/**
 * Main server class for Pothole Detection MCP integration
 * @class PotholeServer
 */
export class PotholeServer {
    private client: any;
    private server: Server;

    /**
     * Creates a new PotholeServer instance
     * @param {string} supabaseUrl - Supabase project URL
     * @param {string} supabaseKey - Supabase API key
     */
    constructor(supabaseUrl: string, supabaseKey: string) {
        this.client = createSupabaseClient(supabaseUrl, supabaseKey);
        this.server = new Server(
            {
                name: 'pothole-detection',
                version: '0.1.0',
            },
            {
                capabilities: {
                    tools: {},
                },
            }
        );

        this.setupHandlers();
        this.setupErrorHandling();
    }

    /**
     * Sets up MCP request handlers for tools
     * @private
     */
    private setupHandlers(): void {
        // List available tools
        this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
            tools: [queryHazardsToolDefinition, estimateRepairPlanToolDefinition, projectWorseningToolDefinition],
        }));

        // Handle tool calls
        this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
            const { name, arguments: args } = request.params;

            switch (name) {
                case 'query_hazards':
                    return handleQueryHazardsTool(this.client, args);
                
                case 'estimate_repair_plan':
                    return handleEstimateRepairPlanTool(this.client, args);

                case 'project_worsening':
                    return handleProjectWorseningTool(this.client, args);
                
                default:
                    throw new McpError(
                        ErrorCode.MethodNotFound,
                        `Unknown tool: ${name}`
                    );
            }
        });
    }

    /**
     * Configures error handling and graceful shutdown
     * @private
     */
    private setupErrorHandling(): void {
        this.server.onerror = (error) => console.error('[MCP Error]', error);
        
        process.on('SIGINT', async () => {
            await this.server.close();
            process.exit(0);
        });
    }

    /**
     * Returns the underlying MCP server instance
     * @returns {Server} MCP server instance
     */
    getServer(): Server {
        return this.server;
    }
}

/**
 * Factory function for creating standalone server instances
 * Used by HTTP transport for session-based connections
 * @param {string} supabaseUrl - Supabase project URL
 * @param {string} supabaseKey - Supabase API key
 * @returns {Server} Configured MCP server instance
 */
export function createStandaloneServer(supabaseUrl: string, supabaseKey: string): Server {
    const server = new Server(
        {
            name: "pothole-detection-discovery",
            version: "0.1.0",
        },
        {
            capabilities: {
                tools: {},
            },
        },
    );

    const client = createSupabaseClient(supabaseUrl, supabaseKey);

    // Set up handlers
    server.setRequestHandler(ListToolsRequestSchema, async () => ({
        tools: [queryHazardsToolDefinition, estimateRepairPlanToolDefinition, projectWorseningToolDefinition],
    }));

    server.setRequestHandler(CallToolRequestSchema, async (request) => {
        const { name, arguments: args } = request.params;

        switch (name) {
            case 'query_hazards':
                return handleQueryHazardsTool(client, args);
            
            case 'estimate_repair_plan':
                return handleEstimateRepairPlanTool(client, args);

            case 'project_worsening':
                return handleProjectWorseningTool(client, args);
            
            default:
                throw new McpError(
                    ErrorCode.MethodNotFound,
                    `Unknown tool: ${name}`
                );
        }
    });

    return server;
}