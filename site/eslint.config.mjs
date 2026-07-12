import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslint10ReactVersionCompatibility = {
  settings: {
    react: {
      version: "19.2.7",
    },
  },
};

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  eslint10ReactVersionCompatibility,
  globalIgnores([".next/**", "out/**", "next-env.d.ts"]),
]);
