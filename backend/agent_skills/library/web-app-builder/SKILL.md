---
name: web-app-builder
description: Build, fix or extend a web app (HTML/CSS/JS, React, Vue or a Vite project) inside the user's coding project and make it previewable. Use when the user asks for a website, landing page, dashboard, UI component or front-end app.
license: MIT
metadata:
  author: mizan
  version: "1.0"
---

# Web app builder

Work inside the selected coding project with the `workspace_*` tools.

## Steps
1. **Plan first.** For anything beyond one file, write a short `todo_write` list.
2. **Inspect before changing.** `workspace_tree` / `workspace_glob`, then `workspace_read`.
   Follow the existing stack; for a new app prefer a single `index.html` for small pages,
   or a Vite + React (TypeScript) layout for real apps:
   `index.html`, `src/main.tsx`, `src/App.tsx`, `src/index.css`, `package.json`.
3. **Edit precisely.** Use `workspace_edit` with exact, unique `old_string` text; use
   `workspace_write` only for new files. Keep files small and focused.
4. **Make it previewable.**
   - Plain HTML/CSS/JS and single-file React render in the browser preview directly.
   - Publish a page with `workspace_artifact` when the user should see it in chat.
   - Multi-file Vite apps preview in the project's Preview pane.
5. **Check your work.** Run available checks with `workspace_run` (for example
   `node --check file.js`, `npx tsc --noEmit` when dependencies exist). Read errors and fix
   the cause; never claim success without a real result.
6. **Finish with a summary**: what changed, which files, how to preview, what is left.

## Quality bar
- Semantic HTML, keyboard-accessible controls, visible focus, alt text on images.
- Responsive layout (mobile first), no horizontal scroll at 360px.
- No secrets in front-end code; read configuration from the environment.
- Respect the user's language and direction (`dir="rtl"` for Arabic/Urdu content).
