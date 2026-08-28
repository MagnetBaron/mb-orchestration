# Mobile leaf catalog

Select from this catalog; then open only the selected leaf files under
`~/.codex/skill-library/mobile/`.

## Dart

| Signal | Leaf | Notes |
|---|---|---|
| Unit tests for non-widget Dart logic | `dart-add-unit-test` | Use when tests are in scope. |
| CLI entrypoint, exit codes, scripts | `dart-build-cli-app` | Pure Dart command-line apps. |
| LCOV or coverage collection | `dart-collect-coverage` | Coverage deliverable only. |
| Active runtime or analyzer failure | `dart-fix-runtime-errors` | Prefer `dart-run-static-analysis` unless an active trace or Dart MCP runtime evidence exists; upstream title/body are analyzer-focused despite the name. |
| Mockito mocks and generation | `dart-generate-test-mocks` | External dependency isolation. |
| Migrate matcher expectations to checks | `dart-migrate-to-checks-package` | Explicit migration only. |
| `pub get` dependency resolution failure | `dart-resolve-package-conflicts` | Package constraints only. |
| Analyzer warnings, errors, lint cleanup | `dart-run-static-analysis` | Default analyzer workflow; CLI-capable. |
| Native Assets hooks for C or C++ | `dart-setup-ffi-assets` | Version-sensitive; verify SDK and package versions first. |
| Generate C, Objective-C, or Swift FFI bindings | `dart-use-ffigen` | Binding generation, not general FFI design. |
| Explicit pattern-matching refactor | `dart-use-pattern-matching` | Do not load for ordinary Dart edits. |
| Explicit primary-constructor work | `dart-use-primary-constructors` | Version-sensitive; confirm project language version. |
| Dart API doc comments | `dart-write-documentation` | Documentation deliverable only. |

## Flutter

| Signal | Leaf | Notes |
|---|---|---|
| End-to-end or integration flow | `flutter-add-integration-test` | Dart MCP improves exploration; verify whether the project uses current `integration_test` or legacy `flutter_driver` patterns. |
| Widget preview | `flutter-add-widget-preview` | Verify the installed Flutter version supports the preview API used. |
| Component rendering or interaction test | `flutter-add-widget-test` | Prefer for isolated widget behavior. |
| New app structure or architecture refactor | `flutter-apply-architecture-best-practices` | Do not load for a local feature edit. |
| Responsive mobile/tablet/desktop layout | `flutter-build-responsive-layout` | Layout adaptation, not overflow diagnosis. |
| Overflow, unbounded constraint, ParentData error | `flutter-fix-layout-issues` | Dart MCP or live app evidence preferred; label CLI or manual fallback. |
| Small manual JSON model mapping | `flutter-implement-json-serialization` | Not for code-generated serialization. |
| `MaterialApp.router`, deep links, browser history | `flutter-setup-declarative-routing` | Router setup only. |
| ARB, `flutter_localizations`, `intl`, l10n setup | `flutter-setup-localization` | Localization initialization. |
| REST calls using `package:http` | `flutter-use-http-package` | Not for GraphQL, gRPC, or another client. |

## iOS accessibility

| Signal | Leaf | Notes |
|---|---|---|
| VoiceOver, Dynamic Type, labels, traits, hints, Switch Control, Voice Control, Full Keyboard Access, UIKit or SwiftUI accessibility | `ios-accessibility` | Manual device and assistive-technology validation remains required. Do not load merely because a Flutter app targets iOS. |

## Pairing rules

- Choose one primary leaf by the defect or deliverable, not by every technology present in the repository.
- Add a test leaf only when the brief requires that test artifact or the changed behavior needs a regression test.
- `ios-accessibility` may pair with one implementation leaf when native iOS accessibility is an explicit acceptance criterion.
- Treat the version-sensitive and upstream-mismatch notes as gates. Verify current project versions and behavior before applying those instructions.
