/**
 * Locates a system Chrome/Edge install so the headless UI checks can run
 * without downloading a browser (CHROME_PATH overrides).
 */
const CHROME_CANDIDATES = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
];

export function resolveChrome() {
  return process.env.CHROME_PATH ?? CHROME_CANDIDATES[0];
}
