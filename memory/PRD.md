# RapidoChecker — PRD

## Migration note (this workspace, 2026-06)
- App migrated from github.com/thiagosm15/rapidochecker into this workspace for publishing prep.
- backend/.env: JWT_SECRET generated; ADMIN_PASSWORD reset to `Rapido-570c2c10` (see test_credentials.md).
- MongoDB starts empty here (previous session's DB did not migrate); approved test CPF 529.982.247-25 seeded (device test-device-1).
- Backend suite: 55/55 passing serial (`pytest -n0`); stale test helpers updated to send device_id (iteration-12 contract).
- Publish: use the platform Publish button → Android build (accessibility service needs a real APK; web/Expo Go = Modo prévia).

- Removal (2026-06, iteration 28): at the user's request, the 99 app and all its functions (radar) were removed. Apps are now rapido, moove and urbano. get_settings $unsets leftover apps.app99; /rides only lists known apps; a stored busy='app99' is cleared on the device (Kotlin currentBusy + JS getBusy). Radar code, settings fields, UI and tests were deleted.
- Fix (2026-06, iteration 27): the radar did not refresh on the device. It now does a real screen tap (dispatchGesture) on "Atualizar" (falling back to ACTION_CLICK, then a pull-down); the tick runs every 500 ms; the interval is 1-30 s (default 1); radar screen detection is relaxed; and diag.radar records why it did/didn't refresh, shown in Modo aprendizado → 99 → Diagnóstico.
- Feature (2026-06, iteration 26): web admin panel for the computer at GET /api/painel (backend/admin_web.html, plain HTML+JS, same /api/admin/* endpoints; token kept in sessionStorage; CSP/no-store/X-Frame-Options DENY). Tabs with counts, search by CPF/name, rename, 1-day trial, 7/15/30/Sem prazo, trocar aparelho, bloquear, excluir with confirmation. Trial is atomic (filter trial_used != true) and only offered for pending/expired users. Production URL: https://ready-to-publish-10.emergent.host/api/painel
- Feature (2026-06, iteration 25): admin "Liberar teste de 1 dia (só uma vez)" per registration. PATCH /api/admin/users/{id} {trial:true} → approved, expires_at=now+1d, trial_used=true, trial_at. A second time returns 409; combining it with access_days returns 422. The admin card shows "Teste de 1 dia já usado em …" afterwards.
- Feature (2026-06, iteration 24): 99 radar (apps.app99.radar_enabled, radar_interval_s 2-30, default 4). The native radarTick runs every 1s; while the 99 "Solicitações" screen is on screen (texts Solicitações / Escolha uma / Ainda buscando), and the bot is on, in schedule and not busy, it taps "Atualizar" or pulls down every N s. radarScan evaluates every "Escolher" card (offerText per card; each offer judged and logged once per 2 min) and taps Escolher on the first match (then holds for 8 s, alert/notify/busy as usual). The accept logic of the other apps is unchanged.
- Feature (2026-06, iteration 23): two new apps with the same rules as the others: Urbano Norte (key urbano, target_package "urbanonorte" → br.com.urbanonorte.taxi.drivermachine, source urbanonorte) and 99 (key app99, target "app99" → com.app99.driver, source 99app). Existing settings get the missing apps added on read. All UI loops over APP_KEYS; one ride at a time pauses every other app's bot.
- Feature (2026-06, iteration 22): "Locais recusados" (Settings.blocked_places, global for both apps). Filtros section with add input + removable chips; backend trims/collapses spaces/dedupes case-insensitively (max 200 items, 80 chars). Native: the offer card text (price + km scopes) is accent/case-folded and matched on word boundaries; a match adds reason "Local recusado: X" (so auto-reject applies).
- Feature (2026-06, iteration 21): "Voltar online" action button on the ride-accepted notification (only when exclusive_enabled). ResumeBotsReceiver (exported=false) clears busy, cancels the notification and shows a toast. busy stores notification_id, so clearBusy (finish tap, Painel button, receiver) also removes the notification.
- Feature (2026-06, iteration 19): "Uma corrida por vez" (exclusive_enabled, default on). When a bot accepts in one app, the native service stores busy={app,since} and the other app's bot is skipped (off-line). A tap (typeViewClicked) on a finish_texts button (default Finalizar/Encerrar/Concluir) in the busy app clears it, so both bots are online again; 3h safety expiry. Painel shows the "Em corrida na X" banner with a "Voltar online" button; the master ON also clears busy. Bots only, the driver apps are untouched.
- Fix (2026-06, iteration 17): MooveCar offers not read at all on the new APK. Service now also reads the window that fired the event and falls back to the active window when no window matches the package (old behaviour); listens to every launchable package containing the target text; writes a Diagnóstico (listening packages, last event package, windows read, status, visible texts) shown in Modo aprendizado.
- Feature (2026-06): auto-reject per app (reject_enabled + reject_texts, default "Recusar") taps the reject button when an offer fails filters; phone notification with price/km on every auto-accept (notify_enabled, POST_NOTIFICATIONS asked on Android 13+ from Filtros); Painel master button turns both bots ON/OFF at once.
- Fix (2026-06): MooveCar "modo padrão" pop-up offers were not accepted. Service now scans every window of the target app (overlay isn't the active window), listens to typeWindowsChanged, reads price/km only from the card around the accept button (ignores background prices), and falls back to a real screen tap (canPerformGestures) if ACTION_CLICK is ignored. Needs new APK + re-enabling the accessibility service.

---


# AutoCorrida – PRD

## Problem statement
"Crie um aplicativo mobile: que aceite sozinho as corridas do aplicativo rapidocar de acordo com filtro ajustável de preço/km"
Follow-up: "Adicione ao bot para ele ficar off-line na rapidocar sempre que aceite uma corrida na 99, e fique online quando a corrida acabar."

## Architecture
- Expo Router app (4 tabs: Painel, Filtros, Simular, Histórico), dark utility theme (Rajdhani + IBM Plex Sans)
- FastAPI + MongoDB: /api/settings, /api/simulate, /api/rides, /api/rides/bulk, /api/stats
- Local Expo native module `modules/ride-filter` (Android only, Kotlin):
  - RideAccessibilityService reads RapidoCar screen (R$ and km), checks filters, taps "Aceitar"
  - 99 sync: detects ride in progress/ended on the 99 app (configurable texts), opens RapidoCar, taps offline/online, returns to 99
  - Events stored in SharedPreferences and synced to the backend when the Painel opens
- On Expo Go / web, the native module is absent → "Modo prévia" + Simulator

## Implemented (2026-06)
- Auto-accept switch, accessibility service status + button to open settings
- Filters: min R$/km, min fare, max pickup km, editable accept texts, target package
- 99 integration toggle + editable texts (ride active/end, offline/online buttons)
- Simulator with ACEITO/RECUSADO stamp, history with filter chips, daily earnings / acceptance rate
- Does not auto-accept on RapidoCar while a 99 ride is in progress

## Backlog
- P0: Validate on a real Android APK with the real RapidoCar/99 texts and adjust defaults
- P1: Per-device settings (multi-user), working-hours schedule, minimum price per minute
- P2: Weekly earnings chart, sound alert on accept

## Update (2026-06, iteration 3)
- Modo aprendizado (/aprender): service captures visible texts of RapidoCar/99; user taps a text to assign it to Aceitar / offline / online / 99 lists (warning on suspicious picks)
- Working hours: schedule_enabled/start/end/days (crosses midnight), enforced in Android service and simulator
- Weekly chart on Painel (/api/stats/weekly?tz=)
- Sound + vibration alert on auto-accept (alert_enabled), native only
- User asked for an APK: build via Publish → Android build

## Update (2026-06, iteration 4-5)
- JWT login per driver (email/password, 30-day token, 5 failed logins/15 min lockout), data scoped by user_id; pre-login data migrated to the first account
- Accessibility disclosure screen (/aviso) before enabling the service; privacy policy at /api/privacy; account screen (logout, clear history, delete account)
- Monthly report (/relatorio, /api/stats/monthly)
- Logout resets native service config; Stack.Protected auth gating
- Speed: notificationTimeout=0, events filtered to RapidoCar/99 packages only, cached config parsing

## Update (2026-06, iterations 6-8)
- Login is CPF only (POST /api/auth/cpf). New CPFs are "pending" until the owner approves them in the in-app Área do administrador (/admin, ADMIN_PASSWORD in backend/.env). Blocking a driver signs them out.
- Removed: 99 integration, earnings counters (today/weekly/monthly report), simulator tab and endpoints
- Added MooveCar: the Android service reads RapidoCar and MooveCar, each with its own filters (settings.apps.rapido / settings.apps.moove)
- Rate limits use the real client IP (CF-Connecting-IP / XFF[-3]); admin login has a global limit of 10 failures per 15 min
- Root cause of the user's error: the old APK had no login but called the new auth-protected backend → new build required

## Iteration 9 (Jun 2026)
- Admin grants access per driver: 7/15/30 days or no limit (PATCH /api/admin/users/{id} {access_days}); expired drivers get login status "expired" and 401 on API.
- Painel "Hoje" card: accepted/rejected per app (GET /api/rides/summary?since=<local midnight ISO>).
- New app icon/splash/login logo (RapidoChecker artwork, white background).
- Admin password changed via secure secrets card (ADMIN_PASSWORD).
- Iteration 10-11: admin "Vencidos" tab; Painel warning when access ends in <=3 days; login explains automatic sign-out (expired/blocked); app renamed to RapidoChecker.
- Iteration 12: one device per CPF (device_id bound on request/first login; admin 'Trocar aparelho' unlinks; token carries dev claim).

- 2026-06: Painel agora mostra bots dos outros apps como OFF-LINE (cinza) enquanto há corrida em andamento; botão mestre conta só bots realmente online.

- 2026-06: Added LOG Urbano (key log, pkg br.com.devbase.logurbano.prestador, target logurbano). Busy guard before tap; retry never taps another configured app; longest package match; strict finish-text match; master button reflects paused bots.
