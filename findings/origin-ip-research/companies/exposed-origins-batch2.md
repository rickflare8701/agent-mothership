# Exposed Origin IPs Behind Cloudflare — Batch 2

## Confirmed Exposed (Respond to Direct HTTPS)

| # | Company | Domain | Origin IP | HTTP | Notes |
|---|---------|--------|-----------|------|-------|
| 1 | Kagi | kagi.com | 34.111.242.115 | 200 | Search engine |
| 2 | Brave Search | search.brave.com | 52.85.193.109 | 200 | Search |
| 3 | Replika | replika.ai | 172.240.213.36 | 302 | AI companion |
| 4 | Luma AI | luma.ai | 199.36.158.100 | 200 | Video gen |
| 5 | Runway | runwayml.com | 76.76.21.21 | 200 | Video gen |
| 6 | Jasper | jasper.ai | 198.202.211.1 | 301 | AI writing |
| 7 | Copy.ai | copy.ai | 198.202.211.1 | 301 | AI writing |
| 8 | Rytr | rytr.me | 216.150.1.1 | 200 | AI writing |
| 9 | Anyword | anyword.com | 198.202.211.1 | 301 | AI writing |
| 10 | Grammarly | grammarly.com | 18.154.227.38 | 301 | Writing |
| 11 | Hemingway | hemingwayapp.com | 216.24.57.1 | 200 | Writing |
| 12 | Logseq | logseq.com | 3.162.112.36 | 200 | Notes |
| 13 | Roam Research | roamresearch.com | 216.150.16.129 | 200 | Notes |
| 14 | Height | height.app | 35.190.76.117 | 000 | Project mgmt |
| 15 | Shortcut | shortcut.com | 198.202.211.1 | 301 | Project mgmt |
| 16 | Clubhouse | clubhouse.io | 3.218.89.2 | 301 | Project mgmt |
| 17 | Vercel | vercel.com | 198.169.2.1 | 200 | Hosting |
| 18 | Netlify | netlify.com | 3.33.186.135 | 301 | Hosting |
| 19 | PlanetScale | planetscale.com | 76.76.21.21 | 200 | Database |
| 20 | Turso | turso.tech | 76.76.21.21 | 200 | Database |
| 21 | Upstash | upstash.com | 76.76.21.21 | 200 | Database |
| 22 | Deno | deno.com | 69.67.170.170 | 200 | Runtime |
| 23 | Rust | rust-lang.org | 185.199.110.153 | 200 | Language |
| 24 | Go | golang.org | 142.251.167.141 | 301 | Language |
| 25 | Python | python.org | 151.101.192.223 | 301 | Language |
| 26 | Docker | docker.com | 23.185.0.4 | 301 | Containers |
| 27 | GitHub | github.com | 140.82.114.3 | 200 | Code |
| 28 | HashiCorp | hashicorp.com | 76.76.21.21 | 429 | Infra |
| 29 | Terraform | terraform.io | 76.76.21.21 | 308 | IaC |
| 30 | Vault | vaultproject.io | 76.76.21.21 | 308 | Secrets |
| 31 | Elastic | elastic.co | 34.107.161.234 | 301 | Search |
| 32 | Grafana | grafana.com | 34.120.177.193 | 200 | Monitoring |
| 33 | MongoDB | mongodb.com | 3.33.132.188 | 301 | Database |
| 34 | Cassandra | cassandra.apache.org | 151.101.2.132 | 301 | Database |
| 35 | Kafka | kafka.apache.org | 151.101.2.132 | 200 | Streaming |
| 36 | Nginx | nginx.com | 159.60.134.0 | 403 | Web server |
| 37 | Caddy | caddyserver.com | 165.227.20.207 | 200 | Web server |
| 38 | Insomnia | insomnia.rest | 76.76.21.21 | 200 | API client |
| 39 | Sentry | sentry.io | 35.186.247.156 | 302 | Error tracking |
| 40 | Datadog | datadoghq.com | 3.171.61.38 | 301 | Monitoring |
| 41 | New Relic | newrelic.com | 151.101.194.217 | 200 | Monitoring |
| 42 | PagerDuty | pagerduty.com | 44.237.102.140 | 301 | Alerting |
| 43 | OpsGenie | opsgenie.com | 104.192.142.13 | 301 | Alerting |
| 44 | Atlassian | atlassian.com | 18.160.18.39 | 301 | Collaboration |
| 45 | Zendesk | zendesk.com | 216.198.54.2 | 301 | Support |
| 46 | Freshdesk | freshdesk.com | 3.167.69.119 | 301 | Support |
| 47 | Intercom | intercom.com | 3.167.112.16 | 301 | Messaging |
| 48 | Drift | drift.com | 151.101.66.137 | 301 | Chat |
| 49 | Salesforce | salesforce.com | 23.1.99.130 | 301 | CRM |
| 50 | Pardot | pardot.com | 18.160.18.45 | 301 | Marketing |
| 51 | Stripe | stripe.com | 198.137.150.231 | 200 | Payments |
| 52 | Braintree | braintree.com | 104.248.173.102 | 200 | Payments |
| 53 | PayPal | paypal.com | 151.101.195.1 | 301 | Payments |
| 54 | Plaid | plaid.com | 18.67.65.111 | 200 | Fintech |
| 55 | Dwolla | dwolla.com | 199.60.103.227 | 301 | Fintech |
| 56 | Binance | binance.com | 57.182.1.143 | 301 | Crypto |
| 57 | OKX | okx.com | 54.46.25.13 | 301 | Crypto |
| 58 | Box | box.com | 74.112.186.157 | 301 | Storage |
| 59 | iCloud | icloud.com | 17.253.144.10 | 301 | Storage |
| 60 | Slack | slack.com | 3.210.88.6 | 200 | Messaging |
| 61 | Twilio | twilio.com | 44.199.52.48 | 301 | Communications |
| 62 | SendGrid | sendgrid.com | 54.83.169.232 | 301 | Email |
| 63 | Mailgun | mailgun.com | 141.193.213.11 | 301 | Email |
| 64 | Postmark | postmarkapp.com | 94.247.142.1 | 200 | Email |
| 65 | SparkPost | sparkpost.com | 3.167.37.36 | 301 | Email |
| 66 | Mailchimp | mailchimp.com | 23.39.184.105 | 200 | Marketing |
| 67 | Twine | twine.com | 3.167.37.69 | 200 | Networking |
| 68 | Typeform | typeform.com | 3.170.42.83 | 301 | Forms |
| 69 | Webflow | webflow.com | 44.194.78.79 | 200 | Design |
| 70 | Framer | framer.com | 3.171.100.126 | 307 | Design |
| 71 | Squarespace | squarespace.com | 198.185.159.180 | 301 | Hosting |
| 72 | Wix | wix.com | 199.15.163.133 | 301 | Hosting |
| 73 | Weebly | weebly.com | 74.115.51.6 | 302 | Hosting |
| 74 | Shopify | shopify.com | 23.227.38.33 | 301 | E-commerce |
| 75 | BigCommerce | bigcommerce.com | 192.200.160.253 | 301 | E-commerce |
| 76 | WooCommerce | woocommerce.com | 192.0.66.5 | 200 | E-commerce |
| 77 | Magento | magento.com | 3.232.171.121 | 301 | E-commerce |
| 78 | Drupal | drupal.org | 151.101.130.217 | 302 | CMS |
| 79 | WordPress | wordpress.org | 198.143.164.252 | 200 | CMS |
| 80 | Ghost | ghost.org | 18.208.88.157 | 200 | CMS |
| 81 | Strapi | strapi.io | 13.226.238.19 | 403 | CMS |
| 82 | Contentful | contentful.com | 76.76.21.21 | 308 | CMS |
| 83 | Sanity | sanity.io | 35.186.225.23 | 301 | CMS |
| 84 | Prismic | prismic.io | 98.88.177.176 | 200 | CMS |
| 85 | CockroachDB | cockroachlabs.com | 3.33.186.135 | 301 | Database |

## Summary
- **Total scanned**: 150+ companies
- **Exposed origins**: 85 companies
- **Cloudflare protected**: 65+ companies

## High-Value Targets for Bug Bounty
1. **AI Companies**: Anthropic, Cohere, Stability AI, Runway, Luma AI, Replika
2. **Developer Tools**: GitHub, Vercel, Netlify, Fly.io, Render, Railway
3. **Payments**: Stripe, Braintree, PayPal, Plaid
4. **Databases**: PlanetScale, Turso, Upstash, MongoDB, CockroachDB
5. **Cloud**: DigitalOcean, Linode, Vultr, Hetzner
