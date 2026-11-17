# RapidoChecker — PRD

## Migration note (this workspace, 2026-06)
- App migrated from github.com/thiagosm15/rapidochecker into this workspace for publishing prep.
- backend/.env: JWT_SECRET generated; ADMIN_PASSWORD reset to `Rapido-570c2c10` (see test_credentials.md).
- MongoDB starts empty here (previous session's DB did not migrate); approved test CPF 529.982.247-25 seeded (device test-device-1).
- Backend suite: 55/55 passing serial (`pytest -n0`); stale test helpers updated to send device_id (iteration-12 contract).
- Publish: use the platform Publish button → Android build (accessibility service needs a real APK; web/Expo Go = Modo prévia).

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
