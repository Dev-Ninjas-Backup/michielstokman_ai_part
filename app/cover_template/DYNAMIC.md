# Cover template — Dynamic Content Guide

Pixel-perfect HTML/CSS cover (`2160×2160`) in `app/cover_template/`. Fields update via `Cover.set()` (see `cover.js`). Preview: `GET/POST /v1/test/cover-template-preview` (non-production).

## Quick start

```js
Cover.set({
  gender: "male",
  orientation: "homosexual",
  age: 31,
  author: "Alex",
});

Cover.get(); // current values
```

API / preview payload names map as: `description` → confession, `author_name` → author, `title` / `subtitle` newline-split into line1/line2.

## Text limits (empirically measured)

Counts include spaces. Prefer **soft**; never exceed **hard**.

Measured 2026-09-12 against the **current** template (post clip-path / torn-border / badge layout fixes) by progressive `Cover.set` renders in Playwright at 2160×2160, scoring:

- single-line fields wrapping to a second line
- chip label past badge / past canvas edge
- confession bottom into `.location` (or ≥5 wrap lines)
- city/country block into the photo hole

| Field | Soft (best look) | Hard (safe max) | Notes |
| --- | --- | --- | --- |
| Title line 1 | 10–14 | **14** | Edo brush, uppercase. Soft-wrap long titles; photo stacks above so glyphs do not paint over the torn edge. |
| Title line 2 | 9–14 | **14** | Same as line 1. |
| Subtitle line 1 | 12–14 | **14** | Pink Edo @ 80px in the 558px column (stops before photo torn edge @ 670). |
| Subtitle line 2 | 12–14 | **14** | Same as subtitle line 1. Pink underline is also 558px. |
| Confession (`description`) | 45–58 | **77** | Outfit 70px in a 663px box. Soft ≈ **3 lines** with ≥40px gap above location. Hard = last length before confession bottom crosses location top (**78** overlaps pin). |
| City | 8–12 | **20** | One visual line (Cover appends `, `). Longer strings push location text into the photo hole (~21+). |
| Country | 5–10 | **21** | One line under city. Breaks ~22 when location text enters the photo. |
| Author (`author_name`) | 4–11 | **16** | Chip grows **left** from `right: 24px`, `max-width: 720px`. ≥8 chars → `is-long` (76px); ≥11 (`Bartholomew`) → `is-xlong` (62px). **16** still inside the badge; **17** spills past chip bg (and often past canvas). |
| Age | 2 | **3** | Chip is fixed 380px. Digits through 5 still fit geometrically; treat **3** as product max (`28` ideal; avoid `100+`). |
| Gender | 4–6 | **12** | `male` / `female` only for icon+shape assets (unknown → female artwork). Label alone can go longer; keep ≤12 so the meta row stays balanced with a long orientation. |
| Orientation | 8–11 | **16** | `bisexual` / `homosexual` soft. `heteroflexible` (**14**) comfortable (≈42px canvas clearance). `heteroflexiblexx` (**16**) last safe; **17** overflows the 2160 canvas. Extremely wide synthetic glyphs (`w`×14) can fail earlier — real orientation words through 16 are OK. |

### Hard-limit boundary screenshots

Still acceptable (not broken) at the hard limit:

| Field | Chars | Fixture | Image |
| --- | --- | --- | --- |
| `author_name` | 16 | `BartholomewXXXXX` | [docs/text_limits/hard_author_name_16ch.png](docs/text_limits/hard_author_name_16ch.png) |
| `orientation` | 16 | `heteroflexiblexx` | [docs/text_limits/hard_orientation_16ch.png](docs/text_limits/hard_orientation_16ch.png) |
| `description` | 77 | padded confession copy | [docs/text_limits/hard_description_77ch.png](docs/text_limits/hard_description_77ch.png) |

### Rules of thumb

- Badge labels (gender, orientation, age, author) stay **one line** — no wrapping (`white-space: nowrap`).
- Split long titles/subtitles across the two lines; do not put 15+ chars on a single title line.
- Author over 16 chars spills out of the purple chip; the chip is right-anchored so names expand toward the photo, not off the right edge — until they overflow the chip itself.
- Confession soft target is the default three-line sample (~57 chars). Four lines are possible up to 77; five lines collide with location.

## `Cover.set()` fields

| Key | Example | Effect |
| --- | --- | --- |
| `titleLine1` / `titleLine2` | `"TO WASTELAND"` | Main purple title |
| `subtitleLine1` / `subtitleLine2` | `"A NIGHT THAT"` | Pink subtitle |
| `confession` | `"A confession about…"` | Body copy (wraps in box) |
| `city` / `country` | `"BARCELONA"`, `"SPAIN"` | Location |
| `author` / `role` | `"Lisa"`, `"author"` | Author chip |
| `age` | `28` or `"28"` | Orange age chip |
| `gender` | `"female"` \| `"male"` | Swaps label + icon asset. Unknown values fall back to `female` (only two Figma assets exist). |
| `orientation` | `"bisexual"` \| `"homosexual"` \| `"heteroflexible"` | Label; chip widens / shrinks font if long (`is-long` ≥10, `is-xlong` ≥12) |
| `explicit` | `true` \| `"explicit"` \| `null` \| `false` | Truthy shows `.chip--explicit`; `null` / `false` / `""` hides it. |

Same values can be set on `#cover` via `data-*` attributes.

## How these numbers were measured

Reproducible harness (scratch, not shipped):

```bash
.venv/bin/python scratch/measure_cover_text_limits_v2.py
```

Uses the same static `index.html` + `Cover.set` path as `/v1/test/cover-template-preview`. Limits above are from geometry at render time, then spot-checked on PNG screenshots at the hard boundary.
