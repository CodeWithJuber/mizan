# Shahid: a browser that only goes where you point and sends nothing without you

Shahid (شاهد, witness) is MIZAN's browser. Ask "Open https://shop.example and
search for Ajwa dates", "https://example.com ka screenshot do" or "Visit
https://example.com/contact and fill my name Zubair": MIZAN opens the page in a
sandboxed browser, does the steps, answers from what the page says, and shows a
screenshot.

## What MIZAN fixes before the browser starts

- **Where.** The sites are the hosts of the links in your own words, with their
  `www.` twin. A link inside pasted text or an image never counts. The browser
  may follow a link only within those sites. A page's own scripts, styles and
  images may come from any public host.
- **What.** Lisan proposes the steps: go to, click (by role and visible text),
  fill (by label), press a key, read, screenshot, wait. MIZAN checks each one:
  - every page is an https page of your sites;
  - a field is filled only with words you wrote, so MIZAN never types a value
    you did not say (a card number, an address);
  - the steps end with a read, so the answer comes from the page.
  If Lisan's plan is refused twice, MIZAN just opens the page and reads it.
- **Changes.** Every request that would change something on the site (a form
  posted, an order placed: any method but GET, HEAD or OPTIONS) is **held**.
  - The page stays where it was.
  - MIZAN shows you exactly what would be sent (method, address, form data) and
    asks.
  - Only on your **Allow** does it run the steps again with that one request
    approved (`shahid_submit`). Allow is asked in every chat mode, Full auto
    included.
  - In an unattended run (a watcher, Telegram) the action is held for you, and
    with no one to ask nothing is sent.

## Where it runs

Each job is a one-shot container on MIZAN's private runner, from the
`workspace-browser` image (Playwright 1.64.1, Chromium headless shell). The
container is:
- read-only, as user 65534;
- run with every capability dropped and `no-new-privileges`;
- limited to 1 CPU, 1 GB of memory and 256 processes.

Its only network is an internal Docker network whose one peer is the browse
egress proxy. That proxy:
- connects only on port 443;
- connects only to hosts whose every address is globally routable, so never to
  the server, other containers, private networks or cloud metadata.

Inside, every request goes through a guard:
- a navigation outside your sites, or a held form post, is aborted (`net::ERR_ABORTED`): the browser stays on its page, with no error page;
- a request that changes something is held;
- WebSockets, service workers and downloads are refused.

The container and its network are removed after the job. Nothing (cookies,
history, cache) outlives it.

## What you can check afterwards

Each step is a signed receipt in your Sakk chain (`/api/sakk`). A receipt holds:
- the full address, fragment included;
- the SHA-256 of the page's accessibility snapshot, its text and the screenshot;
- what was held and what you approved.

The screenshot is kept with the chat like an image you sent (`/api/media/{sha}`),
and deleting the chat (Mahw) deletes it. The page's text is outside content:
- instructions in it are neutralized (Amanah);
- an action the model would choose after reading it needs a person.

## Turning it on

Shahid needs the private runner (the server sandbox) with the browser image.
- **The image:** CI builds it, runs the self-test inside the hardened container
  (a real Chromium checks that a link to another origin is not followed, an
  order is held, an approved order goes through, and every step is witnessed),
  and publishes it with the other images.
- **On the server:** the runner setup (`scripts/setup_workspace_runner.py`)
  pulls it into the worker daemon, pins it by content ID, and gives the runner
  `MIZAN_WORKSPACE_BROWSER_IMAGE`. The browser image is optional: a setup
  without it leaves MIZAN reading pages without a browser.

Without the browser, MIZAN reads the page instead, as before. It never falls back
to a browser inside the backend.

The older in-process browser tools of the web agent (Mubashir) now:
- refuse private and local addresses (`net_guard`), redirects included;
- no longer take screenshots through a shell.

## Code

- `backend/workspace/browse_agent.py`: the job inside the container: the
  request guard `decide`, the steps, the witness hashes.
- `backend/workspace/browse_selftest.py`: the real-browser self-test, run by hand
  in the image (the command is in [ci-artifacts.md](ci-artifacts.md), Not in CI).
- `backend/workspace/browse.py` and `runner.py` (`POST /browse`): the container
  and its network on the runner.
- `backend/workspace/egress_proxy.py`: `MIZAN_EGRESS_MODE=public` for the browse
  proxy.
- `backend/tadbir/shahid.py`: the sites, the plan check, the call, the
  screenshot and the receipts.
- `backend/skills/builtin/shahid_browser.py`: the `shahid_read` and
  `shahid_submit` tools.
- `backend/tadbir/engine.py` (`_browse`) and `fahm.py` (`browse`, family
  `page` with `web_read`).
- `docker/Dockerfile.workspace-browser`, `.github/workflows/ci.yml` (job
  `production-images` builds the image Deploy Production sends).
- Tests: `tests/test_shahid.py`.
