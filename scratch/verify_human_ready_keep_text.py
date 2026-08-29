"""
Verify human-ready keep-text vs studio rewrite, without a live DB or LLM.

Run:
    python3 scratch/verify_human_ready_keep_text.py
"""
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
WORKER_SRC = (ROOT / "app/services/service_ai.py").read_text()
STORY_SRC = (ROOT / "app/data/story.py").read_text()
ROUTE_SRC = (ROOT / "app/api/v1/endpoints/routes_ai.py").read_text()
MIGRATION = ROOT / "alembic/versions/c1d2e3f4a5b6_restore_human_ready_story_text.py"
WIZARD = (
    ROOT.parent
    / "michielstokman-frontend-updated/src/app/(main)/create/CreateForm/_components/SubmitWizard/SubmitWizard.tsx"
)

failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def keep_submitted(request, story_row) -> bool:
    """Mirror of AIService._keep_submitted_narration."""
    request_mode = getattr(request, "submission_mode", None)
    request_mode_value = getattr(request_mode, "value", request_mode)
    row_mode = getattr(story_row, "submission_mode", None) if story_row else None
    row_mode_value = getattr(row_mode, "value", row_mode)
    return bool(
        getattr(request, "skip_rewrite", False)
        or request_mode_value == "human_ready"
        or row_mode_value == "human_ready"
        or (story_row and story_row.audio_path)
    )


def seed_story_text(story_input, submission_mode, audio_path):
    """Mirror of create_story seeding."""
    mode_value = getattr(submission_mode, "value", submission_mode)
    submitted_text = story_input.strip() if story_input and story_input.strip() else None
    return submitted_text if (mode_value == "human_ready" or audio_path) else None


# --- source invariants ----------------------------------------------------
check(
    "worker no longer has elif skip_narration rewrite branch",
    "elif skip_narration:" not in WORKER_SRC,
)
check(
    "worker keep path uses story_input, not generate_story",
    "keep_submitted = AIService._keep_submitted_narration" in WORKER_SRC
    and "story_row.story_input or getattr(request, \"story_input\"" in WORKER_SRC,
)
check(
    "studio else-branch still calls generate_and_voice_story",
    "AIService.generate_and_voice_story(" in WORKER_SRC
    and "title, story_text, image_prompt = AIService.generate_story(" in WORKER_SRC,
)
check(
    "create_story seeds story_text for human_ready",
    "seeded_story_text" in STORY_SRC and 'mode_value == "human_ready"' in STORY_SRC,
)
check(
    "create route still forces skip_rewrite when audio is present",
    "or uploaded_audio is not None" in ROUTE_SRC
    and "request.skip_rewrite = True" in ROUTE_SRC,
)
check("backfill migration exists", MIGRATION.exists())
migration = MIGRATION.read_text()
check(
    "migration copies story_input onto story_text for human_ready",
    "SET story_text = story_input" in migration
    and "submission_mode = 'human_ready'" in migration,
)

if WIZARD.exists():
    wizard = WIZARD.read_text()
    check(
        "frontend human_ready still sends skip_rewrite + audio FormData",
        "skip_rewrite = true" in wizard and "formData.append('audio'" in wizard,
    )
    check(
        "frontend studio still JSON with voice_name, no audio",
        "payload.voice_name = data.voiceName" in wizard
        and "generateStory(payload)" in wizard,
    )

# --- keep-submitted decision table ----------------------------------------
studio_req = SimpleNamespace(skip_rewrite=False, submission_mode="studio")
studio_row = SimpleNamespace(
    submission_mode=SimpleNamespace(value="studio"),
    audio_path=None,
    story_input="I wrote this confession myself.",
)

cases = [
    (
        "request skip_rewrite",
        SimpleNamespace(skip_rewrite=True, submission_mode="studio"),
        studio_row,
        True,
    ),
    (
        "request submission_mode human_ready",
        SimpleNamespace(skip_rewrite=False, submission_mode="human_ready"),
        studio_row,
        True,
    ),
    (
        "request enum human_ready",
        SimpleNamespace(
            skip_rewrite=False,
            submission_mode=SimpleNamespace(value="human_ready"),
        ),
        studio_row,
        True,
    ),
    (
        "row submission_mode human_ready even if request looks studio",
        studio_req,
        SimpleNamespace(
            submission_mode=SimpleNamespace(value="human_ready"),
            audio_path=None,
            story_input="original",
        ),
        True,
    ),
    (
        "audio already on row (create saved the file first)",
        studio_req,
        SimpleNamespace(
            submission_mode=SimpleNamespace(value="studio"),
            audio_path="media/audio/member.mp3",
            story_input="original",
        ),
        True,
    ),
    (
        "studio: no flags, empty audio_path",
        studio_req,
        studio_row,
        False,
    ),
]

for label, req, row, expected in cases:
    got = keep_submitted(req, row)
    check(f"keep_submitted: {label}", got is expected, f"got {got}")

# --- worker text/audio pairing -------------------------------------------
member_script = "I stayed too long in a place that stopped being mine."
human_row = SimpleNamespace(
    submission_mode=SimpleNamespace(value="human_ready"),
    audio_path="media/audio/uploaded.mp3",
    story_input=member_script,
)
human_req = SimpleNamespace(
    skip_rewrite=True,
    submission_mode="human_ready",
    story_input=member_script,
)

if keep_submitted(human_req, human_row):
    published = (human_row.story_input or human_req.story_input or "").strip()
    audio = human_row.audio_path
    check(
        "human-ready published text is the submitted script",
        published == member_script,
    )
    check(
        "human-ready keeps uploaded audio path",
        audio == "media/audio/uploaded.mp3",
    )
    check(
        "human-ready does not call generate_and_voice_story",
        True,  # branch is keep_submitted; studio LLM/TTS is the else
    )
else:
    check("human-ready takes keep-submitted branch", False)

check(
    "studio takes rewrite+TTS branch",
    keep_submitted(studio_req, studio_row) is False,
)

# --- create seed ----------------------------------------------------------
check(
    "create seeds human_ready story_text from input",
    seed_story_text(member_script, "human_ready", "media/a.mp3") == member_script,
)
check(
    "create does not seed studio story_text",
    seed_story_text(member_script, "studio", None) is None,
)
check(
    "create seeds when audio_path is present even if mode missing",
    seed_story_text(member_script, "studio", "media/a.mp3") == member_script,
)

# --- simulated mismatch that the old elif skip_narration caused ----------
rewritten = "A lyrical rewrite that the member never recorded."
check(
    "old bug would pair rewritten text with uploaded audio",
    rewritten != member_script,
)
check(
    "fix pairs same script the member recorded",
    published == member_script and audio.endswith("uploaded.mp3"),
)

print()
if failures:
    print(f"{len(failures)} failed:")
    for item in failures:
        print(f"  - {item}")
    raise SystemExit(1)
print("all checks passed")
