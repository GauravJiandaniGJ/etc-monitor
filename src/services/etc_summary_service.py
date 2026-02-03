"""ETC Summary Service for generating daily task summaries."""
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
from src.core.models import Reminder, ReminderStatus
from src.database.repositories.reminder_repository import ReminderRepository
from src.services.notification_service import NotificationService
from src.services.ai_service import GeminiService
from src.utils.logger import get_logger
from src.utils.timezone import now_ist, to_ist


logger = get_logger('ETCSummaryService')


class ETCSummaryService:
    """Service for generating and sending daily ETC summaries.
    
    Provides daily summaries to users showing:
    - Yesterday's ETCs (overdue/missed)
    - Today's ETCs
    - Tomorrow's ETCs
    
    Excludes cancelled and confirmed tasks.
    """
    
    def __init__(
        self,
        reminder_repo: ReminderRepository,
        notification_service: NotificationService,
        ai_service: Optional[GeminiService] = None
    ):
        """Initialize ETC summary service.
        
        Args:
            reminder_repo: Reminder repository instance
            notification_service: Notification service for sending messages
            ai_service: Optional AI service for task summarization
        """
        self.reminder_repo = reminder_repo
        self.notification_service = notification_service
        self.ai_service = ai_service
        logger.info('ETC Summary service initialized')
    
    def get_user_summary(
        self,
        user_id: str
    ) -> List[Dict]:
        """Get ETC summary for a specific user with AI-enhanced details.
        
        Args:
            user_id: Slack user ID
            
        Returns:
            List of dictionaries containing reminder details and AI summary
        """
        logger.info(f'Generating summary for user {user_id}')
        
        # Get all active reminders for the user
        all_reminders = self.reminder_repo.get_by_user(user_id)
        
        # Filter for PENDING or RESCHEDULED status
        active_statuses = [ReminderStatus.PENDING, ReminderStatus.RESCHEDULED]
        active_reminders = [
            r for r in all_reminders 
            if r.status in active_statuses
        ]
        
        # Sort by deadline
        active_reminders.sort(key=lambda x: x.deadline_datetime)
        
        logger.debug(f'Found {len(active_reminders)} active reminders for user {user_id}')
        
        enhanced_summary = []
        
        for reminder in active_reminders:
            # Basic info
            item = {
                'reminder': reminder,
                'summary_text': reminder.task_description or "Unknown Task",
                'thread_link': None
            }
            
            # Fetch thread context and link
            if reminder.channel_id and reminder.thread_ts:
                # Get permalink
                permalink = self.notification_service.get_message_permalink(
                    reminder.channel_id, 
                    reminder.thread_ts
                )
                item['thread_link'] = permalink
                
                # AI Summarization Logic
                if self.ai_service and self.ai_service.is_configured():
                    try:
                        # Fetch parent message
                        parent_text = self.notification_service.get_thread_parent_message(
                            reminder.channel_id,
                            reminder.thread_ts
                        )
                        
                        if parent_text:
                            # Generate AI summary
                            prompt = (
                                f"Original Task Context: {parent_text}\n"
                                f"User Status Update: {reminder.deadline_text or 'ETC provided'}\n"
                                f"Summarize this into a single, short, clear task description (max 10 words). "
                                f"Example output: 'Deploying backend to staging'"
                            )
                            
                            ai_summary = self.ai_service.generate(prompt, max_tokens=50, temperature=0.3)
                            
                            if ai_summary:
                                item['summary_text'] = ai_summary.strip()
                                logger.debug(f'Generated AI summary for reminder {reminder.id}: {item["summary_text"]}')
                    except Exception as e:
                        logger.warning(f'Failed to generate AI summary for reminder {reminder.id}: {e}')
            
            enhanced_summary.append(item)
            
        return enhanced_summary
    
    def format_summary_message(
        self,
        summary_list: List[Dict],
        user_id: str
    ) -> Optional[str]:
        """Format summary data into a Slack message.
        
        Args:
            summary_list: List of summary items from get_user_summary()
            user_id: User ID for personalization
            
        Returns:
            Formatted Slack message string, or None if no tasks
        """
        if not summary_list:
            logger.debug(f'No tasks for user {user_id}, skipping summary')
            return None
        
        # Build message
        lines = ['📝 *Your ETC Summary*\n']
        lines.append('*Pending Tasks:*')
        
        for i, item in enumerate(summary_list, 1):
            reminder = item['reminder']
            text = item['summary_text']
            link = item['thread_link']
            
            # Format: 1. Task Description <link|View> - ETC: 5 mins
            if link:
                line = f"{i}. {text} <{link}|View Thread>"
            else:
                line = f"{i}. {text}"
            
            # Add simple ETC info if relevant
            # deadline_str = format_datetime_friendly(reminder.deadline_datetime)
            # line += f" (Due: {deadline_str})" 
            
            lines.append(line)
            
        lines.append('')
        lines.append('_This summary is AI-generated based on your task context._')
        
        message = '\n'.join(lines).strip()
        logger.debug(f'Formatted summary message for {user_id}')
        return message
    
    def send_daily_summaries(self) -> int:
        """Send daily summaries to all users with active ETCs.
        
        Called by scheduler at configured time (e.g., 9:00 AM daily).
        
        Returns:
            Number of summaries sent
        """
        logger.info('Starting daily summary generation')
        
        try:
            # Get all active reminders
            all_reminders = self.reminder_repo.get_all()
            
            # Get unique user IDs
            user_ids = set(r.user_id for r in all_reminders)
            logger.info(f'Found {len(user_ids)} users with reminders')
            
            sent_count = 0
            
            for user_id in user_ids:
                try:
                    # Generate summary for this user
                    summary = self.get_user_summary(user_id)
                    
                    # Format message
                    message = self.format_summary_message(summary, user_id)
                    
                    if message:
                        # Send as DM
                        success = self.notification_service.send_dm(user_id, message)
                        
                        if success:
                            sent_count += 1
                            logger.success(f'Sent daily summary to {user_id}')
                        else:
                            logger.error(f'Failed to send summary to {user_id}')
                    else:
                        logger.debug(f'No summary to send for {user_id}')
                        
                except Exception as e:
                    logger.error(f'Error generating summary for {user_id}: {e}', exc=e)
                    continue
            
            logger.success(f'Daily summary complete: {sent_count} summaries sent')
            return sent_count
            
        except Exception as e:
            logger.error(f'Error in daily summary generation: {e}', exc=e)
            return 0
    
    def send_summary_to_user(self, user_id: str) -> bool:
        """Send summary to a specific user (for testing or on-demand).
        
        Args:
            user_id: Slack user ID
            
        Returns:
            True if summary sent successfully
        """
        logger.info(f'Generating on-demand summary for {user_id}')
        
        try:
            summary = self.get_user_summary(user_id)
            message = self.format_summary_message(summary, user_id)
            
            if message:
                success = self.notification_service.send_dm(user_id, message)
                if success:
                    logger.success(f'Sent summary to {user_id}')
                return success
            else:
                logger.info(f'No tasks to summarize for {user_id}')
                return False
                
        except Exception as e:
            logger.error(f'Error sending summary to {user_id}: {e}', exc=e)
            return False
