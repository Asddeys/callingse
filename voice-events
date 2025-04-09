"""
Voice Events Handler Lambda Function

This Lambda function handles various voice events from LiveKit,
including call start/end, silence detection, and error notifications.
"""

import os
import json
import logging
import boto3
import sys
import time
from datetime import datetime

# Add parent directory to path for importing shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import livekit_client, db_operations

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS SDK clients
dynamodb = boto3.resource('dynamodb')

# DynamoDB tables
CALLS_TABLE = os.environ.get('CALLS_TABLE', 'DebtReduction_Calls')
CUSTOMER_INFO_TABLE = os.environ.get('CUSTOMER_INFO_TABLE', 'DebtReduction_CustomerInfo')
TRANSCRIPTS_TABLE = os.environ.get('TRANSCRIPTS_TABLE', 'DebtReduction_Transcripts')

def handle_participant_joined(event_data, call_id):
    """
    Handle a participant joined event
    """
    participant_id = event_data.get('participant_id')
    participant_type = event_data.get('metadata', {}).get('type')
    
    logger.info(f"Participant {participant_id} of type {participant_type} joined call {call_id}")
    
    # Get call data
    call_data = db_operations.get_call(call_id)
    if not call_data:
        logger.error(f"Call {call_id} not found")
        return
    
    # Update call data with participant info
    if participant_type == 'customer':
        call_data['customer_participant_id'] = participant_id
    
    call_data['last_update'] = datetime.now().isoformat()
    db_operations.update_call(call_data)

def handle_participant_left(event_data, call_id):
    """
    Handle a participant left event
    """
    participant_id = event_data.get('participant_id')
    reason = event_data.get('reason')
    
    logger.info(f"Participant {participant_id} left call {call_id} due to {reason}")
    
    # Get call data
    call_data = db_operations.get_call(call_id)
    if not call_data:
        logger.error(f"Call {call_id} not found")
        return
    
    # Check if this was the customer participant
    if call_data.get('customer_participant_id') == participant_id:
        # Customer hung up, end the call
        call_data['call_state'] = 'ended'
        call_data['end_reason'] = 'customer_disconnect'
        call_data['end_timestamp'] = datetime.now().isoformat()
    
    call_data['last_update'] = datetime.now().isoformat()
    db_operations.update_call(call_data)

def handle_silence_detected(event_data, call_id):
    """
    Handle a silence detected event
    """
    duration_ms = event_data.get('duration_ms', 0)
    
    # Only log prolonged silence
    if duration_ms > 5000:  # 5 seconds
        logger.info(f"Prolonged silence detected in call {call_id}: {duration_ms}ms")
        
        # Get call data
        call_data = db_operations.get_call(call_id)
        if not call_data:
            logger.error(f"Call {call_id} not found")
            return
        
        # Check if we need to prompt the customer due to silence
        current_state = call_data.get('current_state')
        last_bot_speak = call_data.get('last_bot_speak_timestamp')
        
        # If it's been more than 10 seconds since the bot spoke, prompt the customer
        if last_bot_speak:
            last_speak_time = datetime.fromisoformat(last_bot_speak)
            now = datetime.now()
            time_since_speak = (now - last_speak_time).total_seconds()
            
            if time_since_speak > 10 and duration_ms > 8000:
                room_name = call_data.get('room_name')
                prompt = "I'm still here. Can you please respond to my question?"
                
                # Speak the prompt
                livekit_client.speak_text(room_name, prompt)
                
                # Update the last bot speak timestamp
                call_data['last_bot_speak_timestamp'] = now.isoformat()
                call_data['last_update'] = now.isoformat()
                db_operations.update_call(call_data)
                
                # Save transcript
                db_operations.save_transcript(call_id, 'bot', prompt)

def handle_speech_detected(event_data, call_id):
    """
    Handle a speech detected event
    """
    # Just log that speech was detected
    logger.info(f"Speech detected in call {call_id}")

def handle_room_ended(event_data, call_id):
    """
    Handle a room ended event
    """
    logger.info(f"Room ended for call {call_id}")
    
    # Get call data
    call_data = db_operations.get_call(call_id)
    if not call_data:
        logger.error(f"Call {call_id} not found")
        return
    
    # Update call data to ended state
    call_data['call_state'] = 'ended'
    call_data['end_reason'] = 'room_closed'
    call_data['end_timestamp'] = datetime.now().isoformat()
    call_data['last_update'] = datetime.now().isoformat()
    
    db_operations.update_call(call_data)

def handle_error(event_data, call_id):
    """
    Handle an error event
    """
    error_type = event_data.get('error_type')
    error_message = event_data.get('error_message')
    
    logger.error(f"Error in call {call_id}: {error_type} - {error_message}")
    
    # Get call data
    call_data = db_operations.get_call(call_id)
    if not call_data:
        logger.error(f"Call {call_id} not found")
        return
    
    # Record the error
    call_data['last_error'] = json.dumps({
        'type': error_type,
        'message': error_message,
        'timestamp': datetime.now().isoformat()
    })
    call_data['last_update'] = datetime.now().isoformat()
    
    db_operations.update_call(call_data)

def handle_recording_complete(event_data, call_id):
    """
    Handle a recording complete event
    """
    recording_url = event_data.get('recording_url')
    recording_duration = event_data.get('duration_seconds')
    
    logger.info(f"Recording complete for call {call_id}: {recording_url}, duration: {recording_duration}s")
    
    # Get call data
    call_data = db_operations.get_call(call_id)
    if not call_data:
        logger.error(f"Call {call_id} not found")
        return
    
    # Update call data with recording info
    call_data['recording_url'] = recording_url
    call_data['recording_duration'] = recording_duration
    call_data['last_update'] = datetime.now().isoformat()
    
    db_operations.update_call(call_data)

def process_voice_event(event):
    """
    Process a voice event from LiveKit
    """
    try:
        # Extract call ID from the path parameter
        call_id = event.get('pathParameters', {}).get('call_id')
        if not call_id:
            logger.error("Missing call_id in path parameters")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing call_id in path parameters'
                })
            }
        
        # Parse request body
        body = event.get('body', '{}')
        if isinstance(body, str):
            body = json.loads(body)
        
        # Extract event type
        event_type = body.get('event_type')
        if not event_type:
            logger.error("Missing event_type in request body")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing event_type in request body'
                })
            }
        
        # Handle different event types
        if event_type == 'participant_joined':
            handle_participant_joined(body, call_id)
        elif event_type == 'participant_left':
            handle_participant_left(body, call_id)
        elif event_type == 'silence_detected':
            handle_silence_detected(body, call_id)
        elif event_type == 'speech_detected':
            handle_speech_detected(body, call_id)
        elif event_type == 'room_ended':
            handle_room_ended(body, call_id)
        elif event_type == 'error':
            handle_error(body, call_id)
        elif event_type == 'recording_complete':
            handle_recording_complete(body, call_id)
        else:
            logger.warning(f"Unhandled event type: {event_type}")
        
        # Return success response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'call_id': call_id,
                'event_type': event_type,
                'status': 'processed'
            })
        }
    
    except Exception as e:
        logger.error(f"Error processing voice event: {str(e)}")
        
        # Return error response
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f"Error processing voice event: {str(e)}"
            })
        }

def lambda_handler(event, context):
    """
    Lambda handler function for voice events webhook
    """
    logger.info(f"Received voice event: {json.dumps(event)}")
    
    # Process the voice event
    return process_voice_event(event)
