#!/usr/bin/env python3
"""
Test script for the improved ETC detection system
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from deadline_agent import DeadlineAgent

def test_etc_detection():
    """Test the improved ETC detection system"""
    
    # Initialize the agent
    agent = DeadlineAgent(timezone='Asia/Kolkata')
    
    # Test cases
    test_cases = [
        # Should TRIGGER (valid ETC messages)
        "ETC: today 5 PM",
        "ETC tomorrow 2pm", 
        "I need to finish this task. ETC: Monday 3 PM",
        "ETC: friday morning",
        "Working on the feature. ETC next wednesday 4pm",
        
        # Should NOT TRIGGER (normal conversations with time words)
        "I'll see you today at 5 PM",
        "Can we meet tomorrow?",
        "Let's discuss this today",
        "The meeting is scheduled for friday",
        "I need to use deepseek's free API in ETC-Monitor - it confirmed a timing based on today keyword",
        
        # Edge cases
        "etc: tonight 8pm",  # lowercase
        "ETCs are important today",  # plural, not ETC format
        "The ETC for this project is unclear",  # ETC as noun, not command
    ]
    
    print("=" * 60)
    print("TESTING IMPROVED ETC DETECTION SYSTEM")
    print("=" * 60)
    
    for i, message in enumerate(test_cases, 1):
        print(f"\nTest {i}: '{message}'")
        print("-" * 40)
        
        # Test the detection
        result = agent.handle_message(
            message=message,
            user_id="test_user",
            channel_id="test_channel",
            message_ts=str(datetime.now().timestamp()),
            thread_ts="test_thread"
        )
        
        if result:
            print(f"✅ ETC DETECTED: {result.matched_text} -> {result.due_at}")
        else:
            print("❌ No ETC detected")
    
    print("\n" + "=" * 60)
    print("Test completed!")

if __name__ == "__main__":
    test_etc_detection()