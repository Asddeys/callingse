"""
Transcript Handler Lambda Function - Enhanced Version

This Lambda function receives speech-to-text transcripts from LiveKit/Deepgram,
processes them, and triggers the appropriate conversation responses.
Enhanced to accept call_id from both path parameters and request body.
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
from shared import db_operations

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS SDK clients
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

# DynamoDB tables
CALLS_TABLE = os.environ.get('CALLS_TABLE', 'DebtReduction_Calls')
TRANSCRIPTS_TABLE = os.environ.get('TRANSCRIPTS_TABLE', 'DebtReduction_Transcripts')

# Lambda function names
CONVERSATION_FUNCTION = os.environ.get('CONVERSATION_FUNCTION', 'DebtReduction-ConversationManager')

class ConversationState:
    """
    Class to track the state of the conversation
    """
    GREETING = 'greeting'
    QUALIFICATION = 'qualification'
    DEBT_AMOUNT = 'debt_amount'
    CARD_COUNT = 'card_count'
    PAYMENT_STATUS = 'payment_status'
    EMPLOYMENT = 'employment'
    MONTHLY_PAYMENT = 'monthly_payment'
    INTENT_CHECK = 'intent_check'
    OBJECTION_HANDLING = 'objection_handling'
    TRANSFER = 'transfer'
    CLOSING = 'closing'
    ENDED = 'ended'

def process_transcript(event):
    """
    Process a transcript from any source (flexible for path parameters or body)
    """
    try:
        # Extract call ID from path parameters if available
        call_id = event.get('pathParameters', {}).get('call_id')
        
        # Parse request body
        body = event.get('body', '{}')
        if isinstance(body, str):
            body = json.loads(body)
        
        # If call_id not in path parameters, try to get from request body
        if not call_id:
            call_id = body.get('call_id')
            if not call_id:
                logger.error("Missing call_id in both path parameters and request body")
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Missing call_id in both path parameters and request body'
                    })
                }
        
        # Extract transcript data
        if 'transcript' not in body or not body['transcript']:
            logger.error("Empty or missing transcript in request")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Empty or missing transcript in request'
                })
            }
        
        # Extract transcript text
        transcript_text = body['transcript']
        
        # Check if this is the bot's own voice, avoid processing
        is_bot_voice = body.get('is_bot', False) or "bot" in body.get('speaker', "").lower()
        if is_bot_voice:
            logger.info(f"Skipping bot's own voice transcript: {transcript_text}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'skipped',
                    'reason': 'bot_voice'
                })
            }
        
        # Get call data
        call_data = db_operations.get_call(call_id)
        if not call_data:
            logger.error(f"Call {call_id} not found")
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'error': f"Call {call_id} not found"
                })
            }
        
        # Check if the call is in an active state for processing transcripts
        if call_data.get('call_state') in ['ended', 'failed']:
            logger.warning(f"Call {call_id} is in {call_data.get('call_state')} state, skipping transcript")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'skipped',
                    'reason': 'call_inactive'
                })
            }
        
        # Save transcript to database
        db_operations.save_transcript(call_id, 'customer', transcript_text)
        
        # Forward transcript to conversation manager for processing
        lambda_client.invoke(
            FunctionName=CONVERSATION_FUNCTION,
            InvocationType='Event',
            Payload=json.dumps({
                'call_id': call_id,
                'transcript': transcript_text,
                'speaker': 'customer',
                'timestamp': datetime.now().isoformat(),
                'confidence': body.get('confidence', 0.0),
                'channel': body.get('channel', 0),
                'metadata': body.get('metadata', {})
            })
        )
        
        # Return success response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'call_id': call_id,
                'status': 'processed',
                'transcript_length': len(transcript_text)
            })
        }
    
    except Exception as e:
        logger.error(f"Error processing transcript: {str(e)}")
        
        # Return error response
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f"Error processing transcript: {str(e)}"
            })
        }

def lambda_handler(event, context):
    """
    Lambda handler function for transcript webhook
    """
    try:
        # Log the event
        logger.info(f"Received transcript event: {json.dumps(event)}")
        
        # Process the transcript with enhanced flexibility
        return process_transcript(event)
    except Exception as e:
        logger.error(f"Unhandled exception in lambda_handler: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f"Unhandled exception: {str(e)}"
            })
        }
