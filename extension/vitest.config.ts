import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    environmentOptions: {
      jsdom: {
        url: "https://www.linkedin.com/",
      },
    },
    include: ["tests/**/*.ts"],
    exclude: ["tests/test-setup.ts"],
  },
});
