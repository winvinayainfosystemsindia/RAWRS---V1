import { chromium } from "playwright";
import fs from "node:fs";

const SHOT_DIR = "C:/RAWRS - WINVINAYA/frontend/.verify-shots";
fs.mkdirSync(SHOT_DIR, { recursive: true });

const errors = [];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
page.on("console", (msg) => {
  if (msg.type() === "error") errors.push(msg.text());
});
page.on("pageerror", (err) => errors.push(String(err)));

async function shot(name) {
  await page.screenshot({ path: `${SHOT_DIR}/${name}.png`, fullPage: true });
  console.log("screenshot:", name);
}

console.log("--- nav to upload page ---");
await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
await page.waitForSelector("text=Remediate a PDF");
await page.waitForSelector("text=Recent documents");
await shot("01-upload-page");

const recentLinks = await page.locator('a[href^="/documents/"]').count();
console.log("recent document links found:", recentLinks);

console.log("--- open first recent document ---");
await page.locator('a[href^="/documents/"]').first().click();
await page.waitForURL(/\/documents\//);
await page.waitForSelector("text=Complete", { timeout: 15000 });
await shot("02-document-overview");

console.log("--- download bar present ---");
const downloadLinks = await page.locator("text=Markdown (.md)").count();
console.log("markdown download link present:", downloadLinks > 0);

console.log("--- click Validation tab ---");
await page.getByRole("tab", { name: /Validation/ }).click();
await shot("03-validation-tab");

console.log("--- click Images tab ---");
await page.getByRole("tab", { name: /Images/ }).click();
await page.waitForTimeout(500);
await shot("04-images-tab");

console.log("--- click Footnotes tab ---");
await page.getByRole("tab", { name: /Footnotes/ }).click();
await shot("05-footnotes-tab");

console.log("--- click OCR tab ---");
await page.getByRole("tab", { name: /OCR/ }).click();
await shot("06-ocr-tab");

console.log("--- click Markdown tab ---");
await page.getByRole("tab", { name: /Markdown/ }).click();
await page.waitForTimeout(500);
await shot("07-markdown-tab");

const markdownText = await page.locator('[role="tabpanel"]:not([hidden])').innerText();
console.log("markdown tab panel text length:", markdownText.length);

await browser.close();

console.log("\n=== console/page errors captured ===");
console.log(errors.length === 0 ? "none" : errors.join("\n"));
