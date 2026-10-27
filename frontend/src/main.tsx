import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { installStaleBuildReload } from './utils/staleBuild'
import { registerWorker } from './utils/push'
import './index.css'

installStaleBuildReload()
// Notifications-only service worker (caches nothing); harmless where unsupported.
registerWorker().catch(() => undefined)

// The public reliability page needs no sign-in and none of the app around it.
const ReliabilityPage = lazy(() => import('./pages/ReliabilityPage'))
const isPublicPage = window.location.pathname.replace(/\/+$/, '') === '/reliability'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isPublicPage ? (
      <Suspense fallback={null}>
        <ReliabilityPage />
      </Suspense>
    ) : (
      <BrowserRouter>
        <App />
      </BrowserRouter>
    )}
  </StrictMode>
)
