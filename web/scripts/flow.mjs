/**
 * End-to-end UI flow test: upload → progress/success → analyze → analytics →
 * delete confirmation → cleanup + state restore.
 *
 * Uses the system Chrome via puppeteer-core against the Vite dev server
 * (which proxies /api to the FastAPI bridge).
 *
 *   node scripts/flow.mjs [baseUrl]
 */
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";
import { resolveChrome } from "./chrome.mjs";

const BASE_URL = process.argv[2] ?? "http://localhost:5173";
const API = `${BASE_URL}/api/v1`;
const outDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", ".smoke");

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

async function api(pathname, init) {
  const response = await fetch(`${API}${pathname}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${pathname} → ${response.status} ${text.slice(0, 300)}`);
  }
  return body;
}

const SAMPLE_ROWS = (() => {
  const regions = ["North", "South", "East", "West"];
  const lines = ["date,region,units,revenue"];
  let units = 40;
  let revenue = 4200;
  for (let day = 0; day < 45; day += 1) {
    const date = new Date(Date.UTC(2024, 4, 1 + day));
    const drift = Math.round(Math.sin(day / 5) * 9 + day / 4);
    units = Math.max(6, units + drift);
    revenue = Math.max(500, revenue + drift * 95);
    lines.push(
      `${date.toISOString().slice(0, 10)},${regions[day % regions.length]},${units},${revenue}`,
    );
  }
  return lines.join("\n");
})();

async function main() {
  await mkdirSafe(outDir);
  const workDir = await mkdtemp(path.join(tmpdir(), "visora-flow-"));
  const stem = `flow_${Date.now().toString(36)}`;
  const csvPath = path.join(workDir, `${stem}.csv`);
  await writeFile(csvPath, SAMPLE_ROWS, "utf8");

  const initial = await api("/datasets");
  const initialCount = initial.datasets.length;

  const browser = await puppeteer.launch({
    executablePath: resolveChrome(),
    headless: true,
    args: ["--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--window-size=1440,900"],
  });

  const consoleErrors = [];
  let tempId = null;

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));

    // 1. Datasets page loads
    await page.goto(`${BASE_URL}/datasets`, { waitUntil: "networkidle2", timeout: 45000 });
    await page.waitForSelector("input[type=file]", { timeout: 15000 });
    check("datasets page renders dropzone", true);

    // 2. Upload with phase capture (slow the upload POST so progress UI is observable)
    await page.setRequestInterception(true);
    page.on("request", (request) => {
      const isUpload =
        request.method() === "POST" && request.url().endsWith("/api/v1/datasets");
      if (isUpload) {
        setTimeout(() => {
          request.continue().catch(() => {});
        }, 1200);
      } else {
        request.continue().catch(() => {});
      }
    });

    const seenPhases = new Set();
    const watcher = setInterval(async () => {
      try {
        const text = await page.evaluate(() => document.body.innerText);
        for (const phase of ["Uploading", "Processing", "Dataset ready", "failed", "retry"]) {
          if (text.includes(phase) && !seenPhases.has(phase)) {
            seenPhases.add(phase);
            if (phase !== "failed" && phase !== "retry") {
              await page.screenshot({
                path: path.join(outDir, `flow-phase-${phase.toLowerCase().replace(/\s+/g, "-")}.png`),
              });
            }
          }
        }
      } catch {
        /* page may be mid-navigation */
      }
    }, 80);

    const input = await page.$("input[type=file]");
    await input.uploadFile(csvPath);

    try {
      await page.waitForFunction(
        () => document.body.innerText.includes("Dataset ready"),
        { timeout: 60000 },
      );
      await new Promise((resolve) => setTimeout(resolve, 400));
      check("upload reaches success phase", true, `phases seen: ${[...seenPhases].join(", ") || "none"}`);
    } catch {
      const text = await page.evaluate(() => document.body.innerText.slice(0, 600));
      check("upload reaches success phase", false, text.replace(/\s+/g, " "));
      await page.screenshot({ path: path.join(outDir, "flow-upload-failed.png") });
      return;
    } finally {
      clearInterval(watcher);
    }

    // Upload success routes to the new dataset's detail page.
    try {
      await page.waitForFunction(
        () => /^\/datasets\/.+/.test(window.location.pathname),
        { timeout: 30000 },
      );
    } catch {
      const text = await page.evaluate(() => document.body.innerText);
      await page.screenshot({ path: path.join(outDir, "flow-row-missing.png") });
      check("upload opens dataset detail page", false, text.replace(/\s+/g, " ").slice(0, 700));
      throw new Error("detail navigation failed");
    }
    await new Promise((resolve) => setTimeout(resolve, 900));
    await page.screenshot({ path: path.join(outDir, "flow-01-detail.png") });
    check("upload opens dataset detail page", true);

    const after = await api("/datasets");
    const temp = after.datasets.find((d) => d.fileName === `${stem}.csv`);
    check("dataset registered", Boolean(temp), temp ? `id=${temp.id}` : "not found");
    if (!temp) return;
    tempId = temp.id;
    check(
      "dataset profiled on ingest",
      temp.rowCount > 0 && temp.columnCount === 4,
      `rows=${temp.rowCount} cols=${temp.columnCount}`,
    );

    const detailText = await page.evaluate(() => document.body.innerText);
    check(
      "detail page shows data profile",
      /MISSING VALUES|DUPLICATE ROWS|COLUMN HEALTH/.test(detailText),
      detailText.replace(/\s+/g, " ").slice(0, 150),
    );

    // 3. Run the unified analysis from the detail page (routes to Analytics)
    const clicked = await page.evaluate(() => {
      const button = [...document.querySelectorAll("button")].find((b) =>
        /Analyze dataset|Re-run analysis/.test(b.textContent),
      );
      if (!button) return false;
      button.click();
      return true;
    });
    check("analyze action is clickable", clicked);

    const routed = await page
      .waitForFunction(() => window.location.pathname === "/analytics", { timeout: 120000 })
      .then(() => true)
      .catch(() => false);
    check("analysis routes to analytics", routed);

    await page
      .waitForFunction(
        () => /Trend|Contribution|Findings/.test(document.body.innerText),
        { timeout: 60000 },
      )
      .catch(() => {});
    await new Promise((resolve) => setTimeout(resolve, 1800));
    const analyticsText = await page.evaluate(() => document.body.innerText);
    check(
      "analytics renders metrics",
      /UNITS|REVENUE|Trend/i.test(analyticsText),
      analyticsText.replace(/\s+/g, " ").slice(0, 180),
    );
    check("analytics targets uploaded dataset", analyticsText.includes(stem));
    await page.screenshot({ path: path.join(outDir, "flow-02-analytics.png") });

    // 4. The unified snapshot now points at the new dataset
    const current = await api("/reports/current");
    check(
      "unified snapshot updated",
      current?.dataset?.dataset_id === tempId,
      `snapshot dataset=${current?.dataset?.dataset_id}`,
    );

    // 5. Insights page renders the AI interpretation of the new analysis
    await page.goto(`${BASE_URL}/insights`, { waitUntil: "networkidle2", timeout: 45000 });
    await page.waitForFunction(() => document.body.innerText.includes("SUMMARY"), { timeout: 30000 });
    await new Promise((resolve) => setTimeout(resolve, 900));
    const insightsText = await page.evaluate(() => document.body.innerText);
    check("insights renders summary", true);
    check("insights reflects uploaded dataset", insightsText.includes(stem));
    await page.screenshot({ path: path.join(outDir, "flow-03-insights.png") });

    // 7. Delete confirmation dialog (screenshot, then confirm)
    await page.goto(`${BASE_URL}/datasets`, { waitUntil: "networkidle2", timeout: 45000 });
    await page.waitForFunction(
      (name) => document.body.innerText.includes(name),
      { timeout: 20000 },
      `${stem}.csv`,
    );
    await page.click(`button[aria-label="Delete ${stem}"]`);
    await page.waitForFunction(
      () => document.body.innerText.includes("Delete dataset"),
      { timeout: 15000 },
    );
    await new Promise((resolve) => setTimeout(resolve, 500));
    await page.screenshot({ path: path.join(outDir, "flow-05-delete-dialog.png") });
    check("delete confirmation dialog opens", true);

    // Cancel first — the dialog must dismiss without deleting anything.
    const cancelClicked = await page.evaluate(() => {
      const buttons = [...document.querySelectorAll("button")];
      const cancel = buttons.find((b) => b.textContent.trim() === "Cancel");
      if (!cancel) return false;
      cancel.click();
      return true;
    });
    await new Promise((resolve) => setTimeout(resolve, 600));
    const stillThere = (await api("/datasets")).datasets.some((d) => d.id === tempId);
    check("cancel keeps dataset", cancelClicked && stillThere);

    // Confirm for real.
    await page.click(`button[aria-label="Delete ${stem}"]`);
    await page.waitForFunction(() => document.body.innerText.includes("Delete dataset"), {
      timeout: 15000,
    });
    await page.evaluate(() => {
      const buttons = [...document.querySelectorAll("button")];
      const confirm = buttons.find((b) => b.textContent.trim() === "Delete dataset");
      confirm?.click();
    });
    await page.waitForFunction(
      (name) => !document.body.innerText.includes(name),
      { timeout: 30000 },
      `${stem}.csv`,
    );
    const finalList = await api("/datasets");
    check(
      "confirm deletes dataset",
      !finalList.datasets.some((d) => d.id === tempId),
      `count ${initialCount} → ${finalList.datasets.length}`,
    );
    await page.screenshot({ path: path.join(outDir, "flow-06-after-delete.png") });

    // 8. Restore: re-analyze the surviving dataset so the snapshot matches it again.
    const remaining = finalList.datasets.find((d) => d.status === "ready");
    if (remaining) {
      await api(`/datasets/${remaining.id}/analyze`, { method: "POST" });
      const restored = await api("/reports/current");
      check(
        "workspace snapshot restored",
        restored?.dataset?.dataset_id === remaining.id,
        `dataset=${remaining.id} snapshot=${restored?.dataset?.dataset_id}`,
      );
    } else {
      check("workspace snapshot restored", false, "no ready dataset left");
    }
  } finally {
    await browser.close();
    // Safety net: never leave the temp dataset behind.
    try {
      const list = await api("/datasets");
      for (const dataset of list.datasets) {
        if (dataset.fileName === `${stem}.csv`) {
          await api(`/datasets/${dataset.id}`, { method: "DELETE" });
          console.log(`cleanup: removed leftover ${dataset.id}`);
        }
      }
    } catch (error) {
      console.warn("cleanup failed:", error.message);
    }
    await rm(workDir, { recursive: true, force: true }).catch(() => {});
  }

  const relevantErrors = consoleErrors.filter(
    (line) => !line.includes("favicon") && !line.includes("Download the React DevTools"),
  );
  check("no console/page errors during flow", relevantErrors.length === 0, relevantErrors.join(" | "));

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  if (failed.length > 0) {
    console.error(`FLOW FAILED: ${failed.map((f) => f.name).join(", ")}`);
    process.exitCode = 1;
  } else {
    console.log("FLOW PASSED");
  }
}

async function mkdirSafe(dir) {
  const { mkdir } = await import("node:fs/promises");
  await mkdir(dir, { recursive: true });
}

main().catch((error) => {
  console.error("flow run crashed:", error);
  process.exitCode = 1;
});
