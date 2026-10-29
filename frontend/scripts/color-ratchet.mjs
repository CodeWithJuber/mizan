// Raw Tailwind palette colours (text-gray-500, bg-zinc-900, …) bypass the
// theme tokens in src/index.css. Their count may only go down: this fails
// when it rises above the number kept in .color-ratchet.json.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const RAW = /\b(?:bg|text|border|ring|from|to|via|fill|stroke|outline|divide|placeholder|decoration|shadow|accent|caret)-(?:gray|zinc|slate|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/g;

function* files(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* files(path);
    else if (/\.tsx?$/.test(name)) yield path;
  }
}

let count = 0;
for (const path of files("src")) count += readFileSync(path, "utf8").match(RAW)?.length ?? 0;
const { max } = JSON.parse(readFileSync(".color-ratchet.json", "utf8"));

if (count > max) {
  console.error(`Raw palette colour classes: ${count}, allowed ${max}. Use the theme tokens (text-muted-foreground, bg-card, border-border, text-brand, …).`);
  process.exit(1);
}
console.log(`Raw palette colour classes: ${count} (allowed ${max})${count < max ? `; lower "max" in .color-ratchet.json to ${count}` : ""}.`);
