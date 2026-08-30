/**
 * Utility tools for the Node-RED MCP server
 *
 * Forked from upstream to support HTTP Basic Auth: the Home Assistant
 * "Node-RED" add-on (hassio-addons/addon-node-red) has `auth_api: true` and no
 * native adminAuth/token option of its own — direct-access requests to its
 * admin API (bypassing HA's ingress, which uses cookie/session auth this tool
 * can't do either) are gated by an nginx front door that checks HTTP Basic
 * Auth against actual Home Assistant user credentials
 * (`WWW-Authenticate: Basic realm="Home Assistant Authentication"`). Upstream
 * only ever sends `Authorization: Bearer <token>`, which that front door
 * rejects outright — there's no OAuth2 token exchange to do here at all.
 */

import axios from 'axios';
import https from 'https';

/**
 * Build the Authorization header for a Node-RED API call.
 * Basic auth (nodeRedUsername/nodeRedPassword) takes precedence since that's
 * what the HA add-on's direct-access front door actually requires; the
 * original Bearer-token path is kept for anyone running this fork against a
 * vanilla Node-RED instance with real settings.js adminAuth.
 */
export function buildAuthHeaders(config) {
  if (config.nodeRedUsername && config.nodeRedPassword) {
    const basic = Buffer.from(`${config.nodeRedUsername}:${config.nodeRedPassword}`).toString('base64');
    return { Authorization: `Basic ${basic}` };
  }
  if (config.nodeRedToken) {
    return { Authorization: `Bearer ${config.nodeRedToken}` };
  }
  return {};
}

/**
 * Only relaxes TLS verification when explicitly opted into via
 * NODE_RED_INSECURE_TLS — default stays secure. Added because the add-on's
 * direct-access nginx cert was found expired during setup (2026-08-29); this
 * is an escape hatch to unblock, not a substitute for fixing the cert.
 */
export function buildHttpsAgent(config) {
  if (config.nodeRedUrl?.startsWith('https:') && config.nodeRedInsecureTls) {
    return new https.Agent({ rejectUnauthorized: false });
  }
  return undefined;
}

/**
 * Call the Node-RED API
 * @param {string} method - HTTP method (get, post, put, delete)
 * @param {string} path - API path
 * @param {Object|null} data - Data to send (optional)
 * @param {Object} config - Connection configuration
 * @returns {Promise<any>} Result of the API call
 */
export async function callNodeRed(method, path, data = null, config) {
  const url = config.nodeRedUrl + path;
  const headers = buildAuthHeaders(config);
  const httpsAgent = buildHttpsAgent(config);

  try {
    const response = await axios({ method, url, headers, data, httpsAgent });
    return response.data;
  } catch (error) {
    const message = error.response?.data || error.message;
    throw new Error(`Node-RED API error: ${message}`);
  }
}

/**
 * Format output of Node-RED flows
 * @param {Array} flows - Array of Node-RED flows
 * @returns {Object} Formatted data with statistics
 */
export function formatFlowsOutput(flows) {
  // Grouping by type
  const result = {
    tabs: flows.filter(n => n.type === 'tab'),
    nodes: flows.filter(n => n.type !== 'tab' && n.type !== 'subflow'),
    subflows: flows.filter(n => n.type === 'subflow')
  };

  // Statistics
  const stats = {
    tabCount: result.tabs.length,
    nodeCount: result.nodes.length,
    subflowCount: result.subflows.length,
    nodeTypes: {}
  };

  result.nodes.forEach(node => {
    if (!stats.nodeTypes[node.type]) stats.nodeTypes[node.type] = 0;
    stats.nodeTypes[node.type]++;
  });

  return {
    summary: `Node-RED project: ${stats.tabCount} tabs, ${stats.nodeCount} nodes, ${stats.subflowCount} subflows`,
    statistics: stats,
    data: result
  };
}
