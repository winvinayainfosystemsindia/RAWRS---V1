const nextJest = require("next/jest");

// next/jest wires up SWC transform + CSS/asset mocking automatically from
// this app's own next.config.ts and tsconfig.json (including the "@/*"
// path alias every component already imports through) — no hand-rolled
// ts-jest/babel config needed.
const createJestConfig = nextJest({ dir: "./" });

/** @type {import('jest').Config} */
const customJestConfig = {
  testEnvironment: "jest-environment-jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
};

module.exports = createJestConfig(customJestConfig);
