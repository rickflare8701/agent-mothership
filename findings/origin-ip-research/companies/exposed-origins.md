# Exposed Origin IPs Behind Cloudflare

## Confirmed Exposed (Respond to Direct HTTPS)

| # | Company | Domain | Origin IP | HTTP Status | Notes |
|---|---------|--------|-----------|-------------|-------|
| 1 | Anthropic | api.anthropic.com | 160.79.104.10 | 302 | Express.js, AS399358 |
| 2 | Cohere | cohere.com | 76.76.21.21 | 200 | 687KB response |
| 3 | Stability AI | stability.ai | 198.49.23.145 | 200 | Squarespace server |
| 4 | Scale AI | scale.com | 76.76.21.98 | 200 | 631KB response |
| 5 | Supabase | supabase.com | 216.150.1.193 | 200 | 386KB response |
| 6 | Railway | railway.app | 34.107.141.139 | 200 | 336B response |
| 7 | Render | render.com | 216.24.57.1 | 200 | 369KB response |
| 8 | Fly.io | fly.io | 37.16.18.81 | 200 | 202KB response |
| 9 | Deno | deno.com | 69.67.170.170 | 200 | 211KB response |
| 10 | Notion | notion.so | 208.103.161.1 | 301 | Redirect |
| 11 | Dropbox | dropbox.com | 162.125.248.18 | 301 | Redirect |
| 12 | Linode | linode.com | 23.212.251.138 | 301 | Redirect |
| 13 | Vultr | vultr.com | 108.61.13.174 | 301 | Redirect |

## Scanned (Not Exposed / Cloudflare)

| Company | Domain | IP | Status |
|---------|--------|-----|--------|
| OpenAI | openai.com | Cloudflare | Protected |
| Midjourney | midjourney.com | 34.67.5.219 | No response |
| Figma | figma.com | 18.160.41.10 | Fastly CDN |
| Canva | canva.com | 18.165.83.61 | Fastly CDN |
| Airtable | airtable.com | 18.165.98.55 | Fastly CDN |
| GitHub | github.com | 140.82.113.3 | GitHub own IP |
| Stripe | stripe.com | 198.202.176.41 | Protected |
| Shopify | shopify.com | 23.227.38.33 | Shopify CDN |
| Twilio | twilio.com | 52.6.206.82 | AWS |
| SendGrid | sendgrid.com | 54.243.224.74 | AWS |
| Okta | okta.com | 3.171.100.12 | AWS |
| Netlify | netlify.com | 3.33.186.135 | AWS |
| Hugging Face | huggingface.co | 3.167.112.38 | CloudFront |

## Attack Vectors for Exposed Origins

1. **Direct API access** - Bypass Cloudflare WAF/rate-limiting
2. **SSRF** - Test redirect_uri with internal IPs
3. **Auth bypass** - Test without API keys
4. **Endpoint enumeration** - Find /api, /admin, /debug, /.env
5. **Error verbosity** - Compare error messages vs Cloudflare-proxied
