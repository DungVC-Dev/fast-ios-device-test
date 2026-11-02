#!/usr/bin/env node
// `npx fast-ios-device-test [--check [--device <name>]]`: runs install.sh from the package,
// which copies the tool to ~/.local/share/fast-ios-device-test (npx's own folder is temporary)
// and wires the skill, slash commands and launchers into Claude Code.
"use strict";
const { spawnSync } = require("child_process");
const path = require("path");

const args = process.argv.slice(2);
if (process.platform !== "darwin") {
  console.error("fast-ios-device-test needs macOS with Xcode.");
  process.exit(1);
}
if (args.includes("--link")) {
  console.error("--link would point at npx's temporary folder; clone the repo and run install.sh --link instead.");
  process.exit(2);
}
const script = path.join(__dirname, "..", "install.sh");
const result = spawnSync("bash", [script, ...args], { stdio: "inherit" });
process.exit(result.status === null ? 1 : result.status);
