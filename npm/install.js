#!/usr/bin/env node
// npx fast-ios-device-test                     install, or upgrade (copied to ~/.local/share/fast-ios-device-test)
// npx fast-ios-device-test update              upgrade to the latest version, then each agent's plugin
// npx fast-ios-device-test update-tools        pin and install latest AXe + baguette releases
// npx fast-ios-device-test update-axe|update-baguette   update one pinned tool
// npx fast-ios-device-test --check [--device <name>]   what is there and what is missing
// npx fast-ios-device-test --uninstall         remove the tool (caches and build output stay)
// npx fast-ios-device-test clean [--project <root>] [--maps] [--yes]   delete caches and test builds
"use strict";
const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const PACKAGE = "fast-ios-device-test";
const root = path.join(__dirname, "..");
const args = process.argv.slice(2);
const home = os.homedir();

function run(command, commandArgs, options = {}) {
  const result = spawnSync(command, commandArgs, { stdio: "inherit", ...options });
  return result.status === null ? 1 : result.status;
}

function versionParts(text) {
  const parts = String(text || "").split("-")[0].split(".").map(Number);
  return parts.every(Number.isInteger) ? parts : [];
}

function isNewer(latest, current) {
  const a = versionParts(latest);
  const b = versionParts(current);
  if (!a.length || !b.length) return false;
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) > (b[i] || 0);
  }
  return false;
}

async function latestVersion() {
  if (process.env.FAST_IOS_LATEST_VERSION) return process.env.FAST_IOS_LATEST_VERSION;
  try {
    const response = await fetch(`https://registry.npmjs.org/${PACKAGE}/latest`, { signal: AbortSignal.timeout(5000) });
    return (await response.json()).version;
  } catch {
    return null;
  }
}

function exists(file) {
  try { fs.accessSync(file); return true; } catch { return false; }
}

// The folder the launchers point into: a --link clone, or the copy npx installs.
function installedRoot() {
  const binDir = process.env.FAST_IOS_BIN_DIR || path.join(home, ".local", "bin");
  try {
    return path.dirname(path.dirname(fs.realpathSync(path.join(binDir, "fastSimulatorTest"))));
  } catch {
    return null;
  }
}

function hasSkill(folder) {
  if (!exists(folder)) return false;
  const stack = [folder];
  while (stack.length) {
    const dir = stack.pop();
    let entries = [];
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { continue; }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) stack.push(full);
      else if (entry.name === "SKILL.md" && full.endsWith(path.join("skills", PACKAGE, "SKILL.md"))) return true;
    }
  }
  return false;
}

function onPath(command) {
  return spawnSync("sh", ["-c", `command -v ${command}`], { stdio: "ignore" }).status === 0;
}

// Each agent's plugin updates on its own; the runtime above does not touch it.
// Returns 1 when an agent's update command failed.
function updatePlugins() {
  let failed = 0;
  const codexHome = process.env.CODEX_HOME || path.join(home, ".codex");
  const codexCache = process.env.CODEX_PLUGIN_CACHE || path.join(codexHome, "plugins", "cache", PACKAGE);
  if (hasSkill(codexCache)) {
    if (onPath("codex")) {
      console.log("codex: updating the plugin");
      const ok = run("codex", ["plugin", "marketplace", "upgrade", PACKAGE]) === 0
        && run("codex", ["plugin", "add", `${PACKAGE}@${PACKAGE}`]) === 0;
      if (ok) console.log("codex: restart Codex to load it");
      else { console.log("codex: the plugin update failed (output above)"); failed = 1; }
    } else {
      console.log(`codex: run codex plugin marketplace upgrade ${PACKAGE} && codex plugin add ${PACKAGE}@${PACKAGE}`);
    }
  }
  const claudePlugins = path.join(process.env.CLAUDE_PLUGINS_DIR || path.join(home, ".claude", "plugins"), "installed_plugins.json");
  let claudeText = "";
  try { claudeText = fs.readFileSync(claudePlugins, "utf8"); } catch { /* no Claude Code plugins */ }
  if (claudeText.includes(`"${PACKAGE}@`)) {
    if (onPath("claude")) {
      console.log("claude: updating the plugin");
      if (run("claude", ["plugin", "update", `${PACKAGE}@${PACKAGE}`]) === 0) console.log("claude: restart Claude Code to load it");
      else { console.log("claude: the plugin update failed (output above)"); failed = 1; }
    } else {
      console.log(`claude: run claude plugin update ${PACKAGE}@${PACKAGE}`);
    }
  }
  const agyPlugin = process.env.ANTIGRAVITY_PLUGIN_DIR || path.join(home, ".gemini", "config", "plugins", PACKAGE);
  if (hasSkill(agyPlugin)) {
    console.log(`antigravity: reinstall the plugin: agy plugin install https://github.com/DungVC-Dev/${PACKAGE}`);
  }
  const geminiExtension = process.env.GEMINI_EXTENSION_DIR || path.join(home, ".gemini", "extensions", PACKAGE);
  if (exists(geminiExtension)) {
    console.log(`gemini: run gemini extensions update ${PACKAGE}`);
  }
  return failed;
}

async function update() {
  const current = require(path.join(root, "package.json")).version;
  const latest = await latestVersion();
  if (latest && isNewer(latest, current)) {
    // This copy came from an older npx cache: let the latest package do the update.
    console.log(`update: ${current} -> ${latest}`);
    return run("npx", ["--yes", `${PACKAGE}@${latest}`, "update"], { env: { ...process.env, FAST_IOS_LATEST_VERSION: latest } });
  }
  if (!latest) console.log("update: npm could not be reached; installing this package's version");
  const installDir = process.env.FAST_IOS_INSTALL_DIR || path.join(home, ".local", "share", PACKAGE);
  const installed = installedRoot();
  // A git clone anywhere, the install folder included, is the user's: never copy over it.
  const clone = [installed, installDir].find((dir) => dir && exists(path.join(dir, ".git")));
  if (clone) {
    // A --link clone: copying over it would re-point the links away from the clone being edited.
    console.log(`update: the tool is a git clone (${clone}); update it with:`);
    console.log(`  git -C "${clone}" pull && "${clone}/install.sh" --link`);
  } else {
    const status = run("bash", [path.join(root, "install.sh")]);
    if (status !== 0) return status;
    console.log(`update: the runtime is ${current}`);
  }
  return updatePlugins();
}

function updateTool(name) {
  // Update the pin in the active linked clone/copy, not npx's disposable cache.
  const target = installedRoot() || root;
  return run("bash", [path.join(target, "install.sh"), `--update-${name}`]);
}

async function main() {
  if (process.platform !== "darwin") {
    console.error("fast-ios-device-test needs macOS with Xcode.");
    return 1;
  }
  if (args.includes("--link")) {
    console.error("--link would point at npx's temporary folder; clone the repo and run install.sh --link instead.");
    return 2;
  }
  if (args[0] === "update") return update();
  if (args[0] === "update-axe") return updateTool("axe");
  if (args[0] === "update-baguette") return updateTool("baguette");
  if (args[0] === "update-tools") return updateTool("tools");
  if (args[0] === "clean") return run("python3", [path.join(root, "scripts", "fast_ui_clean.py"), ...args.slice(1)]);
  return run("bash", [path.join(root, "install.sh"), ...args]);
}

main().then((code) => process.exit(code));
