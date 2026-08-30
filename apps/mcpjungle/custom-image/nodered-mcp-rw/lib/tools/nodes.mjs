/**
 * MCP tools for working with Node-RED nodes
 */

import { z } from 'zod';
import { callNodeRed } from '../utils.mjs';

/**
 * Registers node-related tools in the MCP server
 * @param {Object} server - MCP server instance
 * @param {Object} config - Server configuration
 */
export default function registerNodeTools(server, config) {
  // Trigger inject node
  server.tool(
    'inject',
    { id: z.string().describe('Inject node ID') },
    async ({ id }) => {
      await callNodeRed('post', '/inject/' + id, null, config);
      return { content: [{ type: 'text', text: `Inject node ${id} triggered` }] };
    }
  );

  // Get list of installed nodes
  server.tool(
    'get-nodes',
    {},
    async () => {
      const nodes = await callNodeRed('get', '/nodes', null, config);
      return {
        content: [{ type: 'text', text: JSON.stringify(nodes, null, 2) }]
      };
    }
  );

  // Get information about a specific module
  server.tool(
    'get-node-info',
    { module: z.string().describe('Node module name') },
    async ({ module }) => {
      const info = await callNodeRed('get', '/nodes/' + module, null, config);
      return {
        content: [{ type: 'text', text: JSON.stringify(info, null, 2) }]
      };
    }
  );

  // Enable/disable node module
  server.tool(
    'toggle-node-module',
    {
      module: z.string().describe('Node module name'),
      enabled: z.boolean().describe('true to enable, false to disable')
    },
    async ({ module, enabled }) => {
      try {
        await callNodeRed('put', '/nodes/' + module, { enabled }, config);
        return {
          content: [{
            type: 'text',
            text: `Module ${module} ${enabled ? 'enabled' : 'disabled'}`
          }]
        };
      } catch (error) {
        return { content: [{ type: 'text', text: `Error: ${error.message}` }] };
      }
    }
  );

  // Find nodes by type
  server.tool(
    'find-nodes-by-type',
    { nodeType: z.string().describe('Node type to search for') },
    async ({ nodeType }) => {
      const flows = await callNodeRed('get', '/flows', null, config);
      const nodes = flows.filter(node => node.type === nodeType);

      return {
        content: [{
          type: 'text',
          text: nodes.length > 0
            ? `Found ${nodes.length} nodes of type "${nodeType}":\n\n${JSON.stringify(nodes, null, 2)}`
            : `No nodes of type "${nodeType}" found`
        }]
      };
    }
  );

  // Search nodes by name/properties
  server.tool(
    'search-nodes',
    {
      query: z.string().describe('String to search in node name or properties'),
      property: z.string().optional().describe('Specific property to search (optional)')
    },
    async ({ query, property }) => {
      const flows = await callNodeRed('get', '/flows', null, config);

      const nodes = flows.filter(node => {
        if (property) {
          return node[property] && String(node[property]).includes(query);
        } else {
          return JSON.stringify(node).includes(query);
        }
      });

      return {
        content: [{
          type: 'text',
          text: nodes.length > 0
            ? `Found ${nodes.length} nodes matching query "${query}":\n\n${JSON.stringify(nodes, null, 2)}`
            : `No nodes found matching query "${query}"`
        }]
      };
    }
  );
}
