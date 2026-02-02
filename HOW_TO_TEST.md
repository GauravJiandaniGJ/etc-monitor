# How to Test Daily Summaries

## Quick Test (30 seconds)

```bash
# Replace with your Slack user ID (get from: Slack → Profile → Copy member ID)
python scripts/quick_test.py U12345678
```

That's it! This will:
1. Create test reminders
2. Show preview
3. Ask if you want to send to Slack
4. Send it

## Manual Testing

```bash
# Preview only (safe, no sending)
python scripts/test_daily_summary_manual.py --preview U12345678

# Send to yourself
python scripts/test_daily_summary_manual.py --user U12345678

# Send to all users
python scripts/test_daily_summary_manual.py --all-users
```

## Unit Tests

```bash
pytest tests/services/test_daily_summary_service.py -v
```

## Troubleshooting

**No DM received?**
- Check user ID starts with `U`
- Check `.env` has `SLACK_BOT_TOKEN=xoxb-...`

**Import errors?**
- Run: `pip install -r requirements.txt`

Done!
