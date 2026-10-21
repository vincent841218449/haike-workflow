# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Accepted Haike design and scope (2026-10-13)

- Company is 海客科技. Reuse the official logo, brand tokens and native shared navigation copied into src/vendor. The sidebar stays 242px; its six entries are 图文视频、数字人口播、创作任务、资源库、发布日历、API设置. Match menu geometry across every route.
- User selected the first redesign on 2026-10-13: ../../docs/ui/component-redesign-20261013/selected-design.png. Use the compact content editor on the left, reference preview on the right, and sticky bottom actions. Keep actual functionality and three avatar templates; reuse buttons, fields, uploads, empty states and native modal dialogs across every route. On narrow viewports the reference preview is a disclosure.
- Sound sources are mutually exclusive. Uploaded audio triggers no TTS; switching source/template preserves assets. Template1/2 posters are layout illustrations, template3 plays an existing real sample, never a newly generated user result.
- This is now the frontend of the actual workbench at 4188, backed by /api/studio/*. Drafts/assets persist on the server; browser IndexedDB only remembers the last avatar project. Paid quotes, budget caps and native queue production are connected. No supplier or customer Key belongs in browser storage.
- Keep original template3 baseline immutable. New parameterized avatar rendering belongs to templates/studio-avatar-v1 with its own version. Graphic uses the native safe_v2 nine-second/three-scene layout.
- Publication is through real CreatorHub receipts: future times, Beijing display, approved final version, owned/authorized sources, title/description/cover and live account checks. Save a draft first, activate only on explicit user confirmation. Unknown results reuse the original idempotency key; partial cancellation stays visible and recoverable.
- No real paid call or external publish during automated validation. Local outputs remain pending user review. Unconfirmed procurement prices must block the relevant capability.

## Accepted unified avatar flow (2026-10-13)

- Use one「选择模板」dialog for basic3 and ADu styles, preserving script, voice/audio, portrait and uploaded materials. The professional manual editor remains an optional deeper entry.
- User materials have must/prefer/reference intent and an explicit usage/AI-analysis rights checkbox. AI previews are content suggestions, with no invented seconds. Final timing uses original ASR sentence timestamps; display subtitle wrapping must not become the storyboard clock.
- New gpt-6-luna / gpt-image-2 features are currently merchant-sponsored trials, with customer charge0 and unknown procurement cost. Keep supplier credentials exclusively in ignored backend configuration; do not package them for customers. Native TTS/avatar/ASR keep their separate commercial quotes and caps.
- Douyin/MediaCrawler precedes Pexels. The user declares Douyin candidate usage rights by default (2026-10-15): automatically acquire and analyze candidates without a per-video selection or rights prompt. AI checks actual representative frames against scene goals and decides adoption; login/network failures preserve the recovery point and original job. Details: ../../docs/PRODUCT_AI_STORYBOARD.md.

## Accepted voice library flow (2026-10-14)

- System and account-owned personal voices share one library/picker, with audition available in both. Video selection preserves script and assets and saves the specific immutable voice ID. Changes to the default voice do not retarget saved selections.
- Clone through Alibaba Bailian after recording rights and cost confirmation; create is free, first synthesized audition has its own quote. Cache successful auditions for repeated playback. Label reference recording playback separately from synthesized audition.
- For voice cloning, account permissions, unknown task recovery or migrating existing voices, read ../../docs/PRODUCT_VOICE_LIBRARY.md before changing the contract.

## Accepted simple avatar flow (2026-10-15)

- The default form has script, voice, portrait and optional image/video materials. Fresh projects start with empty user content, voice synthesis and automatic storyboarding. Show the template picker above these fields; keep layout, uploaded audio and manual storyboard controls under optional settings.
- 「制作视频」saves inputs, reads the commercial quote and enqueues once within the fee cap displayed beside the button, then opens `/tasks?task=<job_id>`. Material rights use one collective checkbox. No required preview or confirmation dialog; over-budget quotes stop without increasing the cap. Unknown submissions preserve their revision/quote and recover the original task, including after refresh.
- New-project voice defaults must be usable with the live model capabilities; preserve explicit saved selections and distinguish audition-only voices. Persist only asset metadata, keeping browser File/Blob objects local. Repeated saves and refreshes must preserve the original media URL.
- Four input cards use real readiness and inline errors; material multi-select keeps the four-item/80MB limits and preserves partial successful uploads. Keep local-only verification and service limitations explicit; current flow and evidence: ../../docs/PRODUCT_AVATAR_SIMPLE_UI.md.

- Keep the default system voice list at 7 curated Alibaba Bailian presets in `../../api-platform/platform_app/bailian_system_voices.json`, with free official auditions. Do not expand the list without user direction. Existing personal voices retain their original model and identity.
- Present voices with generic system/personal labels and style tags. Auditions use a persistent local cache, background warm-up and versioned browser-cache URLs. Supplier attribution stays in backend provenance and recording-transfer consent rather than voice badges or player labels.
- Deploy and validate locally first. Cloud rollout and gateway synchronization require fresh explicit user authorization after local validation.

## Accepted task center and template selection (2026-10-15)

- Use the supplied hkglobal.ai/tasks screenshot as the task-list visual target: warm surfaces, orange selection, two filter rows, continuous task rows with original script excerpt, ratio, status and observed progress. Statistics come from actual local tasks.
- Creation tasks own playback, version selection, download, review and publishing-material preparation. `/projects` is a compatibility redirect to `/tasks`, preserving the work query. The former standalone works page and navigation entry are removed; retain the underlying work/version APIs and media.
- A task opens the version it produced, with its actual media ratio. Task summaries use the frozen submission, even when the editable draft changes. An acknowledged active schedule applies only to its exact video version.
- The always-visible template entry opens basic and motion catalogs with previews. Choosing a template saves the choice and preserves script, voice/audio, portrait and uploaded materials. Previewing existing demos makes no paid generation call.

## Accepted automatic recovery (2026-10-15)

- Lock the user's selected visual style through saving, frozen input, planning, rendering and the task receipt. Automatic adaptation stays within that style; incompatible content preserves the selection and completed artifacts. Never replace a selected motion template with a basic circle layout by default. Project sample recordings are audition-only.
- New motion selections must freeze the real package/contract/engine reference and execute its official workflow. The old self-written instrument adapter is only for frozen historical requests. MotionGit 612 uses the verified personal 2.5.2 package: native recipe or official console components, selected from the whole script and actual audio. Show the actual route and version in tasks; do not claim components reproduce fixed native choreography or that uninstalled MotionGit packages are ready. Keep semantic and visual checks internal, preserve paid artifacts, and expose engineering downloads for the exact completed version.
- Narration footage should dominate the frame, with subject-aware enlargement; screenshots and evidence retain important information. Review every scene, material meaning, crop, captions and presenter overlap before delivery. A decodable file alone does not establish viewing quality. Actual case and checks: ../../docs/tasks/2026-10-15-media-framing-review.md.
- A template-only edit of an existing creation continues its explicit task family and reuses matching narration/avatar/materials. Local-only recomposition must refuse new chargeable stages when artifacts are missing.
- Routine material decisions and intermediate checks run automatically. Require input only for missing/contradictory content, explicit new paid regeneration, or raising the aggregate fee cap. Provider waits query the original intent; pending billing receipts do not block returned media.
- One explicitly linked creation occupies one task row; preserve exact historical attempts and video versions in a collapsed history. Playback and download need no review click. Preparing publication requires selecting one exact version; actual publication retains its existing explicit authorization.

## Accepted portrait catalog (2026-10-21)

- The creation picker shows every official MotionGit 9:16 identity, using the official Chinese name, cover and full playable author example. Use the public media CDN published by the catalog/detail page; preserve its source link. Local test presenters belong to acceptance evidence, not official examples.
- Keep sample identity separate from the frozen executable package/version. Official playback does not enable unverified production. Track the remaining native choreography, media slot and delivery gaps in `../../docs/tasks/2026-10-21-studio-integration-acceptance.md` until actual outputs pass.
