const esbuild = require("esbuild");

const watch = process.argv.includes("--watch");

// ESM — service worker and popup-context scripts (need module semantics)
const esmOptions = {
  bundle: true,
  outdir: "dist",
  platform: "browser",
  target: "es2020",
  format: "esm",
  sourcemap: true,
  logLevel: "info",
  entryPoints: {
    "service-worker": "src/background/service-worker.ts",
    popup: "src/popup/popup.ts",
    overlay: "src/overlay/overlay.ts",
    checkout: "src/checkout/checkout.ts",
    offscreen: "src/offscreen/offscreen.ts",
  },
  define: {
    API_BASE_URL: JSON.stringify(
      process.env.API_URL || "http://localhost:8000"
    ),
  },
};

// IIFE — content scripts injected as classic scripts (no top-level export allowed)
const iifeOptions = {
  bundle: true,
  outdir: "dist",
  platform: "browser",
  target: "es2020",
  format: "iife",
  sourcemap: true,
  logLevel: "info",
  entryPoints: {
    content: "src/content/orchestrator.ts",
    "content/job-page-scraper": "src/content/job-page-scraper.ts",
  },
  define: {
    API_BASE_URL: JSON.stringify(
      process.env.API_URL || "http://localhost:8000"
    ),
  },
};

if (watch) {
  Promise.all([
    esbuild.context(esmOptions).then((ctx) => ctx.watch()),
    esbuild.context(iifeOptions).then((ctx) => ctx.watch()),
  ]).then(() => console.log("Watching for changes..."));
} else {
  Promise.all([
    esbuild.build(esmOptions),
    esbuild.build(iifeOptions),
  ]).catch(() => process.exit(1));
}
