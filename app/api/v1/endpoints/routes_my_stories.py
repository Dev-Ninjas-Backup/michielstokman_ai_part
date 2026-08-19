"""
app/api/v1/endpoints/routes_my_stories.py

The member story workspace: voice selection and cloning, the member's own
story library, edit + regenerate, re-narration, withdraw/resubmit, cover
imagery, and Meta/Spotify distribution copy.

Every route here is scoped to the authenticated member's own content.
"""
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.responses import ApiResponse, success_response
from app.model.user import User
from app.schemas.schema_member_story import (
    CustomVoiceResponse,
    MemberStoryDetail,
    MemberStoryListResponse,
    RenarrateRequest,
    SharePackageResponse,
    StoryImageResponse,
    StoryJobAcceptedResponse,
    UpdateMemberStoryRequest,
    VoiceCatalogResponse,
    WithdrawStoryResponse,
)
from app.schemas.schema_system import MessageResponse
from app.services.service_member_story import (
    MemberStoryService,
    story_reference,
    to_detail,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Voice selection
# ---------------------------------------------------------------------------

@router.get("/voices", response_model=ApiResponse[VoiceCatalogResponse], tags=["Voices"])
def list_voices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    The narration voices a member can choose from, plus their own cloned voice
    when they have recorded one. Pass the returned `name` as `voice_name` on
    story generation, regeneration, or re-narration.
    """
    result = MemberStoryService.get_voice_catalog(db, current_user)
    return success_response("Voice options retrieved", status.HTTP_200_OK, result)


@router.get("/me/voice", response_model=ApiResponse[CustomVoiceResponse], tags=["Voices"])
def get_my_voice(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Whether this member has a cloned narration voice on file."""
    result = MemberStoryService.get_custom_voice(db, current_user)
    return success_response("Custom voice status retrieved", status.HTTP_200_OK, result)


@router.post(
    "/me/voice",
    response_model=ApiResponse[CustomVoiceResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["Voices"],
)
def upload_my_voice(
    recordings: List[UploadFile] = File(..., description="One or more clear speech recordings"),
    display_name: Optional[str] = Query(None, description="Label shown in the voice picker"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Clones the member's own voice from uploaded recordings so their stories can
    be narrated in it. Aim for at least 60 seconds of clean, single-speaker audio.

    Returns 503 when the provider account does not have voice cloning enabled —
    the predefined voices remain available in that case.
    """
    result = MemberStoryService.create_custom_voice(
        db, current_user, recordings, display_name
    )
    return success_response("Custom voice created", status.HTTP_201_CREATED, result)


@router.delete("/me/voice", response_model=ApiResponse[CustomVoiceResponse], tags=["Voices"])
def delete_my_voice(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Removes the member's cloned voice. Already-generated audio is unaffected."""
    result = MemberStoryService.delete_custom_voice(db, current_user)
    return success_response("Custom voice removed", status.HTTP_200_OK, result)


# ---------------------------------------------------------------------------
# Member story library
# ---------------------------------------------------------------------------

@router.get("/me/stories", response_model=ApiResponse[MemberStoryListResponse], tags=["My Stories"])
def list_my_stories(
    story_type: Optional[str] = Query(None, description="confession | meditation | transformation | all"),
    submission_status: Optional[str] = Query(None, description="submitted | withdrawn | draft | all"),
    generation_status: Optional[str] = Query(None, description="processing | completed | failed | all"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    The member's own submissions, including drafts, withdrawn pieces and items
    still awaiting moderation — none of which appear on the public feed.
    """
    result = MemberStoryService.list_stories(
        db, current_user, story_type, submission_status, generation_status, page, limit
    )
    return success_response("Stories retrieved", status.HTTP_200_OK, result)


@router.get(
    "/me/stories/{story_id}",
    response_model=ApiResponse[MemberStoryDetail],
    tags=["My Stories"],
)
def get_my_story(
    story_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full detail for one of the member's own stories: the AI-narrated text, their
    original submission, the audio, the artwork and the word-level alignment.
    """
    result = MemberStoryService.get_story(db, current_user, story_id)
    return success_response("Story retrieved", status.HTTP_200_OK, result)


@router.patch(
    "/me/stories/{story_id}",
    response_model=ApiResponse[MemberStoryDetail],
    tags=["My Stories"],
)
def update_my_story(
    story_id: str,
    payload: UpdateMemberStoryRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Edits a story. By default the updated input is re-run through the AI prompt
    and re-narrated in the background — poll this endpoint or
    `GET /v1/me/stories/{story_id}` until `generation_status` is `completed`,
    then preview the new text and audio.

    Set `regenerate: false` to correct metadata without re-running the AI.
    """
    story, job_id, voice_name, custom_voice_id = MemberStoryService.update_story(
        db, current_user, story_id, payload
    )
    detail = to_detail(story)

    if job_id:
        background_tasks.add_task(
            MemberStoryService.regeneration_worker,
            job_id=job_id,
            story_db_id=str(story.id),
            voice_name=voice_name,
            custom_voice_id=custom_voice_id,
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return success_response(
            "Story updated. Regeneration in progress.", status.HTTP_202_ACCEPTED, detail
        )

    return success_response("Story updated", status.HTTP_200_OK, detail)


@router.delete(
    "/me/stories/{story_id}",
    response_model=ApiResponse[MessageResponse],
    tags=["My Stories"],
)
def delete_my_story(
    story_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Permanently deletes one of the member's stories along with its audio and
    cover art. Use withdraw instead to keep the story in the private library.
    """
    MemberStoryService.delete_story(db, current_user, story_id)
    return success_response(
        "Story deleted",
        status.HTTP_200_OK,
        MessageResponse(message="Story permanently deleted."),
    )


# ---------------------------------------------------------------------------
# Narration
# ---------------------------------------------------------------------------

@router.post(
    "/me/stories/{story_id}/narrate",
    response_model=ApiResponse[StoryJobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
    tags=["My Stories"],
)
def renarrate_my_story(
    story_id: str,
    payload: RenarrateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Re-records the existing story text in a different voice. The text is not
    changed and no credit is consumed, so members can audition the available
    voices on a finished piece.
    """
    story, job_id, voice_name, custom_voice_id = MemberStoryService.start_renarration(
        db, current_user, story_id, payload
    )
    background_tasks.add_task(
        MemberStoryService.renarration_worker,
        job_id=job_id,
        story_db_id=str(story.id),
        voice_name=voice_name,
        custom_voice_id=custom_voice_id,
    )
    result = StoryJobAcceptedResponse(
        story_id=str(story.id),
        story_reference=story_reference(story),
        job_id=job_id,
        generation_status="processing",
        message="Re-narration queued. Poll GET /v1/me/stories/{story_id} for the new audio.",
    )
    return success_response("Re-narration queued", status.HTTP_202_ACCEPTED, result)


# ---------------------------------------------------------------------------
# Withdraw / resubmit
# ---------------------------------------------------------------------------

@router.post(
    "/me/stories/{story_id}/withdraw",
    response_model=ApiResponse[WithdrawStoryResponse],
    tags=["My Stories"],
)
def withdraw_my_story(
    story_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Withdraws a story from publication. It leaves the public feed and the
    moderation queue but stays in the member's library, so they can resubmit it
    later or submit a new piece in its place.
    """
    story = MemberStoryService.withdraw(db, current_user, story_id)
    result = WithdrawStoryResponse(
        story_id=str(story.id),
        story_reference=story_reference(story),
        submission_status=story.submission_status.value,
        message="Story withdrawn. It is no longer publicly visible.",
    )
    return success_response("Story withdrawn", status.HTTP_200_OK, result)


@router.post(
    "/me/stories/{story_id}/resubmit",
    response_model=ApiResponse[WithdrawStoryResponse],
    tags=["My Stories"],
)
def resubmit_my_story(
    story_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Puts a withdrawn story back in the queue. Moderation reviews it again."""
    story = MemberStoryService.resubmit(db, current_user, story_id)
    result = WithdrawStoryResponse(
        story_id=str(story.id),
        story_reference=story_reference(story),
        submission_status=story.submission_status.value,
        message="Story resubmitted and awaiting review.",
    )
    return success_response("Story resubmitted", status.HTTP_200_OK, result)


# ---------------------------------------------------------------------------
# Cover imagery
# ---------------------------------------------------------------------------

@router.post(
    "/me/stories/{story_id}/image",
    response_model=ApiResponse[StoryImageResponse],
    tags=["My Stories"],
)
def upload_my_story_image(
    story_id: str,
    image: UploadFile = File(..., description="JPEG, PNG or WebP, up to 8 MB"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Uses the member's own image as the story artwork. A member-uploaded image
    is preserved across regenerations and is never replaced by AI artwork.
    """
    story = MemberStoryService.upload_story_image(db, current_user, story_id, image)
    result = StoryImageResponse(
        story_id=str(story.id),
        cover_image_url=story.cover_image_url,
        image_source=story.image_source.value if story.image_source else None,
        message="Cover image updated.",
    )
    return success_response("Cover image updated", status.HTTP_200_OK, result)


@router.post(
    "/me/stories/{story_id}/image/generate",
    response_model=ApiResponse[StoryImageResponse],
    tags=["My Stories"],
)
def generate_my_story_image(
    story_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generates artwork from the story's own content, using the palette and
    collage composition defined for its type (confession, meditation or
    transformation) so it matches the rest of the catalog.
    """
    story = MemberStoryService.generate_story_image(db, current_user, story_id)
    result = StoryImageResponse(
        story_id=str(story.id),
        cover_image_url=story.cover_image_url,
        image_source=story.image_source.value if story.image_source else None,
        message="Cover artwork generated from the story.",
    )
    return success_response("Cover artwork generated", status.HTTP_200_OK, result)


# ---------------------------------------------------------------------------
# Meta / Spotify distribution
# ---------------------------------------------------------------------------

@router.post(
    "/me/stories/{story_id}/social-intros",
    response_model=ApiResponse[MemberStoryDetail],
    tags=["My Stories"],
)
def generate_social_intros(
    story_id: str,
    force: bool = Query(False, description="Rewrite the intros even if they already exist"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Writes the platform introductions for this story: a short teaser for
    Instagram and Facebook, and a longer spoken-word intro for Spotify.
    """
    story = MemberStoryService.generate_social_intros(db, current_user, story_id, force)
    return success_response(
        "Platform introductions generated", status.HTTP_200_OK, to_detail(story)
    )


@router.get(
    "/me/stories/{story_id}/share",
    response_model=ApiResponse[SharePackageResponse],
    tags=["My Stories"],
)
def get_share_package(
    story_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    The complete package for publishing to Meta and Spotify: the story's
    existing artwork, its audio, a public link, and the per-platform
    introductions. Intros are written on first request.
    """
    result = MemberStoryService.get_share_package(db, current_user, story_id)
    return success_response("Share package retrieved", status.HTTP_200_OK, result)
