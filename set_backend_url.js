// set_backend_url.js
//
// Usage:   node set_backend_url.js <backend-url>
// Example: node set_backend_url.js https://polarops.onrender.com
//
// This script updates the constant BACKEND_URL in frontend/app.js so the
// front‑end UI knows where to send its API requests.

const fs = require('fs');
const path = require('path');

// ----- 1️⃣ Get the URL from the command line -----
if (process.argv.length < 3) {
  console.error('Usage: node set_backend_url.js <backend-url>');
  process.exit(1);
}
const newUrl = process.argv[2];

// ----- 2️⃣ Locate the front‑end file -----
const appJsPath = path.join(__dirname, 'frontend', 'app.js');
if (!fs.existsSync(appJsPath)) {
  console.error(`Error: ${appJsPath} not found`);
  process.exit(1);
}

// ----- 3️⃣ Read the file, replace or insert the constant -----
let content = fs.readFileSync(appJsPath, 'utf8');
const regex = /const\s+BACKEND_URL\s*=\s*['"`][^'"`]*['"`]\s*;/;
if (regex.test(content)) {
  // Replace existing declaration
  content = content.replace(regex, `const BACKEND_URL = '${newUrl}';`);
} else {
  // Insert after the first multiline comment block (or at top if none)
  const insertAfter = /\*\/\s*\n/; // closing */ followed by newline
  if (insertAfter.test(content)) {
    content = content.replace(insertAfter, `$&const BACKEND_URL = '${newUrl}';\n`);
  } else {
    content = `const BACKEND_URL = '${newUrl}';\n` + content;
  }
}

// ----- 4️⃣ Write the modified file back -----
fs.writeFileSync(appJsPath, content, 'utf8');
console.log(`✅ BACKEND_URL set to ${newUrl} in frontend/app.js`);
