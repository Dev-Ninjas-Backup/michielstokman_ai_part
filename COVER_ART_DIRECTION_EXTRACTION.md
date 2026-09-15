# Cover-image art-direction extraction (current)

Read-only snapshot of the confession cover pipeline as of 2026-09-08, updated 2026-09-15 for the complete-story portrait analysis. Line numbers refer to `michielstokman_ai_part` on the then-current tree.

**Production path (since 2026-09-15):** `COVER_GENERATION_METHOD=template` + `OPENAI_IMAGE_MODEL=gpt-image-2`. The sections below document the **legacy full-collage path** (still reachable via `COVER_GENERATION_METHOD=dalle`); see §0 for the live template/portrait pipeline.

Python does **not** slice art direction by `story_type`. Grok always receives all three type specs in one block and is told to follow the spec that matches the story type.

---

## 0. Template pipeline — portrait for the photo hole (production)

`app/utils/story_cover.py` routes confession + meditation stories to the HTML
`cover_template` path when `COVER_GENERATION_METHOD=template`:

```
Complete Confession/Meditation (stories.story_text, ≤8,000 chars)
  → build_portrait_story_brief      (story_image_prompt.py — Grok @ 0.35)
      receives: story type, title, hero hook, tags, situation, background,
                age/gender/location, and the COMPLETE story text (no excerpt cap)
      returns:  concise labeled visual brief
        Emotional register / Setting / Atmosphere / Distinctive visuals / Do not invent
  → build_portrait_only_prompt      (story_image_prompt.py)
      brief + narrative moment + confession-vs-meditation ENERGY + cast/intimacy/pose
      + shared ENVIRONMENT + framing + anti-repetition + BRAND + ANTI-AI + LOOK
      → portrait-only prompt (~1,000 words; explicit no-text/no-typography/no-badges/
        no-frame/no-collage constraint; story-specific blocks first)
  → generate_ai_cover_image         (image_generator.py → OpenAI gpt-image-2, 1024x1536)
  → render_cover_png_sync           (cover_template/render.py — Playwright 2160×2160;
      portrait is injected as photoUrl data-URI into the torn-photo hole)
  → S3; stories.image_source = template_v1
```

Key behaviors:

- **Complete-story analysis**: the Grok brief call receives the full `story_text`
  (no 3,500-char excerpt since 2026-09-15). The *brief* — never the full story —
  is passed to the image model.
- **Type-aware wording**: confession vs meditation energy comes from
  `CONFESSION_COVER_ENERGY` / `MEDITATION_COVER_ENERGY` constants, and all analysis
  layers (`brief_story_mood_scene`, `portrait_emotional_state`,
  `portrait_narrative_moment`, `portrait_cast_instruction`) are type-aware — no
  "confession" wording appears in meditation prompts.
- **Fallback**: Grok failure or missing `XAI_API_KEY` degrades to the type-aware
  regex heuristic (`portrait_story_analysis`), logged via
  `Portrait brief path=heuristic|llm reason=...` (story content is never logged).
- **Prompt budgeting**: `gpt-image-*` models accept long prompts — no trimming.
  `dall-e-*` still budgets to ≤4,000 chars (`_portrait_prompt_char_limit`,
  story-specific blocks keep priority; boilerplate drops first).
- **Identity lock, template chrome, typography, badges, Playwright rendering, S3
  flow, member-upload guard: unchanged** from before; the portrait is data-in,
  photo-hole only.

---

## 1. Complete instructions given to Grok for `IMAGE_PROMPT`

### 1.1 `_cover_art_direction()` — `app/utils/story_image_prompt.py` 42–48

```python
def _cover_art_direction(story: Story) -> str:
    from app.utils.prompts import STORY_HUMAN_TEMPLATE, cover_identity_template_vars

    raw = STORY_HUMAN_TEMPLATE.split("IMAGE_PROMPT:", 1)[1].split("STORY:", 1)[0].strip()
    return raw.format(
        **cover_identity_template_vars(story.first_name, story.gender, story.location)
    )
```

### 1.2 `cover_identity_template_vars()` — `app/utils/prompts.py` 243–253

```python
def cover_identity_template_vars(
    first_name: Optional[str] = None,
    gender: Optional[str] = None,
    location: Optional[str] = None,
) -> dict[str, str]:
    """Values bound into STORY_HUMAN_TEMPLATE IMAGE_PROMPT and P2 art direction."""
    return {
        "cover_author_name": (first_name or "").strip() or "Anonymous",
        "cover_gender": (gender or "").strip() or "unspecified",
        "cover_location": (location or "").strip() or "unspecified",
    }
```

### 1.3 `STORY_HUMAN_TEMPLATE` source — `app/utils/prompts.py` 167–197

```python
STORY_HUMAN_TEMPLATE = (
    "Write the {story_type} now using all the rules above.\n"
    "Make it so personal, raw and true that the reader thinks: “This could have been written by me.”\n\n"
    "IMPORTANT: You MUST write the final story, title, and image prompt entirely in English, regardless of the input language. Under no circumstances should any part of the output contain non-English words.\n\n"
    "IMPORTANT: You MUST format your response exactly like this:\n"
    "TITLE: [Your beautiful title here]\n"
    "IMAGE_PROMPT: [Write a unique, highly descriptive DALL-E 3 image prompt to generate a full scrapbook collage cover for this story. The prompt must describe the entire collage layout, including the background, stickers, title text, narrator's portrait, and metadata tags. Follow these design specs based on the story type:\n"
    "1. For CONFESSIONS:\n"
    "   - Background: warm paper texture and blush pink with hot pink splatters.\n"
    "   - Left side: a prominent pink banner sticker saying 'CONFESSION' in bold white letters.\n"
    "   - Top right: a black brush stroke label saying 'PRIVATE' (or 'SECRET' if needed for safety moderation) in red handwritten capital letters.\n"
    "   - Center: bold, eye-catching 3D block letters for the title '[INSERT GENERATED TITLE HERE]' featuring distressed cream-white faces, thick black outlines, and a dramatic hot pink offset drop-shadow, styled with a retro magazine cutout look.\n"
    "   - Bottom: a torn piece of tape saying '[INSERT AUTHOR NAME HERE]' in handwritten marker text next to the corresponding country flag and country name in typewriter font.\n"
    "   - Bottom left: a circular pink stamp featuring a black sketched anatomical heart with a keyhole in the center.\n"
    "   - Right side: a cropped vertical rectangular photo of the narrator or a close-up scene styled in a moody pink duotone filter with a cinematic vignette, taped down with masking tape. The scene in the photo must dynamically depict a single character (the narrator alone) in a warm, evocative mood matching the story's setting. You MUST NOT describe more than one character. Keep the portrait or photo strictly singular, depicting only the narrator alone. Never include multiple people, couples, or physical interactions between characters. The portrait must feel candid and real, capturing a strong sense of emotion and presence rather than a wholesome pose. To prevent OpenAI safety moderation blocks, you MUST NOT describe nudity, bare skin, shoulders, collarbones, lingerie, silk slips, or physical touch. Instead, describe the narrator in elegant, stylish clothing, such as a cozy knit sweater, a simple shirt, or a high-collar jacket. Examples of dynamic concepts to describe based on the story: a close-up of a narrator's face with messy hair, closed eyes, and a soft, thoughtful expression; a narrator sitting by a window in a dimly lit room looking out at the city lights; a close-up of the narrator's hands holding a warm mug or a letter; or a close-up of a wine glass with a delicate reflection. Use purely safe, atmospheric, and aesthetic descriptors (e.g., cozy sweater, simple shirt, closed eyes, soft lighting, warm shadows, cinematic duotone, candid capture) to capture a highly moody and intimate look without triggering safety blocks.\n"
    "2. For MEDITATIONS:\n"
    # (full text in §1.4 / §2.2)
    "3. For TRANSFORMATIONS:\n"
    # (full text in §1.4 / §2.3)
    "Write the prompt as a single continuous paragraph, dynamically substituting the actual generated title. The tape text MUST read exactly: {cover_author_name}. The portrait MUST depict a {cover_gender} person. The setting should match {cover_location}. Never invent a different author name. Do not include any words that might trigger safety moderation filters. Specifically, you MUST NEVER use these banned words: \"sensual\", \"passionate\", \"passion\", \"erotic\", \"desire\", \"alluring\", \"ecstasy\", \"explicit\". Describe the mood and visual scene using purely safe, aesthetic, and atmospheric terms instead (e.g., \"candid capture\", \"warm candlelit glow\", \"glowing warm lighting\", \"soft shadows\", \"closed eyes\", \"head tilted back\", \"messy hair\", \"deep focus\"). Keep the prompt under 120 words.]\n"
    "STORY:\n"
    "[The full text of the story here]"
)
```

The truncated `#` comments above are only in this heading block. The joined string in §1.4 is the complete text `_cover_art_direction` extracts.

### 1.4 Joined IMAGE_PROMPT art-direction (exact extract, before `.format`)

This is the string between `IMAGE_PROMPT:` and `STORY:` in `STORY_HUMAN_TEMPLATE`:

```
[Write a unique, highly descriptive DALL-E 3 image prompt to generate a full scrapbook collage cover for this story. The prompt must describe the entire collage layout, including the background, stickers, title text, narrator's portrait, and metadata tags. Follow these design specs based on the story type:
1. For CONFESSIONS:
   - Background: warm paper texture and blush pink with hot pink splatters.
   - Left side: a prominent pink banner sticker saying 'CONFESSION' in bold white letters.
   - Top right: a black brush stroke label saying 'PRIVATE' (or 'SECRET' if needed for safety moderation) in red handwritten capital letters.
   - Center: bold, eye-catching 3D block letters for the title '[INSERT GENERATED TITLE HERE]' featuring distressed cream-white faces, thick black outlines, and a dramatic hot pink offset drop-shadow, styled with a retro magazine cutout look.
   - Bottom: a torn piece of tape saying '[INSERT AUTHOR NAME HERE]' in handwritten marker text next to the corresponding country flag and country name in typewriter font.
   - Bottom left: a circular pink stamp featuring a black sketched anatomical heart with a keyhole in the center.
   - Right side: a cropped vertical rectangular photo of the narrator or a close-up scene styled in a moody pink duotone filter with a cinematic vignette, taped down with masking tape. The scene in the photo must dynamically depict a single character (the narrator alone) in a warm, evocative mood matching the story's setting. You MUST NOT describe more than one character. Keep the portrait or photo strictly singular, depicting only the narrator alone. Never include multiple people, couples, or physical interactions between characters. The portrait must feel candid and real, capturing a strong sense of emotion and presence rather than a wholesome pose. To prevent OpenAI safety moderation blocks, you MUST NOT describe nudity, bare skin, shoulders, collarbones, lingerie, silk slips, or physical touch. Instead, describe the narrator in elegant, stylish clothing, such as a cozy knit sweater, a simple shirt, or a high-collar jacket. Examples of dynamic concepts to describe based on the story: a close-up of a narrator's face with messy hair, closed eyes, and a soft, thoughtful expression; a narrator sitting by a window in a dimly lit room looking out at the city lights; a close-up of the narrator's hands holding a warm mug or a letter; or a close-up of a wine glass with a delicate reflection. Use purely safe, atmospheric, and aesthetic descriptors (e.g., cozy sweater, simple shirt, closed eyes, soft lighting, warm shadows, cinematic duotone, candid capture) to capture a highly moody and intimate look without triggering safety blocks.
2. For MEDITATIONS:
   - Background: aged yellow-green cardboard with dark grunge borders, using warm paper, butter yellow, and sage green tones.
   - Top left: black tape label saying 'MEDITATION' in white letters, next to a sketched green heart doodle.
   - Main title on the left: large 3D butter-yellow block letters for the title '[INSERT GENERATED TITLE HERE]' with a thick black outline and dark sage-green/charcoal drop-shadows.
   - Right side: a vertical rectangular sepia-toned vintage photo of the narrator taped down at the corners, slightly larger. The narrator (based on gender) must be dynamically depicted in a deeply serene, sensual, and intimate mindful moment that fits the specific meditation setting. You MUST NOT describe more than one character. Keep the portrait or photo strictly singular, depicting only the narrator alone. Never include multiple people, couples, or physical interactions between characters. Write a detailed description of this scene, selecting from these highly sensual, intimate concepts based on the meditation: (1) a portrait of a person sitting on a bed by a sunlit window, wearing a loose knit cardigan or sweater that gently slips off one bare shoulder, with closed eyes, head tilted up in quiet bliss, and warm light filtering in to cast delicate slatted shadow lines across their bare shoulder, neck, and collarbones; or (2) a portrait of a person with a messy high bun, closed eyes, and a serene, deeply feeling expression, resting a hand gently on their chest/sternum to feel their breathing, wearing a simple thin-strap top that exposes their neck and collarbones, bathed in soft, dappled light and delicate leaf shadows. Ensure the description uses highly evocative, sensory, and artistic descriptors (e.g., bare shoulder, loose knit cardigan, hand resting on chest, head tilted back, soft sunbeams, slatted shadows, vintage warm sepia tone) to capture a highly sensual, intimate, and serene atmosphere while keeping it fully compliant with safety filters.
   - Bottom left: themes listed ('PRESENCE', 'BREATH', 'HEALING', 'SLEEP') next to hand-drawn icons.
   - Bottom right: a torn yellow note saying 'DURATION 3 MIN' (or '[INSERT DURATION HERE]').
3. For TRANSFORMATIONS:
   - Background: aged dark purple cardboard with grunge borders, using soft lavender, periwinkle, and dusty violet tones.
   - Top left: purple tape label saying 'TRANSFORMATION' in white letters.
   - Center-left: large 3D block letters for the title '[INSERT GENERATED TITLE HERE]' featuring periwinkle/white faces and deep violet-purple drop-shadows.
   - Right side: a vertical rectangular photo of the narrator styled in a deep purple duotone filter, taped down with masking tape. The scene must dynamically depict the narrator in an emotional, free, and highly sensual moment of release and self-realization. You MUST NOT describe more than one character. Keep the portrait or photo strictly singular, depicting only the narrator alone. Never include multiple people, couples, or physical interactions between characters. Write a detailed description of this scene, selecting from these highly sensual, liberating concepts based on the transformation: (1) a person standing tall with their head tilted back, eyes closed, hair flowing dynamically in the wind, holding a sheer, flowing purple fabric or robe that blows dramatically around their body against a cloudy sunset sky; or (2) a person dancing freely in warm evening sunset light, back arched, arms outstretched, wearing a thin, flowing lavender dress, capturing a powerful feeling of physical liberation, sensory awakening, and self-acceptance. Ensure the description uses highly evocative, sensory, and artistic descriptors (e.g., arched back, sheer flowing fabric, wind-blown hair, head tilted back, dramatic sunset, purple duotone filter, high-contrast soft shadows) to capture a highly sensual, raw, and liberating mood while keeping it fully compliant with safety filters.
Write the prompt as a single continuous paragraph, dynamically substituting the actual generated title. The tape text MUST read exactly: {cover_author_name}. The portrait MUST depict a {cover_gender} person. The setting should match {cover_location}. Never invent a different author name. Do not include any words that might trigger safety moderation filters. Specifically, you MUST NEVER use these banned words: "sensual", "passionate", "passion", "erotic", "desire", "alluring", "ecstasy", "explicit". Describe the mood and visual scene using purely safe, aesthetic, and atmospheric terms instead (e.g., "candid capture", "warm candlelit glow", "glowing warm lighting", "soft shadows", "closed eyes", "head tilted back", "messy hair", "deep focus"). Keep the prompt under 120 words.]
```

After `.format()`:

| Placeholder | Bound from | Fallback if empty |
|---|---|---|
| `{cover_author_name}` | `story.first_name` / request first name | `Anonymous` |
| `{cover_gender}` | `story.gender` / request gender | `unspecified` |
| `{cover_location}` | `story.location` / request location | `unspecified` |

`[INSERT GENERATED TITLE HERE]`, `[INSERT AUTHOR NAME HERE]`, and `[INSERT DURATION HERE]` stay until `substitute_cover_placeholders` runs.

### 1.5 P1 (story generation) — `app/services/service_ai.py` 184–195

```python
        chat_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(system_template),
            HumanMessagePromptTemplate.from_template(STORY_HUMAN_TEMPLATE),
        ])

        formatted_messages = chat_prompt.format_prompt(
            user_context=user_context,
            story_type=request.story_type.value,
            **cover_identity_template_vars(
                request.first_name, request.gender, request.location
            ),
        ).to_messages()
```

P1 system prompt also includes `BASE_PERSONA` (`app/utils/prompts.py`):

- Line 33: write title, image prompt, and story in English.
- Line 43, Rule 9: narrative names may vary; **cover art author-name tape must use the submitted name**.
- Lines 48–49, Rule 19–20: English-only title / story / image prompt.

P1 temperature: `settings.LLM_TEMPERATURE_STORY` (default `0.85`). Model: `settings.LLM_MODEL` (default `grok-3`) via `get_story_llm()`.

### 1.6 P2 (rebuild from finished story) — `app/utils/story_image_prompt.py` 51–84

Used when story generation did not return `IMAGE_PROMPT:`, or when `force_rebuild=True`.

```python
def build_image_prompt_from_story(story: Story) -> str:
    """Ask the LLM for a story-specific DALL-E prompt after generation completes."""
    excerpt = (story.story_text or "")[:STORY_EXCERPT_CHARS]
    input_excerpt = (story.story_input or "")[:INPUT_EXCERPT_CHARS]
    tags = ", ".join(story.tags or [])
    growth = ", ".join(story.growth_areas or [])

    llm = get_story_llm(temperature=0.8)
    response = llm.invoke(
        "You write image prompts for cover artwork. Return only the prompt text, "
        "with no preamble and no quotes.\n\n"
        f"Story type: {story.story_type.value}\n"
        f"Title: {story.title or 'Untitled'}\n"
        f"Name: {story.first_name or 'Anonymous'}\n"
        f"Location: {story.location or 'unspecified'}\n"
        f"Gender: {story.gender or 'unspecified'}\n"
        f"Sexual orientation: {story.sexual_orientation or 'unspecified'}\n"
        f"Occupation: {story.occupation or 'unspecified'}\n"
        f"Age: {story.age if story.age is not None else 'unspecified'}\n"
        f"Background: {story.background or 'unspecified'}\n"
        f"Personality: {story.personality or 'unspecified'}\n"
        f"Lifestyle: {story.lifestyle or 'unspecified'}\n"
        f"Situation: {story.situation or 'unspecified'}\n"
        f"Themes/tags: {tags or 'none'}\n"
        f"Growth areas: {growth or 'none'}\n\n"
        f"Art direction:\n{_cover_art_direction(story)}\n\n"
        f"Member's original submission:\n{input_excerpt}\n\n"
        f"Narrated story:\n{excerpt}\n\n"
        "The cover scene must visually reflect THIS specific story — its setting, "
        "mood, and symbols. Do not describe a generic stock scene. "
        f"The tape text MUST read exactly: {story.first_name or 'Anonymous'}. "
        f"The portrait MUST depict a {story.gender or 'unspecified'} person."
    )
    return response.content.strip()
```

`STORY_EXCERPT_CHARS = 6000`, `INPUT_EXCERPT_CHARS = 1500`. P2 temperature is hardcoded `0.8`.

### 1.7 Placeholder substitution — `app/utils/story_image_prompt.py` 24–39

Runs on Grok output before store / DALL-E.

```python
def substitute_cover_placeholders(
    prompt: str,
    *,
    title: str,
    author_name: str,
) -> str:
    """Replace template tokens the story LLM may leave in the IMAGE_PROMPT."""
    replacements = {
        "[INSERT GENERATED TITLE HERE]": title.strip() or "Untitled",
        "[INSERT AUTHOR NAME HERE]": author_name.strip() or "Anonymous",
        "[INSERT DURATION HERE]": "3 MIN",
    }
    result = prompt
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result.strip()
```

### 1.8 Identity lock (Python, not Grok) — `app/utils/image_generator.py` 138–151

Prepended immediately before the DALL-E payload. **Not** stored on `stories.image_prompt`.

```python
def prepend_cover_identity_lock(
    prompt: str,
    *,
    author_name: str,
    gender: str | None,
) -> str:
    """Prefix the DALL-E prompt with a short identity lock Grok cannot overwrite."""
    name = (author_name or "").strip() or "the author"
    gender_label = (gender or "").strip() or "person"
    lock = f"The person depicted MUST be {name}, a {gender_label}."
    stripped = (prompt or "").strip()
    if stripped.startswith("The person depicted MUST be "):
        return stripped
    return f"{lock} {stripped}".strip()
```

Stored column comment (`app/model/story.py` 119–120): resolved DALL-E prompt is **post-placeholder, pre identity lock**. Not public.

---

## 2. Per-`story_type` art-direction blocks

`STORY_TYPE_INSTRUCTIONS` in `prompts.py` 109–150 is narration only (word count, `<break>` tags, POV). Cover layout is not there.

Shared for every type (always in the art-direction string):

- Full scrapbook collage: background, stickers, title text, narrator portrait, metadata tags
- Single continuous paragraph
- Keep under 120 words
- Tape text = `{cover_author_name}`
- Portrait = `{cover_gender}` person
- Setting = `{cover_location}`
- Never invent a different author name
- Banned **output** words: `"sensual"`, `"passionate"`, `"passion"`, `"erotic"`, `"desire"`, `"alluring"`, `"ecstasy"`, `"explicit"`
- Singular narrator only (also repeated inside each type block)

### 2.1 Confession — `prompts.py` 174–181

```
1. For CONFESSIONS:
   - Background: warm paper texture and blush pink with hot pink splatters.
   - Left side: a prominent pink banner sticker saying 'CONFESSION' in bold white letters.
   - Top right: a black brush stroke label saying 'PRIVATE' (or 'SECRET' if needed for safety moderation) in red handwritten capital letters.
   - Center: bold, eye-catching 3D block letters for the title '[INSERT GENERATED TITLE HERE]' featuring distressed cream-white faces, thick black outlines, and a dramatic hot pink offset drop-shadow, styled with a retro magazine cutout look.
   - Bottom: a torn piece of tape saying '[INSERT AUTHOR NAME HERE]' in handwritten marker text next to the corresponding country flag and country name in typewriter font.
   - Bottom left: a circular pink stamp featuring a black sketched anatomical heart with a keyhole in the center.
   - Right side: a cropped vertical rectangular photo of the narrator or a close-up scene styled in a moody pink duotone filter with a cinematic vignette, taped down with masking tape. The scene in the photo must dynamically depict a single character (the narrator alone) in a warm, evocative mood matching the story's setting. You MUST NOT describe more than one character. Keep the portrait or photo strictly singular, depicting only the narrator alone. Never include multiple people, couples, or physical interactions between characters. The portrait must feel candid and real, capturing a strong sense of emotion and presence rather than a wholesome pose. To prevent OpenAI safety moderation blocks, you MUST NOT describe nudity, bare skin, shoulders, collarbones, lingerie, silk slips, or physical touch. Instead, describe the narrator in elegant, stylish clothing, such as a cozy knit sweater, a simple shirt, or a high-collar jacket. Examples of dynamic concepts to describe based on the story: a close-up of a narrator's face with messy hair, closed eyes, and a soft, thoughtful expression; a narrator sitting by a window in a dimly lit room looking out at the city lights; a close-up of the narrator's hands holding a warm mug or a letter; or a close-up of a wine glass with a delicate reflection. Use purely safe, atmospheric, and aesthetic descriptors (e.g., cozy sweater, simple shirt, closed eyes, soft lighting, warm shadows, cinematic duotone, candid capture) to capture a highly moody and intimate look without triggering safety blocks.
```

Confession-specific:

- Palette: warm paper, blush pink, hot pink splatters, cream-white title faces, red handwritten `PRIVATE`/`SECRET`
- Layout: pink `CONFESSION` banner (left); `PRIVATE` brush label (top right); 3D retro magazine-cutout title (center); torn tape + flag + country (bottom); circular pink heart-with-keyhole stamp (bottom left); cropped vertical photo, pink duotone, cinematic vignette, masking tape (right)
- Style refs: scrapbook collage, retro magazine cutout, torn tape, handwritten marker, typewriter, sketched anatomical heart
- Typography in the prompt: bold white letters; red handwritten capitals; 3D block letters with thick black outlines and hot pink offset drop-shadow; handwritten marker; typewriter font
- Banned in the portrait: nudity, bare skin, shoulders, collarbones, lingerie, silk slips, physical touch
- Required clothing examples: cozy knit sweater, simple shirt, high-collar jacket
- Few-shot scene examples: messy-hair face close-up; sitting by a window looking at city lights; hands holding a mug or letter; wine glass with reflection

### 2.2 Meditation — `prompts.py` 182–188

```
2. For MEDITATIONS:
   - Background: aged yellow-green cardboard with dark grunge borders, using warm paper, butter yellow, and sage green tones.
   - Top left: black tape label saying 'MEDITATION' in white letters, next to a sketched green heart doodle.
   - Main title on the left: large 3D butter-yellow block letters for the title '[INSERT GENERATED TITLE HERE]' with a thick black outline and dark sage-green/charcoal drop-shadows.
   - Right side: a vertical rectangular sepia-toned vintage photo of the narrator taped down at the corners, slightly larger. The narrator (based on gender) must be dynamically depicted in a deeply serene, sensual, and intimate mindful moment that fits the specific meditation setting. You MUST NOT describe more than one character. Keep the portrait or photo strictly singular, depicting only the narrator alone. Never include multiple people, couples, or physical interactions between characters. Write a detailed description of this scene, selecting from these highly sensual, intimate concepts based on the meditation: (1) a portrait of a person sitting on a bed by a sunlit window, wearing a loose knit cardigan or sweater that gently slips off one bare shoulder, with closed eyes, head tilted up in quiet bliss, and warm light filtering in to cast delicate slatted shadow lines across their bare shoulder, neck, and collarbones; or (2) a portrait of a person with a messy high bun, closed eyes, and a serene, deeply feeling expression, resting a hand gently on their chest/sternum to feel their breathing, wearing a simple thin-strap top that exposes their neck and collarbones, bathed in soft, dappled light and delicate leaf shadows. Ensure the description uses highly evocative, sensory, and artistic descriptors (e.g., bare shoulder, loose knit cardigan, hand resting on chest, head tilted back, soft sunbeams, slatted shadows, vintage warm sepia tone) to capture a highly sensual, intimate, and serene atmosphere while keeping it fully compliant with safety filters.
   - Bottom left: themes listed ('PRESENCE', 'BREATH', 'HEALING', 'SLEEP') next to hand-drawn icons.
   - Bottom right: a torn yellow note saying 'DURATION 3 MIN' (or '[INSERT DURATION HERE]').
```

Meditation vs confession:

- No `CONFESSION` banner, `PRIVATE` label, heart-keyhole stamp, flag/country tape, or pink duotone
- Palette: aged yellow-green cardboard, butter yellow, sage green, grunge borders, vintage sepia photo
- Portrait **requires** (as few-shot concepts) bare shoulder / collarbones / thin-strap top — the opposite of the confession shoulders/collarbone ban
- Extra chrome: `PRESENCE` / `BREATH` / `HEALING` / `SLEEP` + hand-drawn icons; torn yellow duration note

### 2.3 Transformation — `prompts.py` 189–193

```
3. For TRANSFORMATIONS:
   - Background: aged dark purple cardboard with grunge borders, using soft lavender, periwinkle, and dusty violet tones.
   - Top left: purple tape label saying 'TRANSFORMATION' in white letters.
   - Center-left: large 3D block letters for the title '[INSERT GENERATED TITLE HERE]' featuring periwinkle/white faces and deep violet-purple drop-shadows.
   - Right side: a vertical rectangular photo of the narrator styled in a deep purple duotone filter, taped down with masking tape. The scene must dynamically depict the narrator in an emotional, free, and highly sensual moment of release and self-realization. You MUST NOT describe more than one character. Keep the portrait or photo strictly singular, depicting only the narrator alone. Never include multiple people, couples, or physical interactions between characters. Write a detailed description of this scene, selecting from these highly sensual, liberating concepts based on the transformation: (1) a person standing tall with their head tilted back, eyes closed, hair flowing dynamically in the wind, holding a sheer, flowing purple fabric or robe that blows dramatically around their body against a cloudy sunset sky; or (2) a person dancing freely in warm evening sunset light, back arched, arms outstretched, wearing a thin, flowing lavender dress, capturing a powerful feeling of physical liberation, sensory awakening, and self-acceptance. Ensure the description uses highly evocative, sensory, and artistic descriptors (e.g., arched back, sheer flowing fabric, wind-blown hair, head tilted back, dramatic sunset, purple duotone filter, high-contrast soft shadows) to capture a highly sensual, raw, and liberating mood while keeping it fully compliant with safety filters.
```

Transformation vs confession:

- Palette: dark purple cardboard, lavender, periwinkle, dusty violet, purple duotone
- Label is `TRANSFORMATION` tape, not `CONFESSION` / `PRIVATE`
- No heart stamp, flag/country, or duration note
- Portrait few-shots: wind-blown sheer fabric against sunset; dancing in a thin flowing lavender dress, arched back — not the confession covered-shoulder rule

### 2.4 Disabled Pillow overlay (not live)

`compose_cover_image` in `image_generator.py` 61–136 draws Playfair Display title/subtitle and a Spotify logo. The call is commented out at 224–225 (`# composed_bytes = compose_cover_image(...)`). Live covers are the raw DALL-E image uploaded to S3.

---

## 3. DALL-E API parameters — `app/utils/image_generator.py` 191–208

```python
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        model = settings.OPENAI_IMAGE_MODEL or "dall-e-3"
        size = "1024x1792" if model.startswith("dall-e") else "1024x1536"

        payload = {
            "model": model,
            "prompt": dalle_prompt,
            "n": 1,
            "size": size
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=180)
```

`OPENAI_IMAGE_MODEL` — `app/core/config.py` (updated 2026-09-15):

```python
        self.OPENAI_IMAGE_MODEL: str = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
```

Production sets `OPENAI_IMAGE_MODEL=gpt-image-2`, so `size` is `1024x1536` and no
`style` parameter is sent. dall-e models additionally send `"style": "natural"`
and are prompt-budgeted to ≤4,000 chars (see §0).

| Field | Set in payload? | Value |
|---|---|---|
| `model` | yes | `settings.OPENAI_IMAGE_MODEL` or `"dall-e-3"` |
| `prompt` | yes | identity lock + Grok paragraph |
| `n` | yes | `1` |
| `size` | yes | `"1024x1792"` for `dall-e*`, else `"1024x1536"` |
| `quality` | **no** | OpenAI default (`standard` for DALL-E 3) |
| `style` | **no** | OpenAI default (`vivid` for DALL-E 3) |
| `response_format` | **no** | OpenAI default (`url`) |
| `user` | **no** | omitted |

Pillow `final_img.save(..., quality=90)` exists only inside unused `compose_cover_image`.

---

## 4. Editable without a code deploy?

**Art-direction copy is code-only.** There is no CMS, admin prompt editor, or database table for the collage spec. Changing cover layout/palette/banned elements requires editing `app/utils/prompts.py` and deploying.

| Surface | What it stores | Edits art-direction text? |
|---|---|---|
| `app/utils/prompts.py` `STORY_HUMAN_TEMPLATE` | The collage spec | Yes (deploy required) |
| `stories.image_prompt` | Per-story **resolved Grok output**, not the template. Not on public/member/admin API schemas | No |
| `cover_images` (`app/model/cover_image.py`) | Admin-uploaded fallback JPEGs per type | No — images only |
| `POST /v1/admin/photos` | Upload those fallbacks | No |
| `POST /v1/admin/stories/regenerate-covers` | Re-runs the same Grok + DALL-E path | No |
| `OPENAI_IMAGE_MODEL` env | DALL-E model name | Model/size only |
| `LLM_MODEL` / `LLM_TEMPERATURE_STORY` env | Which Grok + P1 temperature | Not the collage spec |
| Frontend | No `IMAGE_PROMPT` / collage strings | No |

---

## 5. Recent resolved `image_prompt` examples sent to DALL-E

**None available from the extraction environment.**

- Local Postgres (`localhost:5432`) refused connections, so `stories.image_prompt` could not be read.
- No app log files in the repo containing `Generating OpenAI background` (that log line in `image_generator.py` 189 prints the **lock-prefixed** DALL-E string).
- Tests only use stubs (`"stored collage with [INSERT AUTHOR NAME HERE]"`, `"a scrapbook collage"`), not live Grok output.

Structural shape of the live DALL-E `prompt`:

```
The person depicted MUST be {first_name}, a {gender}. {Grok IMAGE_PROMPT paragraph}
```

If gender is empty the lock uses `a person.` The stored `stories.image_prompt` column is the Grok paragraph **without** that prefix.

To pull 2–3 real confession examples from production:

```sql
SELECT id, title, first_name, gender, location, image_prompt, created_at
FROM stories
WHERE image_prompt IS NOT NULL
  AND btrim(image_prompt) <> ''
  AND story_type::text ILIKE '%confession%'
ORDER BY COALESCE(updated_at, created_at) DESC
LIMIT 3;
```

Migration that added the column: `alembic/versions/j0k1l2m3n4o5_add_story_image_prompt.py`.
