/**
 * Headless smoke test for the VISORA web UI.
 *
 * Launches the system Chrome (no browser download), walks every route,
 * collects console/page errors and writes screenshots to web/.smoke/.
 *
 *   node scripts/smoke.mjs [baseUrl]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";
import { resolveChrome } from "./chrome.mjs";

const BASE_URL = process.argv[2] ?? "http://localhost:5173";

const ROUTES = [
  ["overview", "/"],
  ["datasets", "/datasets"],
  ["analytics", "/analytics"],
  ["insights", "/insights"],
  ["reports", "/reports"],
  ["settings", "/settings"],
];

const outDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", ".smoke");

function findChrome() {
  return resolveChrome();
}

async function settle(page, ms = 900) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  await mkdir(outDir, { recursive: true });

  const browser = await puppeteer.launch({
    executablePath: findChrome(),
    headless: true,
    args: ["--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--window-size=1440,900"],
  });

  const problems = [];
  const report = [];

  try {
    for (const [name, route] of ROUTES) {
      const page = await browser.newPage();
      await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });

      const consoleErrors = [];
      page.on("console", (message) => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });
      page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));
      page.on("requestfailed", (request) =>
        consoleErrors.push(`requestfailed: ${request.url()} (${request.failure()?.errorText})`),
      );

      await page.goto(`${BASE_URL}${route}`, { waitUntil: "networkidle2", timeout: 45000 });
      await settle(page, 1500);

      const info = await page.evaluate(() => {
        const text = document.body.innerText ?? "";
        const headings = [...document.querySelectorAll("h1, h2, [data-page-title]")].map((n) =>
          (n.textContent ?? "").trim(),
        );
        return {
          title: document.title,
          readyState: document.readyState,
          rootChildren: document.querySelector("#root")?.children.length ?? 0,
          headings: headings.filter(Boolean).slice(0, 6),
          textLength: text.length,
          hasRawError:
            /Traceback \(most recent call last\)|Error: |TypeError|Cannot read prop/i.test(text),
          snippet: text.replace(/\s+/g, " ").slice(0, 420),
        };
      });

      await page.screenshot({ path: path.join(outDir, `${name}.png`), fullPage: false });

      // Light theme capture for the overview page too.
      if (name === "overview") {
        await page.evaluate(() => {
          document.documentElement.dataset.theme = "light";
        });
        await settle(page, 600);
        await page.screenshot({ path: path.join(outDir, "overview-light.png") });
      }

      const relevantErrors = consoleErrors.filter(
        (line) => !line.includes("favicon") && !line.includes("Download the React DevTools"),
      );

      report.push({ name, route, ...info, consoleErrors: relevantErrors });
      if (relevantErrors.length > 0 || info.rootChildren === 0 || info.hasRawError) {
        problems.push({ name, consoleErrors: relevantErrors, ...info });
      }

      await page.close();
    }
  } finally {
    await browser.close();
  }

  await writeFile(path.join(outDir, "report.json"), JSON.stringify(report, null, 2));

  for (const entry of report) {
    console.log(`\n[${entry.name}] ${entry.route}`);
    console.log(`  rootChildren=${entry.rootChildren} textLength=${entry.textLength}`);
    console.log(`  headings=${JSON.stringify(entry.headings)}`);
    if (entry.consoleErrors.length > 0) {
      console.log(`  console errors:`);
      for (const line of entry.consoleErrors) console.log(`    - ${line}`);
    }
    console.log(`  snippet: ${entry.snippet}`);
  }

  console.log(`\nScreenshots + report written to ${outDir}`);
  if (problems.length > 0) {
    console.error(`\nSMOKE FAILED for: ${problems.map((p) => p.name).join(", ")}`);
    process.exitCode = 1;
  } else {
    console.log("\nSMOKE PASSED: all routes rendered with no page errors.");
  }
}

main().catch((error) => {
  console.error("smoke run crashed:", error);
  process.exitCode = 1;
});
