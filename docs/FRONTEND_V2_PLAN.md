# Frontend plan: recordings saved on the user's own device

Status: revised planning specification. This replaces the earlier server-primary/PWA-download plan. The current application has not yet been rebuilt to implement it.

Companion: [BACKEND_V2_PLAN.md](BACKEND_V2_PLAN.md). The product has two repositories: whiteboard-backend and whiteboard-frontend. The frontend repository contains website and mobile build targets.

## 1. Non-negotiable behavior

**Anything recorded or derived from a private lecture is saved on the user's personal device, never in our backend storage or MongoDB.**

This includes video/audio, pictures, enhanced images, thumbnails, lecture titles, handwritten notes, OCR text, timestamps/history, local calibration/baselines, PDFs and other exported files.

A user does not have to upload a recording and download it again to own it. “Saved” means a durable local file/catalog commit on that device. Server availability, login expiry or admin account blocking must not delete existing local recordings.

Accounts, FAQs, announcements and deliberately published community text remain backend platform features. They are not a remote archive of personal lectures. Admins cannot browse or erase phone-only files.

## 2. Mobile delivery and tools

Keep Next.js as the website for account/help/community/admin access, plus a browser/PWA fallback. For reliable native file/media integration, add a React/Capacitor mobile target using locally bundled assets.

A PWA can store data physically on a phone in IndexedDB/OPFS, but that is browser-managed private storage and is subject to browser clearing/quotas. It does not provide identical Photos/Files integration across iPhone and Android. It should not be the only implementation offered for the stronger personal-storage requirement. [MDN OPFS](https://developer.mozilla.org/en-US/docs/Web/API/File_System_API/Origin_private_file_system), [browser storage behavior](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)

| Responsibility | Choice |
| --- | --- |
| Website | Next.js, React, TypeScript; Pages Router organization following Nestar/TripLink |
| Mobile client | React/Vite bundled inside Capacitor iOS/Android targets |
| Reusable UI | Shared React components, Tailwind/CSS tokens, Radix primitives, Lucide |
| Platform API | Apollo Client + GraphQL Code Generator |
| Forms | React Hook Form + Zod |
| Durable phone catalog | SQLite through a reviewed compatible native adapter |
| Phone files | Native filesystem APIs, exposed through a typed storage adapter |
| Photos/videos integration | iOS PhotoKit; Android MediaStore through a native bridge |
| Notes/documents | App Documents plus OS Files/document export |
| Long recording | Native camera/recorder bridge: AVFoundation on iOS, CameraX/MediaRecorder on Android |
| Local PDF creation | pdf-lib with bundled fonts; local images/notes as inputs |
| Web-only local storage | IndexedDB/OPFS and explicit downloads; feature-detected fallback |
| Native credentials | Keychain/Keystore-backed secure storage |
| Testing | Vitest/Testing Library, Playwright for web, native integration/device tests |

Capacitor has on-device filesystem APIs; ordinary filesystem plugins alone do not implement every video-recording or gallery workflow. Build and test the necessary native bridge. Use supported packages and pin verified versions. [Capacitor Filesystem](https://capacitorjs.com/docs/apis/filesystem), [Capacitor configuration](https://capacitorjs.com/docs/config), [SQLite adapter reference](https://github.com/capacitor-community/sqlite)

Do not put a remotely hosted Next.js server UI into a thin WebView and call that an offline app. Bundle the mobile app's assets; keep Next SSR/admin concerns in the website target. Xcode is required for iOS builds, Android Studio/SDK for Android; App Store/Play distribution needs its respective release/signing setup.

## 3. Frontend repository structure

    whiteboard-frontend/
      apps/
        web/
          pages/
            index.tsx
            account/
            library/
            help/
            community/
            _admin/
              index.tsx
              users/
              devices/
              help-center/
              community/
              reports/
              system/
              audit/
          public/
          next.config.ts
        mobile/
          src/
            screens/
              LocalLibrary/
              LectureDetail/
              Capture/
              VideoPlayer/
              DeviceImport/
              LocalStorage/
              Account/
              Help/
              Community/
            native/
              recorder/
              media-library/
              document-storage/
              sqlite/
          ios/
          android/
          public/
          capacitor.config.ts
          vite.config.ts
      packages/
        ui/
        platform-api/
          apollo/
          generated/
          user/
          admin/
          public/
        local-library/
          models/
          repository/
          migrations/
          idempotency/
          integrity/
        storage/
          native/
          browser/
        capture/
          calibration/
          recording/
          analysis-client/
          lifecycle/
        exports/
          pdf/
          manifest/
        auth/
        validation/
        types/
      tests/
        unit/
        web-e2e/
        native-integration/
        privacy/
      docs/
      package.json
      package-lock.json
      README.md
      AGENTS.md

Shared packages expose interfaces; native SQLite/PhotoKit/MediaStore modules must not be imported into Next server rendering. A website cannot silently access the phone app's filesystem: the user explicitly imports/exports a bundle when moving notes to another device. There is no server lecture synchronization.

## 4. Exact local storage design

Use a persistent application Documents/data location, not Cache or temporary storage. The local catalog and actual file paths are owned by the phone installation.

    <phone app documents>/Whiteboard/
      library.sqlite
      lectures/<local-lecture-uuid>/
        originals/
        enhanced/
        thumbnails/
        recordings/
        notes/
        exports/
        analysis-reference/
        recovery/
      transfers/

Local SQLite tables: lectures, captures, recordings, recordingSegments, notes, localAssets, analysisSettings, calibration, captureEvents, saveRequests, localJobs and migrations. Index local lecture/date and idempotency keys. Avoid embedding image/video blobs in SQLite; store durable file references/checksums and media identifiers.

Use local UUIDs. Do not send the lecture title, notes, local paths, OCR text or durable catalog to platform GraphQL. The backend has no private lecture database.

### User-visible file destinations

- Every capture/recording is saved automatically into persistent on-device app storage.
- Offer Photos/Gallery saving through native APIs after the necessary user permission. Show whether the gallery copy succeeded separately from the app-local save.
- On Android, use MediaStore for gallery media and the system document workflow for PDFs/files. Avoid unrestricted whole-disk permissions.
- On iPhone, use PhotoKit for Photos and app Documents/OS document export for Files. Configure app file visibility where appropriate; document destinations outside the app may require user selection.
- Keep originals until the chosen native destination has confirmed its commit. If access is denied, retain the app-local original and explain how to export later.
- Distinguish app-private files from exported gallery/documents copies: uninstalling the app may remove app-owned data, while external copies follow OS/user rules.

[Android shared storage](https://developer.android.com/training/data-storage/shared/media), [Apple photo saving](https://developer.apple.com/documentation/avfoundation/saving-captured-photos), [Capacitor filesystem visibility](https://capacitorjs.com/docs/apis/filesystem)

The app must not start an automatic developer/cloud backup. Exclude the private vault from automatic application backup where supported. User-enabled iCloud Photos/device backups are OS/user-controlled, so do not promise that exporting to Photos can override those settings or prevent the user's chosen backup service.

## 5. Sessions, databases and cache

| Concept | Location / behavior |
| --- | --- |
| Lecture session | Device SQLite plus actual local files; authoritative |
| Private notes/OCR/history | Device only |
| Local recording job | Device catalog/recovery manifest; never a server job |
| Login session | Backend auth record; credentials in platform secure storage |
| Platform content | Backend MongoDB; optional frontend read cache |
| Apollo cache | In-memory API view cache; no private lecture data belongs there |
| Model/thumbnail/view cache | Re-creatable device cache; not the only copy of originals |
| Web/PWA library | Browser-managed IndexedDB/OPFS; label its capabilities accurately |
| Photo/file export | User-owned native destination; no backend archive |

Local SQLite is still a database, but it is on the person's phone, not our server database. Keep these terms explicit in setup/help screens.

Logout clears tokens and platform API cache but never silently deletes recordings, SQLite catalog or exported files. Lock access to private app screens using device/profile controls as appropriate; a deliberate local erase action is separate and requires confirmation. Account blocking prevents connected platform services, not access to already owned local recordings.

## 6. Local recording and save transactions

### Capture workflow

1. Create a local lecture/destination and verify storage availability.
2. Ask for camera permission; microphone access is separate and off by default.
3. Start preview/recording only after user action. Prefer the rear camera; offer mounted/handheld modes.
4. Record video directly to local files through the native recorder, without sending it to the server or building the whole recording as a JavaScript/base64 blob.
5. When connected analysis returns a candidate, save its actual image bytes and measurements locally, or take a manual local snapshot.
6. Stage files, flush/finalize them, rename into the permanent local location and commit SQLite records with unique save-request IDs.
7. Show “Saved on this phone” only after that local commit. A transmitted frame or AI decision is not a saved recording.
8. Acknowledge candidate persistence to the analysis service only afterward.
9. Generate thumbnails/enhanced copies/notes locally; exports write separate local files and never overwrite originals.

Use a bounded current-frame queue and one analysis frame in flight, initially around five frames per second. Keep one pending explicit capture command so a user click during inference is not dropped. Drop automatic sampling opportunities under load; never put raw frames into a remote retry queue.

### Continuous video

Continuous video is a first-class addition, not a side effect of webcam preview. Use a native recorder with durable output/recovery manifests and bounded memory. Where long-recording segmentation is required, preserve completed segments and clearly indicate recovered/incomplete segments; do not claim a partially finalized MP4 is valid. Local playback/export must work without the backend.

Record foreground-first. Handle screen lock, app backgrounding, camera interruption, calls, rotation, process termination and storage-full events according to the actual OS capabilities. Never promise unrestricted background camera recording. On interruption, finalize/checkpoint what the platform permits and show the real result on reopening.

No silent deletion to free space. Show free space/estimated size and stop/finalize cleanly on write failure. A failed gallery export does not mean the local original was lost; a failed local write must not produce a Saved message.

## 7. Connected AI without server persistence

The default library is local. Connected analysis is a separate clearly described permission:

“Selected frames may be sent to our analysis service temporarily. Recordings and notes remain on this device; the service does not retain lecture content.”

The phone uses an ephemeral random stream ID, not a durable lecture identity. Keep local calibration and accepted baseline; resend necessary baseline bytes after reconnect with permission. The Python service uses bounded RAM and returns rectified/enhanced images and actual measurements without server files/DB records.

The phone commits accepted results locally and returns localSaveAcknowledged with the same candidate ID. Duplicate responses cannot create duplicate local files/catalog entries. If the phone cannot save, display LOCAL_SAVE_FAILED/DEVICE_STORAGE_FULL and do not move the accepted baseline forward.

In mounted mode, confirm corners and detect alignment loss. In handheld mode, show actual board tracking confidence, hold-steady guidance and recalibration requests. Do not display a fixed polygon over a moving phone as if it were valid tracking.

When disconnected or the user declines frame transmission, local video, manual photos, lecture notes, local playback and PDF creation still work. Full automatic OpenCV/YOLO filtering needs a reachable analysis service in this release. Moving inference onto the phone is required before claiming fully offline AI or that no frame ever leaves the device.

No private lecture history, thumbnails, per-lecture analytics or OCR text is sent to GraphQL/telemetry. No cloud-backup switch is included. Community screens must not offer automatic lecture attachment/transcript publication.

## 8. Website, user pages and admin pages

### Native/mobile user screens

- Local library: real device lectures, search, storage usage, recording status and explicit imports/exports.
- Lecture detail: locally stored images/video/notes, source timestamps, manual/automatic labels and local events.
- Capture: preview, rear-camera selection, recording, manual/automatic capture, calibration/tracking, stop/pause and save destination.
- Local player: playback without server/network, recovered recording segments and honest decode errors.
- Local storage: actual local usage, save failures, gallery/files permissions, user-controlled cleanup and export.
- Account/device enrollment: login/security and connected-analysis access, without media upload.
- Help/community: published platform content and deliberate user-written posts/comments.

### Website

Next.js provides public information, account pages, FAQs/community and a browser-local library for explicitly selected files/web captures. On desktop, files belong to that user's device; the website cannot show a phone's private library merely because the same account logs in. Import/export is explicit.

A PWA fallback can keep on-device browser data and offer downloads. Show quota/persistence status, use OPFS/IndexedDB for files rather than localStorage, and do not label browser storage as guaranteed native Photos/Gallery persistence.

### Admin

Admin can manage users, roles/status, authentication sessions, enrolled devices, FAQs/announcements, community moderation/reports, platform audit and service health.

Remove admin pages for all-user lecture galleries, private capture previews, media archives, per-user recording storage quotas, server exports and remote device-file deletion. The admin UI must say private recordings stay on users' devices. Backend authorization still protects every platform action.

## 9. Native permissions, phone storage and privacy

Ask only for permissions needed by the chosen action: camera, optional microphone, add-to-library/document destination. Prefer restricted add/export flows over broad access to unrelated photos/files.

Bundle mobile assets locally and use typed native adapters. Access/refresh tokens use secure OS storage; private notes do not go into analytics, support bundles or notification payloads.

App data is not automatically cleared on login refresh/account changes. Maintain separate local profiles/ownership labels if multiple users share one phone. Do not make a fresh server login falsely imply that it can restore a phone-local library onto another device.

Use native free-space checks and actual filesystem errors. The PWA fallback must request browser persistence and show quota/eviction limitations. Long recordings need chunked/native I/O, not unbounded JS memory. Photo/document shares are initiated by the user and use the OS chooser; the app never uploads to our media server because no such endpoint exists.

No frontend service worker caches private frames in cloud/CDN services. No screenshot/session-replay analytics during capture. Exports into other apps or system backup behavior are the user's choices, not hidden developer media synchronization.

## 10. Shared server contract and local repository interface

Shared server routes:

| Route | Use |
| --- | --- |
| POST /auth/signup, /auth/login, /auth/refresh, /auth/logout | Platform identity |
| GET /auth/me, /auth/csrf | Validated identity/browser CSRF |
| POST /graphql | Accounts, enrollment, published help/community and admin |
| POST /analysis/access | Short-lived transient-analysis permission |
| WSS /ws/analyze | Ephemeral frames/results/local-save acknowledgments |
| WSS /ws/control | Device/account control without lecture data |
| GET /health/live, /health/ready | Service readiness |

There is no /uploads/videos, server media gallery, private lecture CRUD API, server export archive or lecture-sync service.

GraphQL lists are { items, page, pageSize, total }; generate operation types from a versioned schema. Website uses secure-cookie/CSRF transport. Mobile uses its reviewed native secure credential adapter. Never ship server secrets.

The shared frontend local-library interface owns createLecture, listLectures, saveCapture, start/stopRecording, addNote, createPdf, exportBundle, importBundle and deleteLocalItems. Native and browser adapters implement it locally. These are not GraphQL mutations.

Stable server errors: UNAUTHENTICATED, FORBIDDEN, VALIDATION_ERROR, DEVICE_REVOKED, ANALYSIS_BUSY, VISION_UNAVAILABLE. Local errors include DEVICE_STORAGE_FULL, LOCAL_SAVE_FAILED, PERMISSION_DENIED and FILE_MISSING. Handle locally deleted gallery files honestly rather than fetching a nonexistent server backup.

## 11. Development order and tests

| Phase | Build | Required proof |
| --- | --- | --- |
| F1 Local storage foundation | Mobile target, SQLite migrations, file/media adapters and local-library contracts. | Save an actual image on a physical phone, kill/reopen app, open it with no backend. |
| F2 Recording and recovery | Native video, thumbnails, manual snapshots, local notes and recovery. | Record/play locally offline; test process interruption and disk-full handling. |
| F3 Website/account/content | Next layouts, typed platform API, auth, user/admin/help/community. | Account and publication flows work without introducing lecture uploads. |
| F4 Connected AI | Transient analysis, mounted/handheld guidance, local commit/ack and retry idempotence. | Real analysis produces a locally saved image while backend retains no lecture content. |
| F5 Exports/imports | Local PDF, Files/Photos integration and local backup bundles. | Export actual bytes; import bundle onto another selected device without our server. |
| F6 Production readiness | Permissions, privacy checks, native signing/builds, browser fallback and real-device QA. | Record results for actual Android/iPhone devices; do not substitute desktop emulation. |

Test filesystem write/finalize failures, SQLite/file reconciliation, duplicate candidates, local deletion, gallery permissions, interrupted recordings, no-network capture/playback, app restart, logout/account blocking without file loss, import/export integrity and actual free-space handling.

Verify users can find saved originals/exports in the documented app/native destination. Test uninstall behavior separately for app-owned and exported media. The UI must distinguish “saved in app,” “saved to Photos/Files,” “analysis pending,” “analysis unavailable” and “save failed.”

Platform E2E tests cover roles/IDOR, FAQs, community publishing/moderation, credentials and enrollment. Privacy tests inspect network requests to ensure no full video, local catalog, OCR or PDF upload and verify the server-side no-retention report.

## 12. Migration and definition of done

Existing development-Mac data is not already on a phone. Offer a local export bundle from the old application for explicit import into the mobile client, preserving actual files/timestamps/notes/checksums. Do not ingest old lectures into the new backend database.

Completion requires real recordings and notes to be saved on a physical user's phone by default, readable after app restart and backend shutdown, with appropriate native Files/Photos integration and honest permission/error states. The platform backend must have no retained lecture copy. Changes to plans do not implement this behavior in the current MVP.

Deliver both website and mobile source targets, reusable local-library/storage adapters, lockfiles, generated contracts, native setup/signing instructions, tested device matrix, privacy tests and a clear user guide about where every file is saved.
