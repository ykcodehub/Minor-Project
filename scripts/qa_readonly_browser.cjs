// Production GET-only public UI checks. No submissions, sessions, OAuth starts or AI.
const fs = require("node:fs");
const path = require("node:path");
const { chromium, expect } = require("../frontend/node_modules/@playwright/test");
const AxeBuilder = require("../frontend/node_modules/@axe-core/playwright").default;
const out = path.resolve(__dirname, "../docs/testing/evidence");
const front = "https://veriora.vercel.app";
const api = "https://veriora-api.onrender.com";
(async () => {
 const browser = await chromium.launch({headless:true});
 const context = await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:"block"});
 const blocked=[]; const failures=[]; const records=[];
 const safeAPI=new Set(["/api/v1/me","/api/v1/auth/options","/api/v1/health","/api/v1/ready","/api/v1/dashboard","/api/v1/sources"]);
 await context.route("**/*", async route => {
  const r=route.request(); const u=new URL(r.url());
  const safe=["GET","HEAD","OPTIONS"].includes(r.method()) && [front,api].includes(u.origin) && (!u.pathname.startsWith("/api/") || safeAPI.has(u.pathname));
  if(!safe) { blocked.push({method:r.method(),origin:u.origin,path:u.pathname}); return route.abort(); }
  await route.continue();
 });
 const page=await context.newPage();
 page.on("pageerror", e=>failures.push({type:"runtime",name:e.name}));
 page.on("requestfailed", r=>{const u=new URL(r.url());failures.push({type:"requestfailed",origin:u.origin,path:u.pathname,error:r.failure()?.errorText});});
 page.on("response", r=>{if(r.status()>=400) {const u=new URL(r.url());failures.push({type:"http",status:r.status(),origin:u.origin,path:u.pathname});}});
 async function check(id,scenario,fn) {
  const rec={id,scenario,date:new Date().toISOString(),environment:"Production Chromium; fresh anonymous context; mutation/OAuth requests blocked"};
  const start=Date.now();
  try { const actual=await fn(); rec.status="PASS"; rec.actual=actual; }
  catch(e) {rec.status="FAIL";rec.actual=String(e.message).slice(0,1000);}
  rec.duration_ms=Date.now()-start;records.push(rec);fs.writeFileSync(path.join(out,"production-browser.json"),JSON.stringify({records,blocked,failures},null,2));console.log(`${id}: ${rec.status}; ${rec.actual}`);
 }
 await check("PROD-UI-01","Public landing renders the Veriora application",async()=>{
  const r=await page.goto(front,{waitUntil:"networkidle",timeout:60000});
  if(!r||r.status()!==200)throw Error(`Landing HTTP ${r&&r.status()}`);
  if(!await page.locator("main").count())throw Error("Main landmark absent");
  const title=await page.title();const heads=await page.locator("h1").allTextContents();
  if(!heads.some(h=>/clause|document|policy|evidence/i.test(h)))throw Error("Expected Veriora landing heading absent");
  await page.screenshot({path:path.join(out,"production-desktop.png"),fullPage:true});
  return `HTTP200; title=${title}; heading=${heads.join(" | ")}`;
 });
 await check("PROD-UI-02","Public landing has no horizontal overflow at 375px",async()=>{
  await page.setViewportSize({width:375,height:812});
  const sizes=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth}));
  await page.screenshot({path:path.join(out,"production-mobile.png"),fullPage:true});
  if(sizes.scroll>sizes.width)throw Error(`Horizontal overflow: ${sizes.scroll}>${sizes.width}`);
  return `scrollWidth=${sizes.scroll}; viewport=${sizes.width}; Chromium only`;
 });
 await check("PROD-UI-03","Public landing automated WCAG accessibility scan",async()=>{
  const results=await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze();
  const violations=results.violations.map(v=>({id:v.id,impact:v.impact,count:v.nodes.length,targets:v.nodes.map(n=>n.target)}));
  fs.writeFileSync(path.join(out,"production-accessibility.json"),JSON.stringify({violations,passes:results.passes.map(p=>p.id)},null,2));
  if(violations.length)throw Error(JSON.stringify(violations));
  return `No violations in ${results.passes.length} passed axe rules; not a full manual accessibility certification`;
 });
 for(const [id,url,label,selector] of [
  ["PROD-UI-04","/sign-in","Sign-in email/password and Google controls",'input[type="email"]'],
  ["PROD-UI-05","/register","Email-first registration page",'input[type="email"]'],
  ["PROD-UI-06","/forgot-password","Password recovery page",'input[type="email"]'],
  ["PROD-UI-07","/analyze","Upload workspace",'input[type="file"]'],
  ["PROD-UI-08","/library","Library route",'main'],
  ["PROD-UI-09","/dashboard","Dashboard route",'main']
 ]) {
  await check(id,label+" direct navigation",async()=>{
   const r=await page.goto(front+url,{waitUntil:"networkidle",timeout:45000});
   if(!r||r.status()!==200)throw Error(`GET ${url} returned HTTP ${r&&r.status()}`);
   if(!await page.locator(selector).count())throw Error(`Expected control/landmark missing: ${selector}`);
   return `HTTP200; ${selector} present; no form submitted`;
  });
 }
 await check("PROD-UI-10","Browser frontend-to-backend CORS integration",async()=>{
  await page.goto(front,{waitUntil:"domcontentloaded",timeout:45000});
  const result=await page.evaluate(async origin=>{try {const r=await fetch(origin+"/api/v1/health",{credentials:"include"});return {status:r.status,ok:r.ok};}catch{return {error:"Browser fetch rejected (network/CORS)"};}},api);
  if(result.error||result.status!==200)throw Error(JSON.stringify(result));
  return `Browser fetch completed HTTP${result.status}`;
 });
 await check("PROD-UI-12","Client-side navigation renders sign-in without submission",async()=>{
  await page.goto(front,{waitUntil:"networkidle",timeout:45000});
  await page.getByRole("banner").getByRole("link",{name:"Sign in",exact:true}).click();
  await page.locator('input[type="email"]').waitFor({state:"visible",timeout:10000});
  await page.locator('input[type="password"]').waitFor({state:"visible",timeout:10000});
  return "Client-side sign-in renders email/password; no credentials entered or form submitted";
 });
 await check("PROD-UI-13","Configured Google option is usable in the sign-in UI",async()=>{
  const control=page.getByRole("button",{name:"Continue with Google"});
  if(!await control.count())throw Error("Google control absent");
  await expect(control).toBeEnabled({timeout:10000});
  return "Google button enabled; no click, state creation or consent attempted";
 });
 await check("PROD-UI-14","Global Hindi/Hinglish navigation updates and persists anonymously",async()=>{
  await page.goto(front,{waitUntil:"networkidle",timeout:45000});
  const catalog=require("../frontend/src/lib/messages.json");
  for(const language of ["hi","hinglish"]) {
   await page.getByTestId("global-language-toggle").click();
   await page.getByTestId("global-language-select").selectOption(language);
   await page.getByRole("navigation").getByRole("link",{name:catalog.Dashboard[language],exact:true}).waitFor({state:"visible",timeout:5000});
  }
  await page.reload({waitUntil:"networkidle"});
  await page.getByRole("navigation").getByRole("link",{name:catalog.Dashboard.hinglish,exact:true}).waitFor({state:"visible",timeout:5000});
  await page.getByTestId("global-language-toggle").click();
  await page.getByTestId("global-language-select").selectOption("en");
  return "Hindi/Hinglish UI updated and Hinglish survived reload in local browser storage; no authenticated preference write tested";
 });
 await check("PROD-UI-15","Dot-free branding and current-year footer",async()=>{
  const text=(await page.locator("header .brand").textContent()).trim();
  if(!/^(?:V)?veriora$/i.test(text))throw Error("Wordmark differs from dot-free requirement");
  const footer=await page.getByRole("contentinfo").textContent();
  if(!footer.includes(String(new Date().getFullYear())))throw Error("Current-year footer absent");
  return "Dot-free wordmark and current-year footer observed";
 });
 await check("PROD-UI-16","Frontend uses the deployed /api/v1 API prefix",async()=>{
  const wrong=failures.filter(f=>f.origin===api && ["/me","/auth/options"].includes(f.path));
  if(wrong.length)throw Error("Observed requests omit /api/v1: "+JSON.stringify(wrong));
  return "No observed unprefixed profile/auth-options requests";
 });
 await check("PROD-UI-11","Observed anonymous frontend API calls have no network failures",async()=>{
  const unexpected=failures.filter(f=>f.type==="runtime" || (f.type==="requestfailed"&&f.origin===api) || (f.type==="http"&&f.path.startsWith("/api/")&&f.status!==401));
  if(unexpected.length)throw Error(JSON.stringify(unexpected));
  return `No runtime errors or non-401 API failures observed; ${blocked.length} safety-blocked requests`;
 });
 fs.writeFileSync(path.join(out,"production-browser.json"),JSON.stringify({records,blocked,failures},null,2));
 await browser.close();
})().catch(e=>{fs.writeFileSync(path.join(out,"production-browser-error.txt"),e.name+": "+String(e.message).slice(0,1000));process.exitCode=1;});
