const esbuild = require("esbuild");

const watch = process.argv.includes("--watch");

const entryPoints = [
  { in: "src/background/service-worker.ts", out: "service-worker" },
  { in: "src/content/orchestrator.ts", out: "content" },
  { in: "src/popup/popup.ts", out: "popup" },
  { in: "src/overlay/overlay.ts", out: "overlay" },
];

const buildOptions = {
  entryPoints: entryPoints.map((e) => e.in),
  bundle: true,
  outdir: "dist",
  outExtension: { ".js": ".js" },
  entryNames: (entry) => {
    const match = entryPoints.find((e) => e.in === entry.relativePath);
    return match ? match.out : "[name]";
  },
  platform: "browser",
  target: "es2020",
  format: "esm",
  sourcemap: true,
  logLevel: "info",
};

// Resolve entry → output name mapping manually
const resolvedOptions = {
  bundle: true,
  outdir: "dist",
  platform: "browser",
  target: "es2020",
  format: "esm",
  sourcemap: true,
  logLevel: "info",
  entryPoints: {
    "service-worker": "src/background/service-worker.ts",
    content: "src/content/orchestrator.ts",
    popup: "src/popup/popup.ts",
    overlay: "src/overlay/overlay.ts",
  },
};

if (watch) {
  esbuild.context(resolvedOptions).then((ctx) => {
    ctx.watch();
    console.log("Watching for changes...");
  });
} else {
  esbuild.build(resolvedOptions).catch(() => process.exit(1));
}
