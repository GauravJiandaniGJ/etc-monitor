import os
import re
from datetime import datetime
from dotenv import load_dotenv
import dateparser
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from apscheduler.schedulers.background import BackgroundScheduler
from deadline_agent import DeadlineAgent  # Import your agent

# Load environment variables
load_dotenv()

# Initialize Slack app
app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ["SLACK_SIGNING_SECRET"]
)

# Initialize scheduler (in-memory only)
scheduler = BackgroundScheduler()
scheduler.start()

# Initialize DeadlineAgent
deadline_agent = DeadlineAgent(timezone='UTC')

def send_reminder(channel, thread_ts, user_id, original_message):
    """Send the reminder message"""
    try:
        app.client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"<@{user_id}> Reminder: status!"
        )
        print(f"Reminder sent to {user_id}")
    except Exception as e:
        print(f"Error sending reminder: {e}")

@app.event("message")
def handle_message_events(body, event, say, logger):
    """Handle all message events"""
    try:
        print(f"📨 Message received: {event}")

        # Skip bot messages
        if event.get("bot_id"):
            print("Skipping bot message")
            return

        # Check if it's a thread reply
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            print("Not a thread reply - skipping")
            return

        print(f"✅ Thread reply detected in thread: {thread_ts}")

        text = event.get("text", "")
        channel = event["channel"]
        user = event["user"]

        print(f"Processing: '{text}' from user: {user}")

        # Use DeadlineAgent to detect deadline
        reminder = deadline_agent.handle_message(text, user)

        if reminder:
            print(f"🎯 Deadline found: {reminder.due_at}")

            # Create unique job ID
            job_id = f"{channel}_{thread_ts}_{user}_{datetime.now().timestamp()}"

            # Remove existing jobs for same user/thread
            existing_jobs = [job for job in scheduler.get_jobs()
                           if job.id.startswith(f"{channel}_{thread_ts}_{user}_")]
            for job in existing_jobs:
                scheduler.remove_job(job.id)
                print(f"Removed existing job: {job.id}")

            # Schedule the reminder
            scheduler.add_job(
                send_reminder,
                'date',
                run_date=reminder.due_at,
                args=[channel, thread_ts, user, text],
                id=job_id
            )

            print(f"⏰ Reminder scheduled for: {reminder.due_at}")

            # Format deadline for display
            deadline_str = reminder.due_at.strftime('%I:%M %p')

            # Confirm in thread
            say(
                text=f"Deadline confirmed for <@{user}> at {deadline_str}",
                thread_ts=thread_ts
            )
        else:
            print("❌ No deadline detected")

    except Exception as e:
        print(f"💥 Error handling message: {e}")
        import traceback
        traceback.print_exc()

@app.event("app_mention")
def handle_mention(event, say):
    """Handle bot mentions"""
    jobs = scheduler.get_jobs()
    job_count = len(jobs)
    say(f"Tracking {job_count} deadlines")
    print(f"Status check: {job_count} active deadlines")

if __name__ == "__main__":
    app_token = os.environ.get("SLACK_APP_TOKEN")

    if app_token:
        handler = SocketModeHandler(app, app_token)
        print("⚡️ Slack Deadline Bot is running in Socket Mode!")
        handler.start()
    else:
        print("⚡️ Slack Deadline Bot is running on port 3000!")
        app.start(port=3000)
