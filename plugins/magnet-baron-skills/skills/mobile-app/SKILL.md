---
name: mobile-app
description: Mobile-app coding standards for iOS, Android, and cross-platform work — architecture, platform conventions, state and data, testing, and store release; use when building or changing a mobile app.
---

# Mobile app coding

Standards for building and changing mobile apps so a change respects platform conventions, survives
the mobile lifecycle, and ships cleanly through review and the app stores. The constraints that make
mobile different from web: a hostile runtime (battery, memory, flaky network, app suspension), a
slow release channel (store review, users on old versions), and strong platform-native expectations.

## Read before you write

- Identify the stack and match it: native **iOS** (Swift/SwiftUI or UIKit), native **Android**
  (Kotlin/Jetpack Compose or Views), or cross-platform (**React Native**, **Flutter**). Follow the
  architecture already in the repo (MVVM, TCA, Redux, Bloc/Riverpod) — do not introduce a second
  pattern.
- Honor the existing minimum OS version, dependency manager (SPM/CocoaPods, Gradle, npm/pub), and CI
  before adding anything.

## Architecture

- Separate **UI / presentation state / domain logic / data**. Views are thin and declarative; put
  logic in a view model / presenter / store that is unit-testable without the UI toolkit.
- Keep a single source of truth for each piece of state and drive the UI from it (unidirectional
  data flow). Avoid scattering mutable state across view controllers/widgets.
- Isolate platform and third-party SDKs (payments, analytics, push) behind your own interfaces so
  they are swappable and mockable, and so a platform difference lives in one file.
- For cross-platform, keep shared logic platform-agnostic and push platform specifics to a thin
  adapter; do not litter `Platform.OS`/`Platform.isAndroid` checks through business code.

## Lifecycle, memory, and the runtime

- Handle the full lifecycle: background/foreground, suspension and process death, low-memory
  warnings, rotation and configuration changes. **Assume the OS can kill and restore your process at
  any time** — persist and restore transient UI state, do not hold it only in memory.
- Do all real work off the main/UI thread; keep the main thread for rendering only. Use the
  platform's structured concurrency (Swift `async/await`/actors, Kotlin coroutines/`Flow`) rather
  than ad-hoc threads and callbacks.
- Avoid retain cycles and leaks: weak references for delegates/closures capturing `self` (iOS),
  cancel jobs tied to a destroyed lifecycle scope (Android), remove observers/listeners on teardown.
  Dispose subscriptions and timers deterministically.
- Free heavy resources (images, media, DB cursors) promptly; downsample images to display size.

## State and data

- Choose persistence to fit the data: key-value (UserDefaults/SharedPreferences/MMKV) for small
  prefs, a real DB (Core Data/SwiftData, Room, SQLite/Drift) for structured data, the **Keychain /
  Keystore** for secrets and tokens — never plain prefs or source for credentials.
- Design **offline-first**: cache, queue mutations, and reconcile on reconnect. Treat the network as
  optional and slow — timeouts, retries with backoff, and a clear offline UI state. Never block the
  UI on a request with no timeout.
- Version your local schema and write migrations; a user updating from an old version must not lose
  data or crash on launch.
- Request permissions (location, camera, notifications, tracking) lazily, in context, with a
  pre-prompt explaining why, and degrade gracefully when denied.

## Platform conventions

- Follow the platform's design language — **Human Interface Guidelines** on iOS, **Material** on
  Android — for navigation, gestures, system back (Android), safe areas/notches, dynamic type, and
  dark mode. A native-feeling app respects the platform it is on rather than cloning the other.
- Support accessibility: VoiceOver/TalkBack labels, Dynamic Type / font scaling, sufficient contrast
  and hit targets (≥44pt iOS / 48dp Android). This is a correctness requirement.
- Localize user-facing strings through the platform mechanism (`.strings`/String Catalog,
  `strings.xml`, i18n library); no hardcoded display text. Handle RTL if you localize to it.

## Testing

- **Unit-test** the view models / stores / domain logic (the bulk of your tests) with the platform
  framework (XCTest/Swift Testing, JUnit, Jest). Keep them fast and free of the UI toolkit.
- **UI/integration tests** on the critical flows only (onboarding, purchase) with XCUITest,
  Espresso, or Detox/Flutter integration tests — they are slow and brittle, so keep them few and
  stable.
- Test on a **matrix**: oldest supported OS, a small and a large screen, low-memory and slow-network
  conditions, and both light/dark. Simulators for breadth, at least one real device for anything
  touching performance, camera, or push.
- Keep tests deterministic: inject clocks, stub the network, control animations. Run the suite and
  the linter/formatter (SwiftLint, ktlint/detekt, ESLint) before a PR.

## Release

- Manage versioning deliberately (semantic version + monotonic build number) and keep signing
  credentials/provisioning in CI secrets, never in the repo.
- **Users stay on old versions** — keep API changes backward-compatible, feature-flag risky changes
  for staged rollout, and keep a kill switch for anything that could break clients in the field.
- Ship crash and performance monitoring (symbolicated) so field issues are diagnosable; watch
  startup time, jank, and battery.
- Respect store review rules and privacy manifests / data-safety declarations; keep the requested
  permission set minimal and justified.

## Safe-change discipline

Smallest correct diff; stay in the named file scope; no drive-by refactors, dependency bumps, or
min-OS changes mixed into a feature. State what changed, why, how it was tested (which
devices/OS versions), and the rollback in the PR — and flag anything touching payments,
permissions, auth tokens, or data migrations so review sets the right bar.
