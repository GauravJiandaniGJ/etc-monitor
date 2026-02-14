"""Notification service for sending Slack messages."""
from typing import Optional
import time
from datetime import timedelta
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
                # Validate thread_ts before sending - MUST be in thread
                # Use deadline_text or original_message, fallback to deadline_text
                reminder_text = reminder.deadline_text or reminder.original_message or "ETC"

                # CRITICAL: All reminders MUST be in threads - fail if thread_ts is invalid
                if not reminder.thread_ts or len(reminder.thread_ts) <= 10 or '.' not in reminder.thread_ts:
                    logger.error(f'Invalid thread_ts for reminder {reminder.id} - CANNOT send outside thread')
                    return False

                # Send message IN THREAD only
                response = self.client.chat_postMessage(
                    channel=reminder.channel_id,
                    thread_ts=reminder.thread_ts,
                    text=f"<@{reminder.user_id}> Status!\n*ETC:* {reminder_text}"
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
            # Calculate time difference for reminder message
            now = now_ist()
            time_until_reminder = reminder.reminder_datetime - now

            # Format reminder time message - show ACCURATE time until reminder
            # Use round() instead of int() for accurate time display
            total_seconds = time_until_reminder.total_seconds()

            # Debug logging for time calculation
            logger.debug(
                f'Time calculation: now={now}, reminder_time={reminder.reminder_datetime}, '
                f'diff={total_seconds}s ({total_seconds/60:.2f} minutes)'
            )

            if total_seconds <= 30:
                reminder_msg = "You'll be reminded in less than a minute."
            elif total_seconds < 60:
                seconds = round(total_seconds)
                sec_text = "second" if seconds == 1 else "seconds"
                reminder_msg = f"You'll be reminded in {seconds} {sec_text}."
            elif total_seconds < 3600:  # Less than 1 hour
                # Round to nearest minute for accurate display
                minutes = round(total_seconds / 60)
                # Ensure at least 1 minute if there's any time remaining
                if minutes < 1 and total_seconds > 0:
                    minutes = 1
                min_text = "minute" if minutes == 1 else "minutes"
                reminder_msg = f"You'll be reminded in {minutes} {min_text}."
            elif total_seconds < 86400:  # Less than 1 day
                hours = round(total_seconds / 3600)
                remaining_seconds = total_seconds % 3600
                minutes = round(remaining_seconds / 60)
                hour_text = "hour" if hours == 1 else "hours"
                if minutes > 0:
                    min_text = "minute" if minutes == 1 else "minutes"
                    reminder_msg = f"You'll be reminded in {hours} {hour_text} and {minutes} {min_text}."
                else:
                    reminder_msg = f"You'll be reminded in {hours} {hour_text}."
            else:
                days = round(total_seconds / 86400)
                day_text = "day" if days == 1 else "days"
                reminder_msg = f"You'll be reminded in {days} {day_text}."

            message = (
                f"Reminder {action}!\n"
                f"Estimated completion: {deadline_str}\n"
                f"{reminder_msg}"
            )

            if is_update and reminder.reschedule_count > 0:
                message += f"\n(Rescheduled {reminder.reschedule_count} time(s))"

            # CRITICAL: All confirmations MUST be in threads
            if not reminder.thread_ts or len(reminder.thread_ts) <= 10 or '.' not in reminder.thread_ts:
                logger.error(f'Invalid thread_ts for reminder {reminder.id} confirmation - CANNOT send outside thread')
                return False

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
                f"Reminder cancelled.\n"
                f"Original estimated completion: {deadline_str}"
            )

            # CRITICAL: All cancellations MUST be in threads
            if not reminder.thread_ts or len(reminder.thread_ts) <= 10 or '.' not in reminder.thread_ts:
                logger.error(f'Invalid thread_ts for reminder {reminder.id} cancellation - CANNOT send outside thread')
                return False

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

    def send_followup(self, reminder: Reminder) -> bool:
        """Send EOD follow-up message.

        Args:
            reminder: Reminder to follow up on

        Returns:
            True if sent successfully
        """
        logger.info(f'Sending EOD follow-up for reminder {reminder.id}')

        if not reminder.thread_ts or len(reminder.thread_ts) <= 10 or '.' not in reminder.thread_ts:
            logger.error(f'Invalid thread_ts for reminder {reminder.id} follow-up - CANNOT send outside thread')
            return False

        try:
            message = f"👀 <@{reminder.user_id}> Update on this?\n*ETC:* {reminder.deadline_text or '—'}"

            response = self.client.chat_postMessage(
                channel=reminder.channel_id,
                thread_ts=reminder.thread_ts,
                text=message
            )

            if response["ok"]:
                logger.success(f'Follow-up sent for reminder {reminder.id}')
                return True
            else:
                error = response.get('error', 'Unknown error')
                logger.error(f'Failed to send follow-up: {error}')
                return False

        except Exception as e:
            logger.error(f'Error sending follow-up: {e}')
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

    def get_message_permalink(self, channel_id: str, message_ts: str) -> Optional[str]:
        """Get permalink URL for a Slack message.

        Args:
            channel_id: Slack channel ID
            message_ts: Message timestamp

        Returns:
            Permalink URL, or None if fetch fails
        """
        if not self.client:
            logger.warning('Slack client not available')
            return None

        try:
            response = self.client.chat_getPermalink(
                channel=channel_id,
                message_ts=message_ts
            )

            if response['ok'] and response.get('permalink'):
                permalink = response['permalink']
                logger.debug(f'Fetched permalink: {permalink}')
                return permalink
            else:
                logger.warning(f'Failed to fetch permalink: {response.get("error", "Unknown error")}')
                return None

        except SlackApiError as e:
            logger.error(f'Slack API error fetching permalink: {e}')
            return None
        except Exception as e:
            logger.error(f'Unexpected error fetching permalink: {e}')
            return None

    def fetch_parent_message(self, channel_id: str, thread_ts: str) -> Optional[str]:
        """Fetch the parent message text from a Slack thread.

        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp (this is also the parent message timestamp)

        Returns:
            Parent message text, or None if fetch fails
        """
        if not self.client:
            logger.warning('Slack client not available')
            return None

        try:
            # Fetch the conversation history with the specific message
            response = self.client.conversations_history(
                channel=channel_id,
                latest=thread_ts,
                inclusive=True,
                limit=1
            )

            if response['ok'] and response.get('messages'):
                parent_message = response['messages'][0]
                message_text = parent_message.get('text', '')
                logger.debug(f'Fetched parent message: "{message_text[:100]}..."')
                return message_text
            else:
                logger.warning(f'Failed to fetch parent message: {response.get("error", "Unknown error")}')
                return None

        except SlackApiError as e:
            logger.error(f'Slack API error fetching parent message: {e}')
            return None
        except Exception as e:
            logger.error(f'Unexpected error fetching parent message: {e}')
            return None

    def send_morning_summary(
        self,
        user_id: str,
        reminders: list,
        ai_service=None
    ) -> bool:
        """Send morning summary of pending tasks to a user.

        Fetches parent messages from threads, rephrases them with AI,
        and sends a formatted summary.

        Args:
            user_id: Slack user ID to send summary to
            reminders: List of Reminder objects
            ai_service: Optional AI service for rephrasing (GeminiService)

        Returns:
            True if sent successfully, False otherwise
        """
        if not reminders:
            logger.debug(f'No pending reminders for user {user_id}')
            return True

        logger.info(f'Preparing morning summary for user {user_id} with {len(reminders)} tasks')

        try:
            tasks = []
            for idx, reminder in enumerate(reminders, 1):
                # Fetch parent message
                parent_msg = self.fetch_parent_message(reminder.channel_id, reminder.thread_ts)

                if parent_msg:
                    # Rephrase with AI if available
                    if ai_service and hasattr(ai_service, 'rephrase_task'):
                        task_summary = ai_service.rephrase_task(parent_msg)
                    else:
                        # Fallback: use first 50 chars of parent message
                        task_summary = parent_msg[:50] + ('...' if len(parent_msg) > 50 else '')
                else:
                    # Fallback: use deadline_text
                    task_summary = reminder.deadline_text or 'Task'

                # Get proper Slack permalink
                thread_link = self.get_message_permalink(reminder.channel_id, reminder.thread_ts)

                # Fallback if permalink fetch fails
                if not thread_link:
                    thread_link = f"https://slack.com/app_redirect?channel={reminder.channel_id}&message_ts={reminder.thread_ts}"

                # Format deadline
                deadline_str = format_datetime_friendly(reminder.deadline_datetime)

                tasks.append(f"{idx}. {task_summary} (Due: {deadline_str}) - <{thread_link}|View Thread>")

            # Determine greeting based on time of day
            current_hour = now_ist().hour
            if 5 <= current_hour < 12:
                greeting = "Good morning"
            elif 12 <= current_hour < 17:
                greeting = "Good afternoon"
            else:
                greeting = "Good evening"

            # Create summary message
            message = f"{greeting} <@{user_id}>!\n\n"
            message += f"You have {len(tasks)} pending task{'s' if len(tasks) > 1 else ''}:\n\n"
            message += '\n'.join(tasks)

            # Send as DM
            response = self.client.chat_postMessage(
                channel=user_id,
                text=message
            )

            if response["ok"]:
                logger.success(f'Morning summary sent to {user_id}')
                return True
            else:
                error = response.get('error', 'Unknown error')
                logger.error(f'Failed to send morning summary: {error}')
                return False

        except SlackApiError as e:
            logger.error(f'Slack API error sending morning summary: {e}')
            return False
        except Exception as e:
            logger.error(f'Unexpected error sending morning summary: {e}')
            return False

    def clear_cache(self):
        """Clear user and channel name caches.

        Useful for testing or when you want to force refresh of names.
        """
        self.user_cache.clear()
        self.channel_cache.clear()
        logger.debug('Cleared user and channel name caches')
