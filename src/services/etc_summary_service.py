"""ETC Summary Service for generating daily task summaries."""
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
from src.core.models import Reminder, ReminderStatus
from src.database.repositories.reminder_repository import ReminderRepository
from src.services.notification_service import NotificationService
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
        notification_service: NotificationService
    ):
        """Initialize ETC summary service.
        
        Args:
            reminder_repo: Reminder repository instance
            notification_service: Notification service for sending messages
        """
        self.reminder_repo = reminder_repo
        self.notification_service = notification_service
        logger.info('ETC Summary service initialized')
    
    def get_user_summary(
        self,
        user_id: str,
        reference_date: Optional[date] = None
    ) -> Dict[str, List[Reminder]]:
        """Get ETC summary for a specific user.
        
        Args:
            user_id: Slack user ID
            reference_date: Date to use as "today" (defaults to current date)
            
        Returns:
            Dictionary with keys: 'yesterday', 'today', 'tomorrow'
            Each contains list of Reminder objects
        """
        if reference_date is None:
            reference_date = now_ist().date()
        
        logger.info(f'Generating summary for user {user_id} (reference: {reference_date})')
        
        # Get all user reminders
        all_reminders = self.reminder_repo.get_by_user(user_id)
        
        # Filter out cancelled and confirmed reminders
        exclude_statuses = [ReminderStatus.CANCELLED, ReminderStatus.CONFIRMED]
        active_reminders = [
            r for r in all_reminders 
            if r.status not in exclude_statuses
        ]
        
        logger.debug(f'Found {len(active_reminders)} active reminders for user {user_id}')
        
        # Group by date
        yesterday = reference_date - timedelta(days=1)
        tomorrow = reference_date + timedelta(days=1)
        
        summary = {
            'yesterday': [],
            'today': [],
            'tomorrow': []
        }
        
        for reminder in active_reminders:
            # Convert deadline to IST date
            deadline_date = to_ist(reminder.deadline_datetime).date()
            
            if deadline_date == yesterday:
                summary['yesterday'].append(reminder)
            elif deadline_date == reference_date:
                summary['today'].append(reminder)
            elif deadline_date == tomorrow:
                summary['tomorrow'].append(reminder)
        
        logger.info(
            f'Summary for {user_id}: '
            f'{len(summary["yesterday"])} yesterday, '
            f'{len(summary["today"])} today, '
            f'{len(summary["tomorrow"])} tomorrow'
        )
        
        return summary
    
    def format_summary_message(
        self,
        summary: Dict[str, List[Reminder]],
        user_id: str
    ) -> Optional[str]:
        """Format summary data into a Slack message.
        
        Args:
            summary: Summary dictionary from get_user_summary()
            user_id: User ID for personalization
            
        Returns:
            Formatted Slack message string, or None if no tasks
        """
        # Check if there are any tasks
        total_tasks = (
            len(summary['yesterday']) +
            len(summary['today']) +
            len(summary['tomorrow'])
        )
        
        if total_tasks == 0:
            logger.debug(f'No tasks for user {user_id}, skipping summary')
            return None
        
        # Build message
        lines = ['📝 *Your ETC Summary*\n']
        
        # Yesterday's ETCs (missed/overdue)
        if summary['yesterday']:
            lines.append('*Yesterday\'s ETCs (Missed):*')
            for i, reminder in enumerate(summary['yesterday'], 1):
                lines.append(f'{i}. {reminder.task_description}')
            lines.append('')  # Empty line
        
        # Today's ETCs
        if summary['today']:
            lines.append('*Today\'s ETCs:*')
            for i, reminder in enumerate(summary['today'], 1):
                lines.append(f'{i}. {reminder.task_description}')
            lines.append('')  # Empty line
        
        # Tomorrow's ETCs
        if summary['tomorrow']:
            lines.append('*Tomorrow\'s ETCs:*')
            for i, reminder in enumerate(summary['tomorrow'], 1):
                lines.append(f'{i}. {reminder.task_description}')
            lines.append('')  # Empty line
        
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
