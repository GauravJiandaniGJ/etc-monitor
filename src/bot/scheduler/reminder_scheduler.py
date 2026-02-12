"""Reminder scheduler using APScheduler."""
from typing import Callable, Optional
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.job import Job
from src.core.models import Reminder
from src.database.repositories.reminder_repository import ReminderRepository
from src.utils.logger import get_logger
from src.utils.timezone import now_ist, IST


logger = get_logger('ReminderScheduler')


class ReminderScheduler:
    """Scheduler for managing reminder jobs using APScheduler.

    Wraps APScheduler to provide a clean interface for scheduling,
    rescheduling, and canceling reminder notifications.
    """

    def __init__(self, reminder_repo: Optional[ReminderRepository] = None):
        """Initialize reminder scheduler.

        Args:
            reminder_repo: Optional reminder repository for loading pending reminders
        """
        self.scheduler = BackgroundScheduler()
        self.reminder_repo = reminder_repo
        logger.info('Reminder scheduler initialized')

    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info('Scheduler started')

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info('Scheduler stopped')

    def schedule(
        self,
        reminder: Reminder,
        callback: Callable[[Reminder], None]
    ) -> bool:
        """Schedule a reminder job.

        Schedules a job to execute the callback when the reminder is due.
        If the reminder time is too close to now (less than 30 seconds),
        it will be scheduled for 30 seconds from now.

        Args:
            reminder: Reminder object to schedule
            callback: Callback function that takes a Reminder as argument

        Returns:
            True if scheduled successfully, False otherwise
        """
        try:
            job_id = reminder.job_id

            # Check if job already exists and remove it
            existing_job = self.get_job(job_id)
            if existing_job:
                logger.info(f'Removing existing job {job_id} before rescheduling')
                self.cancel(job_id)

            # Get reminder time
            reminder_time = reminder.reminder_datetime

            # Ensure timezone awareness
            if reminder_time.tzinfo is None:
                # Assume IST if naive
                from src.utils.timezone import make_aware
                reminder_time = make_aware(reminder_time)

            # Check if reminder is too close to now
            current_time = now_ist()
            time_diff = (reminder_time - current_time).total_seconds()

            # Only adjust if reminder is less than 30 seconds away (very short)
            # For short deadlines (1-5 min), the reminder is intentionally set at deadline time
            if time_diff < 30:  # Less than 30 seconds
                logger.warning(
                    f'Reminder {reminder.id} too close to now ({time_diff:.1f}s), '
                    f'scheduling for 30 seconds from now'
                )
                reminder_time = current_time + timedelta(seconds=30)

            # Only schedule if in the future
            if time_diff <= 0 and reminder_time <= current_time:
                logger.warning(f'Reminder {reminder.id} is in the past, not scheduling')
                return False

            # Schedule the job
            self.scheduler.add_job(
                callback,
                'date',
                run_date=reminder_time,
                args=[reminder],
                id=job_id,
                replace_existing=True
            )

            logger.success(
                f'Scheduled reminder {reminder.id} (job {job_id}) '
                f'for {reminder_time}'
            )
            return True

        except Exception as e:
            logger.error(f'Error scheduling reminder {reminder.id}: {e}')
            return False

    def reschedule(
        self,
        reminder: Reminder,
        callback: Callable[[Reminder], None]
    ) -> bool:
        """Reschedule an existing reminder job.

        Cancels the existing job and schedules a new one with updated times.
        This is essentially the same as schedule() but semantically indicates
        that we're updating an existing reminder.

        Args:
            reminder: Updated reminder object
            callback: Callback function that takes a Reminder as argument

        Returns:
            True if rescheduled successfully, False otherwise
        """
        logger.info(f'Rescheduling reminder {reminder.id}')
        return self.schedule(reminder, callback)

    def cancel(self, job_id: str) -> bool:
        """Cancel a scheduled job.

        Args:
            job_id: Job ID to cancel

        Returns:
            True if cancelled successfully, False if job not found
        """
        try:
            job = self.get_job(job_id)
            if job:
                job.remove()
                logger.success(f'Cancelled job {job_id}')
                return True
            else:
                logger.warning(f'Job {job_id} not found')
                return False
        except Exception as e:
            logger.error(f'Error cancelling job {job_id}: {e}')
            return False

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID.

        Args:
            job_id: Job ID to look up

        Returns:
            Job object if found, None otherwise
        """
        try:
            return self.scheduler.get_job(job_id)
        except Exception as e:
            logger.error(f'Error getting job {job_id}: {e}')
            return None

    def load_pending_reminders(
        self,
        callback: Callable[[Reminder], None]
    ) -> int:
        """Load and schedule all pending reminders from database.

        This should be called on startup to restore all pending reminders
        that were scheduled before the application restarted.

        Only schedules reminders where deadline_datetime is in the future.

        Args:
            callback: Callback function to execute when reminder is due

        Returns:
            Number of reminders successfully loaded
        """
        if not self.reminder_repo:
            logger.warning('Reminder repository not provided, cannot load pending reminders')
            return 0

        logger.info('Loading pending reminders from database')

        try:
            # Get all pending reminders
            pending_reminders = self.reminder_repo.get_pending()
            current_time = now_ist()

            loaded_count = 0
            skipped_count = 0

            for reminder in pending_reminders:
                # Check if DEADLINE (not reminder time) is still in the future
                if reminder.deadline_datetime:
                    # Ensure timezone awareness
                    deadline_time = reminder.deadline_datetime
                    if deadline_time.tzinfo is None:
                        from src.utils.timezone import make_aware
                        deadline_time = make_aware(deadline_time)

                    # Only schedule if deadline is in the future
                    if deadline_time > current_time:
                        if self.schedule(reminder, callback):
                            loaded_count += 1
                        else:
                            skipped_count += 1
                    else:
                        logger.debug(
                            f'Skipping expired reminder {reminder.id} '
                            f'(deadline {deadline_time} has passed)'
                        )
                        skipped_count += 1
                else:
                    logger.warning(f'Reminder {reminder.id} has no deadline_datetime')
                    skipped_count += 1

            logger.success(
                f'Loaded {loaded_count} pending reminders '
                f'({skipped_count} skipped)'
            )
            return loaded_count

        except Exception as e:
            logger.error(f'Error loading pending reminders: {e}')
            return 0

    def get_all_jobs(self) -> list[Job]:
        """Get all scheduled jobs.

        Returns:
            List of all scheduled Job objects
        """
        return self.scheduler.get_jobs()

    def get_job_count(self) -> int:
        """Get count of scheduled jobs.

        Returns:
            Number of scheduled jobs
        """
        return len(self.scheduler.get_jobs())

    def schedule_morning_summary(
        self,
        callback: Callable,
        hour: int = 9,
        minute: int = 0
    ) -> bool:
        """Schedule daily morning summary job.

        Schedules a recurring job to send morning summaries every day.

        Args:
            callback: Callback function to execute daily
            hour: Hour of day (0-23, default 9 for 9 AM)
            minute: Minute of hour (0-59, default 0)

        Returns:
            True if scheduled successfully, False otherwise
        """
        try:
            job_id = 'morning_summary_daily'

            # Check if job already exists and remove it
            existing_job = self.get_job(job_id)
            if existing_job:
                logger.info(f'Removing existing morning summary job {job_id}')
                self.cancel(job_id)

            # Schedule daily job at specified time in IST timezone
            self.scheduler.add_job(
                callback,
                'cron',
                hour=hour,
                minute=minute,
                timezone=IST,
                id=job_id,
                replace_existing=True
            )

            logger.success(
                f'Scheduled morning summary job to run daily at {hour:02d}:{minute:02d}'
            )
            return True

        except Exception as e:
            logger.error(f'Error scheduling morning summary: {e}')
            return False

    def schedule_eod_check(
        self,
        callback: Callable,
        hour: int = 19,
        minute: int = 0
    ) -> bool:
        """Schedule daily EOD follow-up check.

        Args:
            callback: Callback function to execute daily
            hour: Hour of day (default 19 for 7 PM)
            minute: Minute of hour

        Returns:
            True if scheduled successfully
        """
        try:
            job_id = 'eod_followup_daily'

            # Check if job already exists and remove it
            existing_job = self.get_job(job_id)
            if existing_job:
                logger.info(f'Removing existing EOD check job {job_id}')
                self.cancel(job_id)

            # Schedule daily job at specified time in IST
            self.scheduler.add_job(
                callback,
                'cron',
                hour=hour,
                minute=minute,
                timezone=IST,
                id=job_id,
                replace_existing=True
            )

            logger.success(
                f'Scheduled EOD check job to run daily at {hour:02d}:{minute:02d}'
            )
            return True

        except Exception as e:
            logger.error(f'Error scheduling EOD check: {e}')
            return False
