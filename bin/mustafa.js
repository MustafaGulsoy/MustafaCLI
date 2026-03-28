#!/usr/bin/env node
const { spawn } = require("child_process");
const path = require("path");

const projectDir = path.resolve(__dirname, "..");
const venvPython = process.platform === "win32"
  ? path.join(projectDir, "venv", "Scripts", "python.exe")
  : path.join(projectDir, "venv", "bin", "python");

const args = process.argv.slice(2);
const child = spawn(venvPython, ["-m", "src.cli", ...args], {
  cwd: process.cwd(),
  stdio: "inherit",
  env: { ...process.env, PYTHONPATH: projectDir },
});

child.on("exit", (code) => process.exit(code ?? 0));
