import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { installStaleBuildReload } from './utils/staleBuild'
import { registerWorker } from './utils/push'
import './index.css'

installStaleBuildReload()
// Notifications-only service worker (caches nothing); harmless where unsupported.
registerWorker().catch(() => undefined)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
)
