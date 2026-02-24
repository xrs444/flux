const http = require('http');
const https = require('https');
const url = require('url');

const PORT = process.env.PORT || 3000;
const NOCODB_URL = process.env.NOCODB_URL || 'http://localhost:8080';
const SESSION_TTL = parseInt(process.env.SESSION_TTL_SECONDS || '604800', 10) * 1000; // 7 days default

// In-memory session store (consider Redis for multi-replica)
const sessionStore = new Map();

// Parse user mapping from environment
function getUserMapping() {
  const mapping = process.env.USER_MAPPING || '{}';
  try {
    return JSON.parse(mapping);
  } catch (err) {
    console.error('Failed to parse USER_MAPPING:', err.message);
    return {};
  }
}

// NocoDB login via API
function loginToNocoDB(email, password) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify({ email, password });
    const parsedUrl = url.parse(NOCODB_URL);

    const options = {
      hostname: parsedUrl.hostname,
      port: parsedUrl.port || (parsedUrl.protocol === 'https:' ? 443 : 80),
      path: '/api/v1/auth/user/signin',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': data.length
      }
    };

    const httpModule = parsedUrl.protocol === 'https:' ? https : http;
    const req = httpModule.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => body += chunk);
      res.on('end', () => {
        if (res.statusCode === 200) {
          try {
            const parsed = JSON.parse(body);
            if (parsed.token) {
              resolve({ success: true, token: parsed.token });
            } else {
              resolve({ success: false, error: 'No token in response' });
            }
          } catch (err) {
            resolve({ success: false, error: 'Invalid JSON response' });
          }
        } else {
          resolve({ success: false, error: `HTTP ${res.statusCode}` });
        }
      });
    });

    req.on('error', (err) => resolve({ success: false, error: err.message }));
    req.write(data);
    req.end();
  });
}

// Parse cookies
function parseCookies(cookieHeader) {
  const cookies = {};
  if (!cookieHeader) return cookies;

  cookieHeader.split(';').forEach(cookie => {
    const parts = cookie.trim().split('=');
    if (parts.length === 2) {
      cookies[parts[0]] = parts[1];
    }
  });
  return cookies;
}

// Proxy request to NocoDB
function proxyToNocoDB(req, res, token) {
  const parsedUrl = url.parse(NOCODB_URL);
  const targetUrl = url.parse(req.url);

  const options = {
    hostname: parsedUrl.hostname,
    port: parsedUrl.port || (parsedUrl.protocol === 'https:' ? 443 : 80),
    path: targetUrl.path,
    method: req.method,
    headers: {
      ...req.headers,
      'xc-auth': token,
      host: parsedUrl.hostname
    }
  };

  // Remove headers that shouldn't be forwarded
  delete options.headers['cookie'];
  delete options.headers['nc-session'];

  const httpModule = parsedUrl.protocol === 'https:' ? https : http;
  const proxy = httpModule.request(options, (proxyRes) => {
    const headers = { ...proxyRes.headers };

    // Combine NocoDB's Set-Cookie with our nc-session cookie
    const existingSetCookie = res.getHeader('Set-Cookie');
    if (existingSetCookie || headers['set-cookie']) {
      const cookies = [];
      if (existingSetCookie) {
        cookies.push(existingSetCookie);
      }
      if (headers['set-cookie']) {
        const nocodbCookies = Array.isArray(headers['set-cookie'])
          ? headers['set-cookie']
          : [headers['set-cookie']];
        cookies.push(...nocodbCookies);
      }
      headers['set-cookie'] = cookies;
    }

    res.writeHead(proxyRes.statusCode, headers);
    proxyRes.pipe(res);
  });

  proxy.on('error', (err) => {
    console.error('Proxy error:', err.message);
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Bad Gateway', message: err.message }));
  });

  req.pipe(proxy);
}

// Main request handler
async function handleRequest(req, res) {
  // Health check
  if (req.url === '/healthz') {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    return res.end('OK');
  }

  // Intercept token refresh - we manage auth via sessions, not NocoDB tokens
  if (req.url === '/auth/token/refresh' && req.method === 'POST') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ msg: 'Token refreshed' }));
  }

  // Get authenticated user from oauth2-proxy headers
  const userEmail = req.headers['x-auth-request-email'] || req.headers['x-forwarded-email'];
  console.log(`Request: ${req.method} ${req.url} from ${userEmail || 'anonymous'}`);

  if (!userEmail) {
    res.writeHead(401, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({
      error: 'Unauthorized',
      message: 'No authenticated user from oauth2-proxy'
    }));
  }

  // Check existing session
  const cookies = parseCookies(req.headers.cookie);
  const sessionId = cookies['nc-session'];
  const cachedSession = sessionStore.get(sessionId);

  if (cachedSession && cachedSession.email === userEmail && cachedSession.expires > Date.now()) {
    return proxyToNocoDB(req, res, cachedSession.token);
  }

  // Need to login to NocoDB
  const userMapping = getUserMapping();
  const credentials = userMapping[userEmail];

  if (!credentials) {
    console.error(`No credentials for user: ${userEmail}`);
    res.writeHead(403, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({
      error: 'Forbidden',
      message: 'No NocoDB credentials configured for your account'
    }));
  }

  // Perform login
  const loginResult = await loginToNocoDB(credentials.email, credentials.password);

  if (!loginResult.success) {
    console.error(`Login failed for ${userEmail}:`, loginResult.error);
    res.writeHead(500, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({
      error: 'Authentication failed',
      message: 'Failed to login to NocoDB'
    }));
  }

  // Create session
  const newSessionId = `sess_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  sessionStore.set(newSessionId, {
    email: userEmail,
    token: loginResult.token,
    expires: Date.now() + SESSION_TTL
  });

  // Set session cookie
  res.setHeader('Set-Cookie', `nc-session=${newSessionId}; HttpOnly; Secure; SameSite=Lax; Max-Age=${SESSION_TTL / 1000}; Path=/`);

  // Proxy the request
  proxyToNocoDB(req, res, loginResult.token);
}

// Session cleanup
setInterval(() => {
  const now = Date.now();
  let cleaned = 0;
  for (const [sessionId, session] of sessionStore.entries()) {
    if (session.expires < now) {
      sessionStore.delete(sessionId);
      cleaned++;
    }
  }
  if (cleaned > 0) {
    console.log(`Cleaned ${cleaned} expired sessions. Active: ${sessionStore.size}`);
  }
}, 60 * 60 * 1000); // Every hour

// Start server
const server = http.createServer(handleRequest);
server.listen(PORT, () => {
  console.log(`NocoDB Auth Shim running on port ${PORT}`);
  console.log(`Proxying to: ${NOCODB_URL}`);
  console.log(`Session TTL: ${SESSION_TTL / 1000}s`);
});
