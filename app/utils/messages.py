"""
app/utils/messages.py
Central repository for user-facing success and error messages.
"""

# Liberation Journey
LIBERATION_DAY_COMPLETE = "Day {day} has been completed successfully."
LIBERATION_JOURNEY_COMPLETE = "You have completed the journey."
LIBERATION_ENROLL_REQUIRED = "No active journey found. Please enroll to continue."
LIBERATION_PURCHASE_REQUIRED = "Purchase of the '{journey_code}' journey is required for access."
LIBERATION_DAY_LOCKED = "Day {day} is locked. Please complete the previous day to unlock it."
LIBERATION_CONTINUE_DESC = "Continue your {days}-day program."

# Story Generation
STORY_GENERATION_CREDIT_REMAINING = "You have {remaining} out of {max} credits remaining today."
STORY_GENERATION_PREMIUM_UNLIMITED = "Premium subscription active. You have unlimited stories."

# AI Fallbacks
AI_FALLBACK_GREETING = "Welcome. Today's focus for Day {day} is {theme}."
AI_FALLBACK_WHY = "This exercise connects you to the theme of {theme}."
AI_FALLBACK_FEEDBACK = "No specific reflections were shared."
STORY_UNTITLED = "Untitled"

# User-Facing API Response Messages (Humanized Success)
JOURNEY_ENROLLED_SUCCESS = "You have successfully enrolled in the journey."
JOURNEY_REPEATED_SUCCESS = "Your journey has been restarted successfully."
JOURNEY_STATUS_SUCCESS = "Your progress has been synced successfully."
PURCHASED_JOURNEYS_SUCCESS = "Your purchased journeys have been retrieved."
EXERCISE_GENERATED_SUCCESS = "Your daily exercise guide is ready."
DAY_COMPLETED_SUCCESS = "Your progress for today has been recorded."
DAY_DETAIL_SUCCESS = "Today's guide and practices have been loaded."
FEED_CARD_SUCCESS = "Your personalized feed is ready."

LOGIN_SUCCESSFUL = "You have logged in successfully. Welcome back."
SIGNUP_SUCCESSFUL = "Your account has been created successfully. Welcome."
LOGOUT_SUCCESSFUL = "You have been signed out securely."
PASSWORD_RESET_SUCCESS = "Your password has been reset successfully."
PASSWORD_UPDATE_SUCCESS = "Your password has been changed."
TOKEN_REFRESH_SUCCESSFUL = "Your session has been securely renewed."
FORGOT_PASSWORD_SUCCESS = "If an account exists for this email, a reset link has been sent."

PROFILE_UPDATED_SUCCESS = "Your profile changes have been saved."
PROFILE_FETCHED_SUCCESS = "Your profile details have been loaded."
AVATAR_UPDATED_SUCCESS = "Your profile avatar has been updated successfully."
