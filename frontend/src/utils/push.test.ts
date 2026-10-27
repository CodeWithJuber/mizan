import { keyBytes } from "./push.ts";

let checks = 0;
function check(name: string, condition: boolean) {
  if (!condition) throw new Error(name);
  checks++;
}

const bytes = keyBytes("BHJpZUwI-_8");
check("base64url decodes with padding restored", bytes.length === 8 && bytes[0] === 0x04);
check("url-safe characters map back", bytes[6] === 0xfb && bytes[7] === 0xff);

console.log(`push: ${checks} checks passed`);
