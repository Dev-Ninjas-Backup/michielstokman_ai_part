"""
scratch/ingest_to_pinecone.py
Directly embeds and upserts catalog stories, meditations, and liberation journeys
into the Pinecone 'stories-rag' index using the native 1024-dim inference API.
"""
import re
import json
from pinecone import Pinecone
from app.core.config import settings
from app.services.service_rag import PineconeInferenceEmbeddings, _get_pinecone_index

def clean_narrative(story_text: str) -> str:
    lines = [l.strip() for l in story_text.split("\n") if l.strip()]
    narrative_lines = []
    for line in lines[1:]:
        if line.startswith("**") and any(x in line for x in ["Story by", "M /", "F /", "hetero", "bi", "trans", "Word count"]):
            continue
        elif line.startswith("(") and "Word count" in line:
            continue
        elif any(line.endswith(suffix) for suffix in ["– 18–25", "– 25–35", "– 35–47", "– 47–60", "– 60+"]):
            continue
        else:
            narrative_lines.append(line)
    return "\n\n".join(narrative_lines)

def load_stories():
    with open("scratch/docx_content.txt", "r", encoding="utf-8") as f:
        text = f.read()

    story_matches = list(re.finditer(r"\*\*Story (\d+)\b", text))
    story_configs = [
        {
            "id": "story-028-lars",
            "title": "The Night She Took the Lead",
            "first_name": "Lars",
            "story_type": "confession",
            "tags": ["confidence", "letting go", "surrender", "intimacy"],
            "life_phase": "Discovering freedom and releasing fear in intimacy",
            "match_idx": 1
        },
        {
            "id": "story-132-joanna",
            "title": "Back to the Current",
            "first_name": "Joanna",
            "story_type": "confession",
            "tags": ["overwhelmed", "quiet", "stillness", "renewal"],
            "life_phase": "Returning to calm after deep overwhelm and burnout",
            "match_idx": 4
        },
        {
            "id": "story-136-jonas",
            "title": "Contact with the Trees",
            "first_name": "Jonas",
            "story_type": "meditation",
            "tags": ["grounded", "body", "deep breath", "nature", "presence"],
            "life_phase": "Grounding bodily awareness through nature and stillness",
            "match_idx": 5
        },
        {
            "id": "story-201-desiree",
            "title": "Growing Toward the Light",
            "first_name": "Desiree",
            "story_type": "transformation",
            "tags": ["finding inner confidence", "healing", "growth", "light"],
            "life_phase": "Overcoming morning anxiety and finding steady inner strength",
            "match_idx": 7
        },
        {
            "id": "story-204-jasna",
            "title": "The First Time We Shared",
            "first_name": "Jasna",
            "story_type": "confession",
            "tags": ["heartbreak", "letting go", "vulnerability", "acceptance"],
            "life_phase": "Healing from relationship heartbreak and learning to share again",
            "match_idx": 8
        }
    ]

    docs = []
    for conf in story_configs:
        idx = conf["match_idx"]
        start = story_matches[idx].start()
        end = story_matches[idx+1].start() if idx+1 < len(story_matches) else len(text)
        story_raw = text[start:end]
        narrative = clean_narrative(story_raw)

        doc_text = f"Title: {conf['title']}\nType: {conf['story_type']}\nLife Phase: {conf['life_phase']}\nTags: {', '.join(conf['tags'])}\nStory: {narrative[:1500]}"
        docs.append({
            "id": conf["id"],
            "text": doc_text,
            "metadata": {
                "doc_type": "story",
                "story_id": conf["id"],
                "story_type": conf["story_type"],
                "title": conf["title"],
                "life_phase": conf["life_phase"],
                "tags": json.dumps(conf["tags"]),
            }
        })

    # Add liberation tracks (preset journeys)
    journeys = [
        {
            "id": "track-quiet-sanctuary",
            "journey_code": "quiet-sanctuary",
            "title": "Quiet Sanctuary: Releasing Overwhelm",
            "doc_type": "track",
            "tags": ["overwhelmed", "quiet", "silence", "calm", "peace"],
            "description": "A guided journey designed for minds overwhelmed with noise, responsibility, and constant urgency. Step into quiet presence and rest your nervous system."
        },
        {
            "id": "track-heartbreak-healing",
            "journey_code": "heartbreak-healing",
            "title": "Heartbreak & Letting Go",
            "doc_type": "track",
            "tags": ["heartbreak", "letting go", "grief", "acceptance", "healing"],
            "description": "A compassionate sanctuary for releasing painful attachments, soothing raw emotional ache, and making peace with what was."
        },
        {
            "id": "track-morning-anxiety-relief",
            "journey_code": "morning-anxiety-relief",
            "title": "Morning Anxiety in the Chest: Somatic Awakening",
            "doc_type": "track",
            "tags": ["morning anxiety in the chest", "breath", "calm", "nervous system"],
            "description": "Somatic practices and vocal resonance to soften the tight constriction in the chest upon waking, restoring gentle ease and calm breath."
        },
        {
            "id": "track-inner-confidence",
            "journey_code": "inner-confidence",
            "title": "Finding Inner Confidence & Self-Sovereignty",
            "doc_type": "track",
            "tags": ["finding inner confidence", "power", "self-trust", "courage"],
            "description": "Uncover unwavering trust in yourself. Shed the imposter syndrome and cultivate a grounded, unshakeable center."
        },
        {
            "id": "track-grounded-body",
            "journey_code": "grounded-body",
            "title": "Grounded Body & Deep Breath",
            "doc_type": "track",
            "tags": ["grounded body & deep breath", "somatic", "presence", "earth"],
            "description": "Drop from racing mental loops down into the weight of your bones, the rhythm of your breath, and physical rootedness."
        }
    ]

    for j in journeys:
        doc_text = f"Title: {j['title']}\nType: track\nDescription: {j['description']}\nTags: {', '.join(j['tags'])}"
        docs.append({
            "id": j["id"],
            "text": doc_text,
            "metadata": {
                "doc_type": "track",
                "track_id": j["id"],
                "journey_code": j["journey_code"],
                "title": j["title"],
                "tags": json.dumps(j["tags"]),
            }
        })

    return docs

def main():
    print("Initializing Pinecone Inference Embeddings...")
    embeddings = PineconeInferenceEmbeddings(api_key=settings.PINECONE_API_KEY)
    index = _get_pinecone_index()

    docs = load_stories()
    print(f"Loaded {len(docs)} items to embed and index.")

    texts = [d["text"] for d in docs]
    print(f"Embedding {len(texts)} documents via multilingual-e5-large...")
    vectors = embeddings.embed_documents(texts)
    print(f"Generated {len(vectors)} vectors (dimension {len(vectors[0])}).")

    upsert_items = []
    for d, vec in zip(docs, vectors):
        upsert_items.append({
            "id": d["id"],
            "values": vec,
            "metadata": d["metadata"]
        })

    print(f"Upserting {len(upsert_items)} items to Pinecone index '{settings.PINECONE_INDEX_NAME}'...")
    index.upsert(vectors=upsert_items)

    stats = index.describe_index_stats()
    print("\nSUCCESS! New Pinecone stats:", stats)

if __name__ == "__main__":
    main()
