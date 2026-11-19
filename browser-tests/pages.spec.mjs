// This repo's own browser check (the shared specs are in shared/browser-tests): every page loads with no console
// error, no uncaught exception, no import-map specifier left unresolved, and every script served as JavaScript.
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

const manifest = JSON.parse(readFileSync(new URL("../surveyjs-integration.json", import.meta.url), "utf8"));
const pages = ["/", "/claim", "/examples/server-pdf/loading", "/examples/creator-load-save?form",
  "/examples/creator-uploads?form", ...manifest.steps.map((step) => step.page)];

for (const path of pages) {
  test(`${path} loads without console errors`, async ({ page }) => {
    const problems = [];
    // The browser asks for /favicon.ico on its own; the pages declare no icon (as in the reference)
    page.on("console", (message) => {
      if (message.type() === "error" && !message.location().url.endsWith("/favicon.ico")) problems.push(`console: ${message.text()} (${message.location().url})`);
    });
    page.on("pageerror", (error) => problems.push(`exception: ${error.message}`));
    page.on("response", (response) => {
      const url = new URL(response.url());
      if (/\.m?js$/.test(url.pathname) && response.ok()) {
        const type = (response.headers()["content-type"] || "").split(";")[0].trim();
        if (!["text/javascript", "application/javascript"].includes(type)) problems.push(`${url.pathname} served as ${type}`);
      }
    });
    const answer = await page.goto(path, { waitUntil: "networkidle" });
    expect(answer.status(), path).toBe(200);
    await page.waitForTimeout(500);   // modules that report late
    expect(problems, path).toEqual([]);
  });
}
