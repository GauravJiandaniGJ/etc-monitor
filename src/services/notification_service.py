"""Notification service for sending Slack messages."""
from typing import Optional
import time
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from src.core.models import Reminder
from src.utils.logger import get_logger
from src.utils.timezone import format_datetime_friendly, now_ist


logger = get_logger('NotificationService')


class NotificationService:
    """Service for sending Slack notifications.

    Handles all Slack message sending including reminders, confirmations,
    and cancellations. Includes user/channel name resolution with caching.
    """

    def __init__(self, slack_client: WebClient):
        """Initialize notification service.

        Args:
            slack_client: Slack WebClient instance
        """
        self.client = slack_client
        self.user_cache: dict[str, str] = {}
        self.channel_cache: dict[str, str] = {}
        logger.info('Notification service initialized')

    def send_reminder(self, reminder: Reminder) -> bool:
        """Send reminder notification to user.

        Sends a reminder message in the thread when the deadline is due.
        Includes retry logic with exponential backoff.

        Args:
            reminder: Reminder object to send

        Returns:
            True if sent successfully, False otherwise
        """
        logger.info(f'Sending reminder {reminder.id} to user {reminder.user_id}')

        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                # Validate thread_ts before sending
                if reminder.thread_ts and len(reminder.thread_ts) > 10 and '.' in reminder.thread_ts:
                    response = self.client.chat_postMessage(
                        channel=reminder.channel_id,
                        thread_ts=reminder.thread_ts,
                        text=f"<@{reminder.user_id}> Status!\n*ETC:* {reminder.original_text}"
                    )
                else:
                    # Send as regular message if thread_ts is invalid
                    logger.warning(f'Invalid thread_ts for reminder {reminder.id}, sending as regular message')
                    response = self.client.chat_postMessage(
                        channel=reminder.channel_id,
                        text=f"<@{reminder.user_id}> Status!\n*ETC:* {reminder.original_text}"
                    )

                if response["ok"]:
                    logger.success(f'Reminder {reminder.id} sent successfully to {reminder.user_id}')
                    return True
                else:
                    error = response.get('error', 'Unknown error')
                    logger.error(f'Slack API error: {error}')
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        return False

            except SlackApiError as e:
                logger.error(f'Slack API error (attempt {attempt + 1}/{max_retries}): {e}')
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f'Failed to send reminder {reminder.id} after {max_retries} attempts')
                    return False

            except Exception as e:
                logger.error(f'Unexpected error sending reminder (attempt {attempt + 1}): {e}')
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f'Failed to send reminder {reminder.id} after {max_retries} attempts')
                    return False

        return False

    def send_confirmation(
        self,
        reminder: Reminder,
        is_update: bool = False
    ) -> bool:
        """Send confirmation message after creating/updating reminder.

        Sends a confirmation message in the thread to let the user know
        their reminder was created or updated.

        Args:
            reminder: Reminder object that was created/updated
            is_update: True if this is an update, False if new reminder

        Returns:
            True if sent successfully, False otherwise
        """
        action = "updated" if is_update else "created"
        deadline_str = format_datetime_friendly(reminder.deadline_datetime)

        logger.info(f'Sending {action} confirmation for reminder {reminder.id}')

        try:
            message = (
                f"✅ Reminder {action}!\n"
                f"Deadline: {deadline_str}\n"
                f"You'll be reminded 1 hour before."
            )

            if is_update and reminder.reschedule_count > 0:
                message += f"\n(Rescheduled {reminder.reschedule_count} time(s))"

            response = self.client.chat_postMessage(
                channel=reminder.channel_id,
                thread_ts=reminder.thread_ts,
                text=message
            )

            if response["ok"]:
                logger.success(f'Confirmation sent for reminder {reminder.id}')
                return True
            else:
                error = response.get('error', 'Unknown error')
                logger.error(f'Failed to send confirmation: {error}')
                return False

        except SlackApiError as e:
            logger.error(f'Slack API error sending confirmation: {e}')
            return False
        except Exception as e:
            logger.error(f'Unexpected error sending confirmation: {e}')
            return False

    def send_cancellation(self, reminder: Reminder) -> bool:
        """Send cancellation confirmation message.

        Sends a message in the thread confirming the reminder was cancelled.

        Args:
            reminder: Reminder object that was cancelled

        Returns:
            True if sent successfully, False otherwise
        """
        logger.info(f'Sending cancellation confirmation for reminder {reminder.id}')

        try:
            deadline_str = format_datetime_friendly(reminder.deadline_datetime)
            message = (
                f"❌ Reminder cancelled.\n"
                f"Original deadline: {deadline_str}"
            )

            response = self.client.chat_postMessage(
                channel=reminder.channel_id,
                thread_ts=reminder.thread_ts,
                text=message
            )

            if response["ok"]:
                logger.success(f'Cancellation confirmation sent for reminder {reminder.id}')
                return True
            else:
                error = response.get('error', 'Unknown error')
                logger.error(f'Failed to send cancellation: {error}')
                return False

        except SlackApiError as e:
            logger.error(f'Slack API error sending cancellation: {e}')
            return False
        except Exception as e:
            logger.error(f'Unexpected error sending cancellation: {e}')
            return False

    def resolve_user_name(self, user_id: str) -> str:
        """Resolve user ID to display name.

        Fetches user information from Slack API and caches the result.
        Falls back to user_id if API call fails.

        Args:
            user_id: Slack user ID

        Returns:
            User display name, real name, username, or user_id as fallback
        """
        if not self.client:
            return user_id

        # Check cache first
        if user_id in self.user_cache:
            return self.user_cache[user_id]

        try:
            response = self.client.users_info(user=user_id)
            if response['ok']:
                user_info = response['user']
                # Try to get display name, real name, or fallback to username
                display_name = user_info.get('profile', {}).get('display_name')
                real_name = user_info.get('profile', {}).get('real_name')
                username = user_info.get('name')

                name = display_name or real_name or username or user_id
                self.user_cache[user_id] = name
                logger.debug(f'Resolved user {user_id} to {name}')
                return name
        except SlackApiError as e:
            logger.warning(f'Error fetching user info for {user_id}: {e}')
        except Exception as e:
            logger.warning(f'Unexpected error fetching user info for {user_id}: {e}')

        # Cache the fallback to avoid repeated API calls
        self.user_cache[user_id] = user_id
        return user_id

    def resolve_channel_name(self, channel_id: str) -> str:
        """Resolve channel ID to channel name.

        Fetches channel information from Slack API and caches the result.
        Falls back to channel_id if API call fails.

        Args:
            channel_id: Slack channel ID

        Returns:
            Channel name with # prefix, or channel_id as fallback
        """
        if not self.client:
            return channel_id

        # Check cache first
        if channel_id in self.channel_cache:
            return self.channel_cache[channel_id]

        try:
            response = self.client.conversations_info(channel=channel_id)
            if response['ok']:
                channel_info = response['channel']
                name = channel_info.get('name', channel_id)
                # Add # prefix for channels
                if not name.startswith('#'):
                    name = f"#{name}"
                self.channel_cache[channel_id] = name
                logger.debug(f'Resolved channel {channel_id} to {name}')
                return name
        except SlackApiError as e:
            logger.warning(f'Error fetching channel info for {channel_id}: {e}')
        except Exception as e:
            logger.warning(f'Unexpected error fetching channel info for {channel_id}: {e}')

        # Cache the fallback to avoid repeated API calls
        self.channel_cache[channel_id] = channel_id
        return channel_id

    def clear_cache(self):
        """Clear user and channel name caches.

        Useful for testing or when you want to force refresh of names.
        """
        self.user_cache.clear()
        self.channel_cache.clear()
        logger.debug('Cleared user and channel name caches')
