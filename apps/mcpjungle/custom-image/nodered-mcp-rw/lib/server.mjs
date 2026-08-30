/**
 * MCP server for Node-RED
 * Allows language models to interact with Node-RED through the MCP protocol
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import 'dotenv/config';
import axios from 'axios';
import { buildAuthHeaders, buildHttpsAgent } from './utils.mjs';

// Import tool registrars
import registerFlowTools from './tools/flows.mjs';
import registerNodeTools from './tools/nodes.mjs';
import registerSettingsTools from './tools/settings.mjs';
import registerUtilityTools from './tools/utility.mjs';

/**
 * Default server settings
 */
const defaultConfig = {
  serverName: 'node-red-mcp-server',
  serverVersion: '1.0.0',
  nodeRedUrl: 'http://localhost:1880',
  nodeRedToken: '',
  nodeRedUsername: '',
  nodeRedPassword: '',
  nodeRedInsecureTls: false,
  transportType: 'stdio',
  verbose: false
};

/**
 * Creates and configures an MCP server for Node-RED
 * @param {Object} userConfig - User configuration
 * @returns {Object} Object with start method and other utilities
 */
export function createServer(userConfig = {}) {
  // Merge configuration
  const config = {
    ...defaultConfig,
    ...userConfig,
    nodeRedUrl: userConfig.nodeRedUrl || process.env.NODE_RED_URL || defaultConfig.nodeRedUrl,
    nodeRedToken: userConfig.nodeRedToken || process.env.NODE_RED_TOKEN || defaultConfig.nodeRedToken,
    nodeRedUsername: userConfig.nodeRedUsername || process.env.NODE_RED_USERNAME || defaultConfig.nodeRedUsername,
    nodeRedPassword: userConfig.nodeRedPassword || process.env.NODE_RED_PASSWORD || defaultConfig.nodeRedPassword,
    nodeRedInsecureTls: userConfig.nodeRedInsecureTls ?? (process.env.NODE_RED_INSECURE_TLS === 'true') ?? defaultConfig.nodeRedInsecureTls
  };

  // Create MCP server
  const server = new McpServer({
    name: config.serverName,
    version: config.serverVersion
  });

  // Register all tools
  registerFlowTools(server, config);
  registerNodeTools(server, config);
  registerSettingsTools(server, config);
  registerUtilityTools(server, config);

  /**
   * Tests the connection to Node-RED
   * @returns {Promise<boolean>} True if connection is successful
   */
  async function testNodeRedConnection() {
    try {
      const headers = buildAuthHeaders(config);
      const httpsAgent = buildHttpsAgent(config);
      await axios.get(config.nodeRedUrl, { headers, httpsAgent, timeout: 5000 });
      return true;
    } catch (error) {
      return false;
    }
  }

  /**
   * Starts the MCP server
   * @returns {Promise<void>}
   */
  async function start() {
    // Test Node-RED connection but don't stop if it fails
    try {
      await testNodeRedConnection();
    } catch (_) {
      // Ignore errors
    }

    // Create transport based on settings
    let transport;

    if (config.transportType === 'stdio') {
      transport = new StdioServerTransport();
    } else {
      throw new Error(`Unsupported transport type: ${config.transportType}`);
    }

    // Connect server through transport
    await server.connect(transport);
  }

  return {
    server,
    config,
    start,
    testNodeRedConnection
  };
}

// If this file is run directly (not imported as a module)
if (import.meta.url.startsWith('file:') && import.meta.url === `file://${process.argv[1]}`) {
  try {
    const server = createServer();
    server.start();
  } catch (err) {
    process.exit(1);
  }
}

export { defaultConfig };
