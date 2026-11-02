#!/usr/bin/env node
// npx fast-ios-device-test                     install, or upgrade (copied to ~/.local/share/fast-ios-device-test)
// npx fast-ios-device-test --check [--device <name>]   what is there and what is missing
// npx fast-ios-device-test --uninstall         remove the tool (caches and build output stay)
// npx fast-ios-device-test clean [--project <root>] [--maps] [--yes]   delete caches and test builds
"use strict";
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");
const args = process.argv.slice(2);
if (process.platform !== "darwin") {
  console.error("fast-ios-device-test needs macOS with Xcode.");
  process.exit(1);
}
if (args.includes("--link")) {
  console.error("--link would point at npx's temporary folder; clone the repo and run install.sh --link instead.");
  process.exit(2);
}
const command = args[0] === "clean"
  ? ["python3", [path.join(root, "scripts", "fast_ui_clean.py"), ...args.slice(1)]]
  : ["bash", [path.join(root, "install.sh"), ...args]];
const result = spawnSync(command[0], command[1], { stdio: "inherit" });
process.exit(result.status === null ? 1 : result.status);
