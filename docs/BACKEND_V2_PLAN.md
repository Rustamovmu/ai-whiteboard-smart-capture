# Backend plan: device-owned whiteboard recordings

Status: revised planning specification. This replaces the earlier server-primary plan. It does not describe the existing single-user implementation, which still stores files on the development Mac.

Companion: [FRONTEND_V2_PLAN.md](FRONTEND_V2_PLAN.md). Keep two separate repositories: whiteboard-backend and whiteboard-frontend.

## 1. Mandatory storage rule

**Every private lecture recording and derived file belongs on the recording user's personal device. Our server and our database must not persist any of it.**

This covers videos, audio if enabled, original/enhanced pictures, thumbnails, lecture titles, notes, OCR text, PDFs, calibration, capture histories and comparison baselines. There is no automatic server copy, media archive, cloud backup, lecture synchronization or server upload library.

MongoDB remains appropriate for platform accounts, authentication sessions, device enrollment, administrator permissions, FAQs, announcements, intentionally published community posts/comments and platform moderation. It must not contain private lectures, lecture-media references, extracted text or per-lecture capture statistics.

The mobile device may use its own SQLite database for its local lecture catalog. That database is physically on the user's device and is separate from our backend MongoDB.

Administrators manage the platform and its published data. They cannot browse, download or remotely delete private recordings that remain on a user's phone.

## 2. Delivery and stack

The stronger device-storage requirement changes the earlier PWA-only recommendation. Keep a Next.js website for account/help/community/admin access and an optional browser/PWA client. Add a native-capable React/Capacitor mobile target for persistent phone files, long recordings and OS Files/Photos integration. Both targets live in the frontend repository and share contracts/UI where appropriate.

| Responsibility | Technology |
| --- | --- |
| Platform API | NestJS, TypeScript, Node.js 24 |
| Business operations | GraphQL with Nest Apollo integration |
| Platform database | MongoDB Community + Mongoose |
| Identity | Argon2id passwords, short-lived access tokens, rotating/revocable refresh sessions |
| Optional connected analysis | Private Python/FastAPI service with OpenCV, NumPy, scikit-image, YOLO11n |
| Transport | HTTPS/WSS and authenticated HTTP |
| Proxy | Caddy, configured without lecture-body logging or disk spooling |
| Tests | Jest, Nest testing utilities, Supertest, actual WebSocket clients, Pytest |
| Local infrastructure | Docker Compose or documented native MongoDB setup |
| Inspection | Postman and MongoDB Compass |

Use current compatible supported releases and pin tested dependency versions. Follow the Nestar/TripLink module/resolver/service/DTO/schema/guard organization, not its unrelated property/tour business logic. Redis, object storage and media CDNs are unnecessary. A local single-node MongoDB replica set supports required multi-document platform transactions but is not high availability. [MongoDB transactions](https://www.mongodb.com/docs/manual/core/transactions/)

## 3. What stays local and what can reach the backend

| Item | Device storage | Backend storage |
| --- | --- | --- |
| Lecture video/audio | Persistent native files | Prohibited |
| Original/enhanced captures and thumbnails | Persistent native files | Prohibited |
| Lecture title, notes, OCR and capture history | Local SQLite/files | Prohibited |
| PDF/ZIP exports | Generated and saved locally | Prohibited |
| Analysis baseline and calibration | Local files/SQLite; optional active-worker RAM copy | No persistent copy |
| Selected frame for connected AI | Device owns original; temporary transmitted copy | RAM-only processing, if user enables connected analysis |
| User/account/login/device enrollment | Token in platform secure storage | MongoDB, containing no lecture content |
| FAQs/announcements | Optional read cache | Published platform content in MongoDB |
| Community posts/comments | Optional read cache | Only intentionally published general community content |

“No server storage” is different from “nothing leaves the phone.” Connected Python analysis sends selected frames to our first-party service temporarily. Before enabling it, explain this in the UI. No full video or audio upload is necessary. Disable connected analysis when the user declines; local recording and manual capture still work.

If the requirement later becomes zero transmission of lecture frames, OpenCV/person detection must also run on the device. That is a separate on-device inference implementation, not something the current Python backend can claim to provide.

## 4. Backend repository structure

    whiteboard-backend/
      apps/api/
        src/
          main.ts
          app.module.ts
          config/
          database/
          common/
            guards/
            decorators/
            validation/
            filters/
          modules/
            auth/
            members/
            device-enrollment/
            analysis-access/
            help-center/
            community/
            reports/
            admin/
            audit/
            health/
        test/
      services/vision/
        app/
          main.py
          contracts/
          vision/
            calibration.py
            tracking.py
            quality.py
            motion.py
            change_detection.py
            person_detection.py
            decision_engine.py
          transient/
            session_registry.py
            frame_processor.py
        tests/
        requirements.txt
        requirements-lock.txt
      contracts/
        schema.graphql
        live-protocol.md
        storage-policy.md
        errors.md
      scripts/
        create-admin.ts
        setup-models.py
        backup-platform.ts
        restore-platform.ts
      infra/
        compose.yaml
        Caddyfile
      docs/
      .env.example
      package.json
      package-lock.json
      README.md
      AGENTS.md

There are deliberately no server lecture/media/upload/export-archive modules. Do not adapt the old filesystem Store into a new server-side lecture database. Reuse the vision algorithms through a new transient adapter.

## 5. Platform database

Allowed collections:

- users: normalized unique email, name, password hash, USER/ADMIN role, account status and timestamps.
- authSessions: hashed refresh credentials, expiry, rotation family and revocation.
- authAttempts: expiring rate-limit records.
- devices: account, enrollment label/type, revocation and account-related last activity; no recording paths or lecture titles.
- pairingRequests: expiring hashed single-use enrollment codes, without lecture content.
- helpEntries: FAQ/announcement, title, body, topic, draft/published state, order and author.
- communityPosts/communityComments: explicitly published text, author and moderation state.
- reports: community/platform report, reason and moderation outcome.
- auditEvents: administrator/account actions without lecture payloads or recording-derived content.
- platformSettings: enrollment/auth/content settings and non-content processing limits.

Forbidden collections/fields include lectures, recordings, captures, thumbnails, baselines, OCR text, media URLs, private note text, frame bytes and private per-lecture processing history.

Index unique email; paginate lists; index publication/status/date queries; expire temporary token/rate records. Keep platform IDs separate from device-local lecture/capture UUIDs. The backend does not need the local lecture UUID to perform a frame analysis: use an ephemeral random stream ID.

MongoDB/filesystem backups contain only platform data, approved static branding and model/configuration files. They must not accidentally scoop up development lecture folders or production worker memory dumps.

## 6. Authentication and admin authority

- Public signup creates USER accounts only. Bootstrap ADMIN through a local explicit CLI; no default credentials or “first registrant becomes admin.”
- Access tokens last 15 minutes; refresh sessions have a maximum 30-day lifetime and rotate/revoke server-side.
- The website uses Secure/HttpOnly/same-site cookies with CSRF/origin checks. Native mobile refresh credentials use iOS Keychain/Android Keystore-backed secure storage, never ordinary SQLite/localStorage. Specify the distinct native/browser transports in the contract.
- Verify current account role/status on protected requests. Revoke active connected-analysis streams when a device/account loses access.
- Rate-limit authentication, enrollment, analysis requests and community publishing. Validate and whitelist DTOs.
- Admin can manage accounts, access permissions, enrolled devices, published FAQs/announcements, community moderation/reports and platform service health.
- Protect the last active administrator from deletion/demotion.
- Audit role changes, account blocking, enrollment revocation, help publishing and moderation. Do not log raw frames, OCR, personal lecture names or token values.
- Blocking/logout revokes backend access, not ownership of existing local files. It must not trigger a remote wipe.
- Admin has no “view all recordings,” “download user lecture,” or “clear phone storage” API.
- Recovery is an admin-assisted reset/local recovery CLI until real email delivery is implemented.

Public community publishing is a separate intentional action. V1 accepts general text posts/comments and does not support recorded-lecture attachments, automatic transcript publication or “share lecture to community.”

## 7. RAM-only connected analysis contract

1. Phone creates a local lecture and persistent local destination before opening analysis.
2. After authentication, the backend grants a short-lived, stream-scoped analysis permission. No lecture record is created in MongoDB.
3. Phone sends selected compressed JPEG frames, capped at 2 MB and 16 million decoded pixels, with an ephemeral stream ID, frame ID and monotonic/source timestamp.
4. Nest forwards validated bytes directly to Python in memory. Keep one in-flight frame and a bounded queue; apply backpressure rather than saving a backlog.
5. Python calculates calibrated/tracked board coordinates, quality, motion/stability, actual person boxes/overlap, SSIM and pixel/edge/ink changes.
6. For an accepted candidate, return actual rectified/enhanced image bytes plus calculated measurements to the phone. Keep the candidate only in bounded RAM until acknowledged/expired.
7. The phone writes the images and local metadata, verifies the local save, and sends localSaveAcknowledged with the same candidate ID. Only the phone may show “Saved on this phone.”
8. Worker advances its comparison baseline after that acknowledgment. Lost messages/retries are resolved against the device's idempotent local catalog, not a server capture archive.
9. Phone owns the durable baseline. After reconnect/worker restart it can resend the required baseline with permission; reset temporal stability.
10. Clear stream/candidate buffers on disconnect, logout, revocation or a 30-second inactivity timeout. Limit active sessions and measure actual memory use.

Default analysis targets remain five sampled frames per second, approximately two seconds of stability and a three-second capture interval. Fresh YOLO inference must gate automatic candidates when available. A stationary detected obstruction still blocks saving.

Mounted and handheld modes differ: fixed corners work only for a stable camera. Handheld mode uses OpenCV tracking/homography confidence gates, suppresses automatic capture when tracking fails, and asks the user to hold steady/recalibrate. Keep person coordinates in raw-frame space and comparisons in rectified space.

No automatic server persistence is allowed for a failed/slow mobile save. Return an error or drop the transient result; never “helpfully” retain an image.

## 8. Enforcing no retained lecture content

Apply the policy beyond application code:

- Remove video multipart-upload, lecture-media download, server replay archive, server PDF-export and media-backup endpoints from the planned public API.
- No multipart parsers, proxy request buffering to disk, temporary image files, disk-backed task queues or cache entries for analysis frames.
- Disable request/response body logging, debug image output, APM payload capture, tracing attachments and exception serialization of frames/results.
- Disable process core dumps/automatic memory-dump uploads for analysis services. Review host swap, crash reporting and memory snapshots before describing a deployment as having strict physical RAM-only handling.
- Do not send lecture data to third-party analytics, AI services, error monitoring or storage.
- Cache only model weights/configuration and public application resources server-side.
- Do not store private OCR or lecture results in background-job records. Any connected OCR is bounded RAM-only processing; otherwise defer OCR to device processing.
- Caddy/Nest/Python health and performance reporting uses non-content, aggregate operational information. Do not build a persistent recording timeline from per-frame telemetry.
- Enforce no-store headers on transient analysis HTTP responses. WebSocket payloads must not be captured by support logs.
- A server restart loses active analysis state; this is expected. Originals and metadata remain on the device.

Do not advertise connected analysis as zero transmission or absolute OS-level non-retention without validating the hosting configuration. The mandatory application contract is no retained lecture copy; users who disallow transmission must use local capture/on-device analysis.

## 9. Shared API and events

Both plan documents use these routes:

| Transport | Routes / purpose |
| --- | --- |
| Auth HTTP | POST /auth/signup, /auth/login, /auth/refresh, /auth/logout; GET /auth/me, /auth/csrf |
| GraphQL | POST /graphql: accounts, enrollment, published help/community and admin operations only |
| Analysis authorization | POST /analysis/access: short-lived stream permission, not a media upload |
| Frame processing | WSS /ws/analyze: bounded ephemeral frames, results and local-save acknowledgments |
| Enrollment/status | WSS /ws/control: device/account control, no private lecture feed |
| Health | GET /health/live, /health/ready |

There is no public media library, lecture-sync endpoint, recording database API or full-video upload endpoint.

GraphQL lists return { items, page, pageSize, total }. Expose stable errors: UNAUTHENTICATED, FORBIDDEN, VALIDATION_ERROR, DEVICE_REVOKED, ANALYSIS_BUSY and VISION_UNAVAILABLE. DEVICE_STORAGE_FULL and LOCAL_SAVE_FAILED are local frontend errors, not claims that our server saves the files.

Analysis messages use protocolVersion, streamId, frameId, candidateId where applicable, dimensions, source time and actual computed results. Local titles, note text, filesystem paths and permanent lecture IDs are unnecessary in live analysis messages. Do not use query-string tokens. Version/schema files and generated types must agree between repositories.

## 10. Deployment, migration and operations

Deploy the website/API wherever appropriate; media still saves on the user's device. The server's physical location no longer determines the lecture library location. Keep internal Python/MongoDB private; expose only authenticated HTTPS/WSS entry points.

Local development defaults: Next.js 3000, NestJS 4000, Python 8100 and MongoDB 27017. Explicitly enable LAN HTTPS for physical phone tests. A phone must reach a trusted HTTPS address; its localhost is not the computer. Internet-hosted service deployment uses public HTTPS but must keep the same no-retention analysis policy.

Models are downloaded explicitly from documented legitimate sources, cached and loaded once on CPU. No CUDA or paid cloud API is required. Missing AI is honest: manual recording/capture remains available, while connected auto-analysis is unavailable/degraded.

Existing development-Mac captures must not be silently uploaded into production. Provide a local export bundle for the user to import onto their phone: original files, checksums, notes and timestamps. Keep the original directory untouched. The new backend has no lecture importer that stores those files in MongoDB/server media folders.

Platform DB backups/restores are tested separately from a user's local export/restore. Document startup, shutdown, platform admin recovery, model setup, retention checks and safe test-data isolation.

## 11. Build order and acceptance

| Phase | Work | Acceptance gate |
| --- | --- | --- |
| B1 Policy/contracts | Lock the no-media-persistence contract; repository/config/test setup. | Forbidden endpoint/collection list and cross-project contract tests exist. |
| B2 Platform identity | MongoDB accounts, sessions, roles, enrollment and admin bootstrap. | Current-account guards, revocation and role/IDOR tests pass. |
| B3 Phone storage proof, coordinated with frontend | Define candidate/local-ack flow; no server lecture Store. | Device can record/save/read a real image with backend unavailable. |
| B4 Transient vision | Adapt existing Python algorithms to memory-only inputs/results and recoverable client baselines. | A real frame is analyzed without any server file/DB content record. |
| B5 Published platform content | FAQ/announcement CRUD, community/comments/reports and admin management. | Admin publishes; normal user reads; rejected operations are tested. |
| B6 Reliability/privacy | Limits, cleanup, restart/failure tests, network/log/disk audits and documentation. | Successful, failed and interrupted analysis leaves no retained lecture content. |

Test normal and malicious inputs, actual MongoDB permissions, authentication rotation/revocation, ephemeral session TTL, memory bounds, duplicate local acknowledgments, tracking/quality/occlusion and real model inference.

Privacy acceptance must inspect server database collections, working directories, temporary directories, logs, caches and backup outputs after processing distinctive synthetic content. Test slow client, failed local save, client disconnect and worker crash. Confirm no fallback server save occurs. Use a separate synthetic/real-model test protocol; do not claim physical classroom accuracy from a rectangle fixture.

## 12. Completion definition

Backend success means authenticated users receive useful analysis and platform/admin functionality while every private lecture byte and durable lecture record remains on their own device. Accounts/content survive a server restart; private recordings survive a device-app restart independently of that server.

Deliver contracts, source, lockfiles, setup/stop commands, environment template, tests, a privacy-retention report and honest model/phone-validation limits. No new application implementation or server restart is authorized by this planning document alone.
