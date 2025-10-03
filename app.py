import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from apscheduler.schedulers.background import BackgroundScheduler
from deadline_agent import DeadlineAgent  # Import your agent

# Load environment variables
load_dotenv()

# Initialize Slack app with retry configuration
app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ["SLACK_SIGNING_SECRET"]
)

# Configure retry settings for better reliability
import time
from slack_sdk.errors import SlackApiError

# Initialize scheduler (in-memory only)
scheduler = BackgroundScheduler()
scheduler.start()

# Track processed messages to avoid duplicates
processed_messages = set()

# Initialize DeadlineAgent with IST timezone
import pytz
local_tz = pytz.timezone('Asia/Kolkata')  # IST timezone
deadline_agent = DeadlineAgent(timezone='Asia/Kolkata')

# Recovery function to reschedule existing reminders on startup
def reschedule_existing_reminders():
    """Reschedule all active reminders from database on startup"""
    try:
        active_reminders = deadline_agent.get_active_reminders()
        current_time = datetime.now(local_tz)

        print(f"Found {len(active_reminders)} active reminders to reschedule")

        for reminder in active_reminders:
            # Calculate time difference
            if reminder.due_at:
                time_diff = (reminder.due_at - current_time).total_seconds()

                if time_diff > 0:  # Only schedule future reminders
                    # Create job ID
                    job_id = f"{reminder.channel_id}_{reminder.message_ts}_{reminder.id}"

                    # Schedule the reminder
                    scheduler.add_job(
                        send_reminder,
                        'date',
                        run_date=reminder.due_at,
                        args=[reminder.channel_id, reminder.user_id, reminder.original_text, reminder.thread_ts],
                        id=job_id
                    )

                    print(f"Rescheduled reminder: {reminder.original_text} -> {reminder.due_at}")
                else:
                    print(f"Skipped expired reminder: {reminder.original_text} (was due at {reminder.due_at})")

    except Exception as e:
        print(f"Error rescheduling reminders: {e}")

def send_reminder(channel, thread_ts, user_id, original_message):
    """Send the reminder message with retry logic"""
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            # Validate thread_ts before sending
            if thread_ts and len(thread_ts) > 10 and '.' in thread_ts:  # Better validation
                response = app.client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=f"<@{user_id}> ETC Reminder: {original_message}"
                )
            else:
                # Send as regular message if thread_ts is invalid
                response = app.client.chat_postMessage(
                    channel=channel,
                    text=f"<@{user_id}> ETC Reminder: {original_message}"
                )

            if response["ok"]:
                print(f"ETC reminder sent to {user_id}")
                return
            else:
                print(f"Slack API error: {response.get('error', 'Unknown error')}")

        except SlackApiError as e:
            print(f"Slack API error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print(f"Failed to send ETC reminder after {max_retries} attempts")
        except Exception as e:
            print(f"Unexpected error sending ETC reminder (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print(f"Failed to send ETC reminder after {max_retries} attempts")

# Reschedule existing reminders on startup
reschedule_existing_reminders()
print(f"Using timezone: {local_tz}")

@app.event("message")
def handle_message_events(body, event, say, logger):
    """Handle all message events"""
    try:
        # Handle message deletion and editing events
        if event.get("subtype") == "message_deleted":
            print(f"Message deleted: {event.get('deleted_ts')}")
            # Cancel any scheduled reminders for this message
            channel = event.get("channel")
            deleted_ts = event.get("deleted_ts")
            if deleted_ts:
                # Cancel reminders using the agent's database method
                cancelled_count = deadline_agent.cancel_reminders_for_message(deleted_ts, channel)

                # Find and remove jobs for this specific message
                jobs_to_remove = []
                for job in scheduler.get_jobs():
                    if job.id.startswith(f"{channel}_{deleted_ts}_"):
                        jobs_to_remove.append(job.id)

                for job_id in jobs_to_remove:
                    scheduler.remove_job(job_id)
                    print(f"Cancelled reminder: {job_id}")

                print(f"Cancelled {cancelled_count} reminders from database and {len(jobs_to_remove)} jobs")
            return

        # Handle message editing events
        if event.get("subtype") == "message_changed":
            print(f"Message edited: {event.get('ts')}")
            # Process the edited message as a new deadline
            edited_message = event.get("message", {})
            if edited_message:
                # Extract the edited text
                text = edited_message.get("text", "")
                channel = event["channel"]
                user = edited_message.get("user")
                thread_ts = edited_message.get("thread_ts")

                if text and user and thread_ts:
                    print(f"Processing edited message: '{text}' from user: {user}")

                    # Use DeadlineAgent to detect deadline
                    message_ts = edited_message.get("ts", str(datetime.now().timestamp()))
                    reminder = deadline_agent.handle_message(text, user, channel, message_ts, thread_ts)

                    if reminder:
                        print(f"ETC found in edited message: {reminder.due_at}")
                        print(f"Matched text: {reminder.matched_text}")

                        # Create unique job ID using message timestamp
                        message_ts = edited_message.get("ts", str(datetime.now().timestamp()))
                        job_id = f"{channel}_{thread_ts}_{user}_{message_ts}"

                        # Remove existing jobs for same user/thread
                        existing_jobs = [job for job in scheduler.get_jobs()
                                       if job.id.startswith(f"{channel}_{thread_ts}_{user}_")]

                        is_update = len(existing_jobs) > 0
                        for job in existing_jobs:
                            scheduler.remove_job(job.id)
                            print(f"Removed existing job: {job.id}")

                        # Check if the reminder is too close to now (less than 1 minute)
                        current_time = datetime.now(local_tz)
                        if reminder.due_at:
                            time_diff = (reminder.due_at - current_time).total_seconds()

                            if time_diff < 60:  # Less than 1 minute
                                print(f"Reminder too close to now ({time_diff:.1f} seconds), scheduling for 1 minute from now")
                                reminder.due_at = current_time + timedelta(minutes=1)

                        # Schedule the reminder
                        scheduler.add_job(
                            send_reminder,
                            'date',
                            run_date=reminder.due_at,
                            args=[channel, thread_ts, user, text],
                            id=job_id
                        )

                        print(f"Reminder scheduled for: {reminder.due_at}")

                        # Format deadline for display
                        local_time = reminder.due_at.astimezone(local_tz)
                        current_date = datetime.now(local_tz).date()
                        deadline_date = local_time.date()

                        if deadline_date == current_date:
                            deadline_str = local_time.strftime('%I:%M %p')
                        elif deadline_date == current_date + timedelta(days=1):
                            # Check if user said "tomorrow" or a specific day
                            if 'tomorrow' in text.lower():
                                deadline_str = f"tomorrow at {local_time.strftime('%I:%M %p')}"
                            else:
                                # Check if it's a specific day of week (like "till friday")
                                day_name = local_time.strftime('%A')
                                deadline_str = f"{day_name} at {local_time.strftime('%I:%M %p')}"
                        else:
                            # For future dates, show day name only if it's within a week
                            days_diff = (deadline_date - current_date).days
                            if days_diff <= 7:
                                day_name = local_time.strftime('%A')
                                deadline_str = f"{day_name} at {local_time.strftime('%I:%M %p')}"
                            else:
                                deadline_str = local_time.strftime('%b %d at %I:%M %p')

                        # Send confirmation
                        if is_update:
                            response_text = f"ETC updated for <@{user}> to {deadline_str}"
                        else:
                            response_text = f"ETC confirmed for <@{user}> at {deadline_str}"

                        print(f"Sending response: {response_text}")
                        app.client.chat_postMessage(
                            channel=channel,
                            thread_ts=thread_ts,
                            text=response_text
                        )
            return

        # Create unique message ID to prevent duplicates
        message_id = f"{event.get('channel')}_{event.get('ts')}_{event.get('user')}"

        if message_id in processed_messages:
            print(f"Duplicate message ignored: {message_id}")
            return

        processed_messages.add(message_id)
        print(f"Message received: {event}")

        # Skip bot messages
        if event.get("bot_id"):
            print("Skipping bot message")
            return

        # Check if it's a thread reply
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            print("Not a thread reply - skipping")
            return

        print(f"Thread reply detected in thread: {thread_ts}")

        text = event.get("text", "")
        channel = event["channel"]
        user = event["user"]

        print(f"Processing: '{text}' from user: {user}")

        # Use DeadlineAgent to detect deadline
        message_ts = event.get("ts", str(datetime.now().timestamp()))
        reminder = deadline_agent.handle_message(text, user, channel, message_ts, thread_ts)

        if reminder:
            print(f"ETC found: {reminder.due_at}")
            print(f"Matched text: {reminder.matched_text}")

            # Create unique job ID using message timestamp
            message_ts = event.get("ts", str(datetime.now().timestamp()))
            job_id = f"{channel}_{thread_ts}_{user}_{message_ts}"

            # Remove existing jobs for same user/thread
            existing_jobs = [job for job in scheduler.get_jobs()
                           if job.id.startswith(f"{channel}_{thread_ts}_{user}_")]

            is_update = len(existing_jobs) > 0
            for job in existing_jobs:
                scheduler.remove_job(job.id)
                print(f"Removed existing job: {job.id}")

            # Check if the reminder is too close to now (less than 1 minute)
            current_time = datetime.now(local_tz)
            if reminder.due_at:
                time_diff = (reminder.due_at - current_time).total_seconds()

                if time_diff < 60:  # Less than 1 minute
                    print(f"Reminder too close to now ({time_diff:.1f} seconds), scheduling for 1 minute from now")
                    reminder.due_at = current_time + timedelta(minutes=1)

            # Schedule the reminder
            scheduler.add_job(
                send_reminder,
                'date',
                run_date=reminder.due_at,
                args=[channel, thread_ts, user, text],
                id=job_id
            )

            print(f"Reminder scheduled for: {reminder.due_at}")

            # Debug: Show current time and calculated time
            current_time = datetime.now(local_tz)
            print(f"Current time: {current_time}")
            print(f"Calculated deadline: {reminder.due_at}")

            # Format deadline for display in local timezone with date
            local_time = reminder.due_at.astimezone(local_tz)
            current_date = datetime.now(local_tz).date()
            deadline_date = local_time.date()

            # Show date only if it's not today
            if deadline_date == current_date:
                deadline_str = local_time.strftime('%I:%M %p')
            elif deadline_date == current_date + timedelta(days=1):
                # Check if user said "tomorrow" or a specific day
                if 'tomorrow' in text.lower():
                    deadline_str = f"tomorrow at {local_time.strftime('%I:%M %p')}"
                else:
                    # Check if it's a specific day of week (like "till friday")
                    day_name = local_time.strftime('%A')
                    deadline_str = f"{day_name} at {local_time.strftime('%I:%M %p')}"
            else:
                # For future dates, show day name only if it's within a week
                days_diff = (deadline_date - current_date).days
                if days_diff <= 7:
                    day_name = local_time.strftime('%A')
                    deadline_str = f"{day_name} at {local_time.strftime('%I:%M %p')}"
                else:
                    deadline_str = local_time.strftime('%b %d at %I:%M %p')

            print(f"Display time: {deadline_str}")

            # Confirm in thread with update status
            if is_update:
                response_text = f"ETC updated for <@{user}> to {deadline_str}"
                print(f"Sending update response: {response_text}")
                say(
                    text=response_text,
                    thread_ts=thread_ts
                )
            else:
                response_text = f"ETC confirmed for <@{user}> at {deadline_str}"
                print(f"Sending confirmation response: {response_text}")
                say(
                    text=response_text,
                    thread_ts=thread_ts
                )
        else:
            print("No ETC detected")

    except Exception as e:
        print(f"Error handling message: {e}")
        import traceback
        traceback.print_exc()

@app.event("app_mention")
def handle_mention(event, say):
    """Handle bot mentions"""
    jobs = scheduler.get_jobs()
    job_count = len(jobs)
    say(f"Tracking {job_count} ETC reminders")
    print(f"Status check: {job_count} active ETC reminders")

if __name__ == "__main__":
    app_token = os.environ.get("SLACK_APP_TOKEN")

    if app_token:
        handler = SocketModeHandler(app, app_token)
        print("ETC-Monitor Bot is running in Socket Mode!")
        handler.start()
    else:
        print("ETC-Monitor Bot is running on port 3000!")
        app.start(port=3000)
