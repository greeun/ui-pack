#!/usr/bin/env node
// Compares the target app's gallery (/design) with the pack's gallery by computed style. Needs only Node 22 and Chrome, nothing to install.
// When the target app's global CSS (a rule that sets letter spacing on h1-h4, for example) leaks into pack components, it shows up here.
//
// Usage: node gallery-check.mjs <pack folder> <target gallery URL (e.g. http://localhost:3000/design)>
// The reference is the gallery in the pack viewer (<pack>/view/index.html). For every gallery card (titled by its h2) the elements
// inside are paired in order and their type, color, padding, radius and shadow values compared; each differing card is printed with
// its first difference. The exit code is 0 when no card differs.
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [packDir, targetUrl] = process.argv.slice(2);
if (!packDir || !targetUrl) {
  console.error("Usage: node gallery-check.mjs <pack folder> <target gallery URL>");
  process.exit(2);
}
const viewFile = path.resolve(packDir, "view", "index.html");
if (!fs.existsSync(viewFile)) {
  console.error(`No pack viewer: ${viewFile} (build it first with build-view.py)`);
  process.exit(2);
}
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const port = 19000 + Math.floor(Math.random() * 900);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "ui-pack-gallery-"));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "--no-first-run", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let ws, seq = 0;
const pending = new Map();
const send = (method, params = {}) => new Promise((r) => { const id = ++seq; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const evaluate = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;

// Collects a list of [tag, style values] per card. Values that depend on the outer width, such as width and height, are left out.
const COLLECT = `(() => {
  const props = ["color","backgroundColor","fontFamily","fontSize","fontWeight","letterSpacing","lineHeight","borderTopLeftRadius","boxShadow","paddingTop","paddingLeft","borderTopWidth","borderTopStyle","borderTopColor","textDecorationLine","opacity"];
  const out = {};
  for (const h of document.querySelectorAll("section h2")) {
    const card = h.closest("section");
    if (!card || card.classList.contains("v-section") || card.closest("#catalog, #guide, #overview, #files")) continue;
    const els = [card, ...card.querySelectorAll("*")].filter((e) => !e.closest("svg") || e.tagName === "svg");
    // The color of a zero-width border is not visible, so it is not compared
    out[h.textContent.trim()] = els.map((e) => { const s = getComputedStyle(e); const none = s.borderTopWidth === "0px" || s.borderTopStyle === "none"; return e.tagName.toLowerCase() + "|" + props.map((p) => (none && p === "borderTopColor" ? "-" : s[p])).join("|"); });
  }
  return out;
})()`;

async function read(url, scheme) {
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: scheme }, { name: "prefers-reduced-motion", value: "reduce" }] });
  await send("Page.navigate", { url });
  await sleep(3000);
  await evaluate("document.fonts.ready.then(() => true)");
  await evaluate(`(() => { try { localStorage.clear(); } catch {} document.documentElement.removeAttribute("data-theme"); return true; })()`);
  await sleep(300);
  return evaluate(COLLECT);
}

try {
  let targets;
  for (let i = 0; i < 50; i++) {
    try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); break; } catch { await sleep(200); }
  }
  ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r, { once: true }));
  ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  const names = ["color","background","font","size","weight","letter-spacing","line-height","radius","shadow","padding-top","padding-left","border-width","border-style","border-color","decoration","opacity"];
  let bad = 0, total = 0;
  for (const scheme of ["light", "dark"]) {
    const ref = await read(pathToFileURL(viewFile).href, scheme);
    const got = await read(targetUrl, scheme);
    if (!got || !Object.keys(got).length) {
      console.error(`No gallery card found in the target gallery: ${targetUrl}\nThe server is returning an error (500) or the URL is wrong. Restart the dev server and run this again.`);
      process.exitCode = 2;
      break;
    }
    for (const [title, refEls] of Object.entries(ref)) {
      total++;
      const gotEls = got[title];
      if (!gotEls) { bad++; console.log(`[${scheme}] differs  ${title}: the target gallery has no such card`); continue; }
      let diff = null;
      for (let i = 0; i < Math.max(refEls.length, gotEls.length) && !diff; i++) {
        const a = (refEls[i] ?? "").split("|"), b = (gotEls[i] ?? "").split("|");
        for (let k = 0; k < Math.max(a.length, b.length); k++) {
          if (a[k] !== b[k]) { diff = k === 0 ? `element ${i}: ${a[0]} → ${b[0]}` : `element ${i} (${a[0]}) ${names[k - 1]}: ${a[k]} → ${b[k]}`; break; }
        }
      }
      if (diff) { bad++; console.log(`[${scheme}] differs  ${title}: ${diff}`); }
    }
  }
  if (process.exitCode !== 2) {
    console.log(`${total} gallery cards (light + dark): ${bad} differ`);
    process.exitCode = bad ? 1 : 0;
  }
} finally {
  ws?.close();
  chrome.kill();
  await sleep(300);
  fs.rmSync(profile, { recursive: true, force: true });
}
