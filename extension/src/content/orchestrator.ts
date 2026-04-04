// Content script entry point — orchestrates field scanning and form filling.
// Field scanning is implemented in field-scanner.ts.

import { scanFields } from "./field-scanner.js";

console.debug("[JobCrawler] content script loaded", location.href);

// Expose scanFields on the module for use by other content-script modules.
export { scanFields };
