"""
Generate voice narration for the About page ("Why Transform to Liberation?")
using ElevenLabs TTS and upload to S3.

This is a one-time script to produce the audio file for the play button on the About page.
The resulting S3 URL can be given to the frontend team.
"""
import sys
import os

# Add the project root to sys.path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.llm import generate_voice_elevenlabs, save_audio, ELEVENLABS_VOICES

# ---------------------------------------------------------------------------
# Narration script — written as a spoken-word version of the About page.
# Voice: "Adam" (Deep & Resonant Male Narration) — fits Michiel's persona
# as the founder delivering this message personally.
# ---------------------------------------------------------------------------

ABOUT_PAGE_NARRATION = """
Why Transform to Liberation?

The world we have built is a world of the surface. We live at the narrow edge, where the waves of reaction constantly crash against the rocks. We define ourselves by opposition: right or wrong, success or failure, us versus them.

For many of us — especially those who have achieved much and given more — there comes a moment of silent realization: This friction is not all there is.

The Cost of Adaptation.

No one sets out to lose themselves. We simply learn to survive. We learn which parts of our soul are welcomed and which create friction. We adapt to keep our families, our companies, and our circles safe. We become the keepers of the peace, the managers of the status quo.

But over time, these adjustments look like character. We lose track of the one question that can no longer be silenced: "What is actually true for me?"

The Return to Vitality.

Transform to Liberation is not a program for self-improvement. It is a return to what is real. It is the recognition that maturity is not about control, but about the courage to be fully present.

We are breaking the greatest taboo of our time: the artificial separation of our intellect from our life force. We have lived too long in a "Childish Duality" that ignores our deepest essence.

To be truly liberated is to embrace your sensuality and sexuality not as a performance, but as the sacred fire of your existence. It is the energy that allows a human being to truly shine. It is the integration of the feminine power within the masculine frame — a state where we no longer just manage life, but actually live it.

The Space to Be Seen.

This is not a commercial product. It is a space for honest expression. Through "Confessions" and shared "Transformations," we dissolve the distance between us. We move from the isolation of perfection to the abundance of greatness.

I started this because the path appeared beneath my feet. I realized that our current leaders are not ready to guide us; they are trapped in the same surface-level reactions. We cannot wait for wise elders. We must become them.

Your Invitation.

You have lived for others long enough. You have adapted until you became a stranger to yourself.

Now, the depth is calling. It is asking you to reduce the distance between what you feel and what you allow yourself to express. It is asking you to stop surviving the waves and start owning the ocean.

I am Michiel Stokman. This is Transform to Liberation. I am here. Are you ready to shine?
""".strip()


def main():
    # Use Adam voice — Deep & Resonant Male Narration, perfect for a founder's manifesto
    voice_name = "Adam"
    voice_id = ELEVENLABS_VOICES[voice_name]
    
    print(f"[SCRIPT] Length: {len(ABOUT_PAGE_NARRATION)} characters")
    print(f"[VOICE]  {voice_name} ({voice_id})")
    print("[TTS]    Generating audio via ElevenLabs...")
    
    # Use specific voice settings for a warm, authoritative narration
    audio_bytes = generate_voice_elevenlabs(
        text=ABOUT_PAGE_NARRATION,
        voice_id=voice_id,
        stability=0.72,           # Consistent, warm delivery
        similarity_boost=0.82,    # Expressive but natural
        style=0.20,               # Subtle stylistic variation
    )
    
    if len(audio_bytes) < 100:
        print("[WARN]   Got mock/empty audio -- check your ELEVENLABS_API_KEY in .env")
        return
    
    print(f"[OK]     Audio generated: {len(audio_bytes):,} bytes ({len(audio_bytes)/1024:.1f} KB)")
    
    # Save to S3 (or local fallback)
    audio_url = save_audio(audio_bytes, filename="about_page_narration.mp3")

    # ------------------------------------------------------------
    # Optional: upload the generated MP3 to a remote EC2 server
    # ------------------------------------------------------------
    # Set the following environment variables on the machine running this script:
    #   EC2_HOST – public DNS or IP of the EC2 instance
    #   EC2_USER – SSH user (default "ec2-user")
    #   EC2_REMOTE_PATH – absolute path on the EC2 where the file should live (e.g. "/var/www/html/static/audio")
    #   EC2_BASE_URL – base URL that serves the static files (e.g. "https://mydomain.com/static/audio")
    # If EC2_HOST is defined, we will scp the file there and replace `audio_url`
    import subprocess
    import os
    ec2_host = os.getenv("EC2_HOST")
    if ec2_host:
        ec2_user = os.getenv("EC2_USER", "ec2-user")
        remote_path = os.getenv("EC2_REMOTE_PATH", "/var/www/html/static/audio")
        base_url = os.getenv("EC2_BASE_URL", f"https://{ec2_host}/static/audio")
        # Ensure the remote directory exists – you may need to SSH and mkdir beforehand.
        try:
            subprocess.run(
                ["scp", audio_url, f"{ec2_user}@{ec2_host}:{remote_path}"],
                check=True,
                capture_output=True,
                text=True,
            )
            # Build the public URL for the frontend
            audio_url = f"{base_url}/about_page_narration.mp3"
            print("✅ Uploaded audio to EC2 server")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Failed to upload to EC2: {e.stderr.strip()}")
    
    print(f"\n{'='*60}")
    print(f"[RESULT] Audio URL for frontend:")
    print(f"         {audio_url}")
    print(f"{'='*60}")
    print(f"\nGive this URL to the frontend team for the About page play button.")


if __name__ == "__main__":
    main()
