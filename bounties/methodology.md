# Web Testing Methodology

Same pattern as our Ivanti work — find the crack.

## Phase 1: Recon (in Chrome DevTools)

Open F12 → Network tab → check "Preserve log"

1. **Walk through the app** — click everything, watch what requests fire
2. **Look for patterns** — auth headers, session tokens, API endpoints
3. **Map the surface** — every URL path you see is a potential crack

## Phase 2: The 7 Cracks

### 1. IDOR (Insecure Direct Object Reference)
- Look for IDs in URLs or request bodies: `/users/12345`, `{"conversation_id": "abc"}`
- Change the ID to something else — if you see another user's data, that's a bounty
- *Like: STDispatch RPC didn't check authorization before accepting our requests*

### 2. Auth bypass
- Can you access an endpoint without the auth header?
- Does changing `role: user` to `role: admin` in a JWT work?
- *Like: NOP-ing the IsUserAdministrator check in STAgentCtl.exe*

### 3. Rate limiting / brute force
- Can you spam an API endpoint? No limit = potential data scraping
- Login page: try wrong passwords rapidly — any lockout?

### 4. Input validation
- Any text field: try `' OR 1=1 --` (SQLi)
- Any reflected text: try `<script>alert(1)</script>` (XSS)
- File upload: try uploading non-image files

### 5. JWT / Token tricks
- Decode JWTs at jwt.io — check if you can modify claims
- Try removing the signature, setting `"admin": true`, `"sub": "different_user"`

### 6. Race conditions
- Send two requests at nearly the same time (use DevTools copy as fetch)
- Does the server handle them properly or can you win a race?

### 7. Business logic flaws
- Can you use a feature in a way the developer didn't intend?
- *Like: dispatch --index 1 worked without the agent being registered* 

## Phase 3: Report Writing

When you find something:
1. Note the exact request (copy from DevTools → Copy as cURL)
2. Note the exact response
3. Write steps to reproduce (someone else should be able to follow them)
4. Explain the impact (what could an attacker do with this?)

## Tools from Chrome (No Install)

- DevTools (F12) — Network tab, Console, Sources
- Copy as cURL — export any request
- Edit and replay — right-click request → Copy → Copy as fetch, paste in console, modify
