# Deep Dive Investigation Results

## Render (render.com → 216.24.57.1)

### CRITICAL: Extensive API Discovery Exposed

Render has a complete AI discovery API exposed on their origin IP:

#### Endpoints Found
1. **`/openapi.json`** - Full OpenAPI 3.1 spec for "Render AI Discovery API"
2. **`/llms.txt`** - LLMs index with metadata
3. **`/llms-full.txt`** - Full docs corpus for LLMs
4. **`/docs/api`** - API documentation page
5. **`/.well-known/api-catalog`** - API catalog in Linkset format
6. **`/.well-known/mcp.json`** - MCP server discovery
7. **`/.well-known/mcp/server-card.json`** - MCP Server Card
8. **`/.well-known/webmcp.json`** - WebMCP manifest
9. **`/.well-known/agents.json`** - Agent directory
10. **`/.well-known/agent-skills/index.json`** - Agent Skills discovery
11. **`/api/agent/docs-search`** - Docs search API
12. **`/api/status`** - API health status

#### MCP Server Exposed
```json
{
  "mcpServers": {
    "render": {
      "url": "https://mcp.render.com/mcp",
      "name": "Render MCP Server",
      "description": "Hosted MCP server for managing Render resources from AI tools.",
      "documentationUrl": "https://render.com/docs/mcp-server",
      "authentication": {
        "type": "bearer",
        "description": "Use Authorization: Bearer <RENDER_API_KEY>."
      }
    }
  }
}
```

#### Agent Skills Exposed
Full skill definitions for:
- render-background-workers
- render-blueprints
- render-cli
- render-cron-jobs
- render-debug
- render-deploy
- render-disks
- render-docker
- render-domains
- render-env-vars
- render-keyvalue
- render-mcp
- render-migrate-from-heroku
- render-monitor
- render-networking
- render-postgres
- render-private-services
- render-scaling
- render-static-sites
- render-web-services
- render-workflows

#### Attack Vectors
1. **API Discovery** - Complete OpenAPI spec exposed
2. **MCP Server** - Can potentially interact with Render MCP
3. **Agent Skills** - Full skill definitions exposed
4. **No Authentication Required** - All discovery endpoints are public

---

## Fly.io (fly.io → 37.16.18.81)

### GraphQL-like API

Fly.io returns JSON errors for API endpoints:
```json
{"errors":{"detail":"not found"}}
```

#### Endpoints Tested
- `/api` → `{"errors":{"detail":"not found"}}`
- `/api/v1` → `{"errors":{"detail":"not found"}}`
- `/graphql` → HTML 404 page

#### Notes
- Returns proper JSON error format
- Uses Phoenix framework (Elixir)
- CSRF token exposed in HTML: `ciNxWB4gIVM-YyVbVGEQdzIHah5QPSAd-l03PAWbg4Vj73ZDGLSZ2iKp`
- Google Analytics tracking: `G-EX6DMZ1DZV`

---

## Grafana (grafana.com → 34.120.177.193)

### JSON API with Error Codes

Grafana returns structured JSON errors:
```json
{
  "code": "Unauthorized",
  "message": "Login Required",
  "requestId": "1fada9b7-c7a6-4fcf-8033-e58095946fdd"
}
```

#### Endpoints Tested
- `/api` → 301 redirect
- `/api/health` → `{"code":"NotFound","message":"/health does not exist"}`
- `/api/frontend/settings` → `{"code":"NotFound","message":"/frontend/settings does not exist"}`

#### Notes
- Uses nginx server
- Returns proper error codes (Unauthorized, NotFound)
- Request IDs for tracking

---

## Cohere (cohere.com → 76.76.21.21)

### Next.js App

Cohere returns 404 HTML pages for API endpoints:
- Uses Vercel hosting
- Next.js framework
- Returns standard 404 page

---

## Supabase (supabase.com → 216.150.1.193)

### Next.js App

Supabase returns 404 HTML pages for API endpoints:
- Uses Vercel hosting
- Next.js framework
- Returns standard 404 page
- Has `/.well-known/api-catalog` endpoint

---

## Summary

| Company | Origin IP | Interesting Findings |
|---------|-----------|---------------------|
| Render | 216.24.57.1 | **CRITICAL**: Full API discovery, MCP server, Agent Skills exposed |
| Fly.io | 37.16.18.81 | GraphQL-like API, CSRF token, Phoenix framework |
| Grafana | 34.120.177.193 | JSON API with error codes, request tracking |
| Cohere | 76.76.21.21 | Next.js app (no API exposed) |
| Supabase | 216.150.1.193 | Next.js app (no API exposed) |
