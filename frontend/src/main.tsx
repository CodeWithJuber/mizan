import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { installStaleBuildReload } from './utils/staleBuild'
import { registerWorker } from './utils/push'
import { inviteCode } from './utils/imtihan.ts'
import '@fontsource-variable/dm-sans'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/amiri/400.css'
import '@fontsource/amiri/700.css'
import './index.css'

installStaleBuildReload()
// Notifications-only service worker (caches nothing); harmless where unsupported.
registerWorker().catch(() => undefined)

// The public reliability page and an invited person's human-panel page need no
// sign-in and none of the app around them.
const ReliabilityPage = lazy(() => import('./pages/ReliabilityPage'))
const PanelInvitePage = lazy(() => import('./pages/PanelInvitePage'))
const path = window.location.pathname.replace(/\/+$/, '')
const PublicPage = path === '/reliability' ? ReliabilityPage : inviteCode(path) ? PanelInvitePage : null

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {PublicPage ? (
      <Suspense fallback={null}>
        <PublicPage />
      </Suspense>
    ) : (
      <BrowserRouter>
        <App />
      </BrowserRouter>
    )}
  </StrictMode>
)
