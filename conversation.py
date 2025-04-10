"""
Conversation Manager Lambda Function

This Lambda function manages the AI-powered conversation with
customers, handling speech recognition, intent identification,
and qualification process.

Updated to work with LiveKit auto-room creation feature and
compatible with existing API Gateway resources.
"""

import json
import os
import boto3
import logging
import time
import re
import requests
import jwt
from datetime import datetime

# Import shared modules
import sys
sys.path.append('/opt')
from shared import db_operations, livekit_client, openai_client
from shared import conversation_scripts, objection_handler

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

# DynamoDB table names
CALLS_TABLE = os.environ.get('CALLS_TABLE', 'DebtBotCalls')
CUSTOMER_INFO_TABLE = os.environ.get('CUSTOMER_INFO_TABLE', 'DebtBotCustomerInfo')
TRANSCRIPTS_TABLE = os.environ.get('TRANSCRIPTS_TABLE', 'DebtBotTranscripts')

# Lambda function names
TRANSFER_FUNCTION = os.environ.get('TRANSFER_FUNCTION', 'DebtBot-TransferHandler')

# Qualifying thresholds
MIN_DEBT_AMOUNT = 7000  # Minimum debt amount to qualify
INTENT_CONFIRMATION_THRESHOLD = 0.7  # Confidence threshold for intent confirmation

class ConversationState:
    """
    Class to track the state of the conversation
    """
    GREETING = 'greeting'
    QUALIFICATION = 'qualification'
    BILL_RESPONSIBILITY = 'bill_responsibility'
    DEBT_AMOUNT = 'debt_amount'
    CARD_COUNT = 'card_count'
    PAYMENT_STATUS = 'payment_status'
    EMPLOYMENT = 'employment'
    MONTHLY_PAYMENT = 'monthly_payment'
    QUALIFICATION_COMPLETE = 'qualification_complete'
    INTENT_CHECK = 'intent_check'
    OBJECTION_HANDLING = 'objection_handling'
    TRANSFER = 'transfer'
    CLOSING = 'closing'
    ENDED = 'ended'

def check_livekit_room(room_name):
    """Check if a LiveKit room exists"""
    try:
        # Use the livekit_client module for consistent API access
        room_info = livekit_client.get_room(room_name)
        return room_info is not None
    except Exception as e:
        logger.error(f"Error checking room existence: {str(e)}")
        return False

def initialize_conversation(call_data):
    """
    Initialize the conversation with LiveKit room awareness
    Now supports E.164 phone number format
    """
    try:
        # Extract call ID and phone number
        call_id = call_data['call_id']
        phone_number = call_data.get('phone_number')
        
        # Format phone number in E.164 if needed
        if phone_number and not phone_number.startswith('+') and phone_number != call_id:
            # Import the format_phone_number_e164 function if needed
            from shared.utils import format_phone_number_e164
            formatted_phone = format_phone_number_e164(phone_number)
            if formatted_phone:
                phone_number = formatted_phone
                # Update the call data with properly formatted phone number
                call_data['phone_number'] = formatted_phone
        
        # Set room name
        room_name = call_id
        
        # Check if room already exists (could have been auto-created by SIP)
        room_exists = check_livekit_room(room_name)
        
        if not room_exists:
            # Room doesn't exist yet, create it explicitly
            logger.info(f"Room doesn't exist yet for {call_id}, creating it")
            room = livekit_client.create_room(room_name)
        else:
            logger.info(f"Room already exists for {call_id}, skipping creation")
        
        # Always set up voice pipeline regardless of room creation
        livekit_client.setup_voice_pipeline(room_name)
        
        # Add participant details to call data
        call_data['room_name'] = room_name
        call_data['current_state'] = ConversationState.GREETING
        call_data['last_update'] = datetime.now().isoformat()
        
        # Update call record in DynamoDB
        db_operations.update_call(call_data)
        
        logger.info(f"Initialized conversation for call_id: {call_id}")
        return True
    except Exception as e:
        logger.error(f"Error initializing conversation: {str(e)}")
        call_data['call_state'] = 'failed'
        call_data['error'] = str(e)
        db_operations.update_call(call_data)
        raise

def get_question_for_state(state, customer_info):
    """
    Get the question text for a given conversation state
    """
    if state == ConversationState.GREETING:
        return conversation_scripts.get_greeting(customer_info)
    elif state == ConversationState.QUALIFICATION:
        return conversation_scripts.get_qualification_intro(customer_info)
    elif state == ConversationState.BILL_RESPONSIBILITY:
        return conversation_scripts.get_bill_responsibility_question(customer_info)
    elif state == ConversationState.DEBT_AMOUNT:
        return conversation_scripts.get_debt_amount_question(customer_info)
    elif state == ConversationState.CARD_COUNT:
        return conversation_scripts.get_card_count_question(customer_info)
    elif state == ConversationState.PAYMENT_STATUS:
        return conversation_scripts.get_payment_status_question(customer_info)
    elif state == ConversationState.EMPLOYMENT:
        return conversation_scripts.get_employment_question(customer_info)
    elif state == ConversationState.MONTHLY_PAYMENT:
        return conversation_scripts.get_monthly_payment_question(customer_info)
    elif state == ConversationState.INTENT_CHECK:
        return conversation_scripts.get_intent_check(customer_info)
    elif state == ConversationState.TRANSFER:
        return conversation_scripts.get_transfer_message(customer_info)
    elif state == ConversationState.CLOSING:
        return conversation_scripts.get_closing_message(customer_info)
    else:
        return "Unknown state"

def process_user_input(transcript, call_data):
    """
    Process user input from transcript and update call state
    """
    try:
        call_id = call_data['call_id']
        current_state = call_data.get('current_state', ConversationState.GREETING)
        customer_info = db_operations.get_customer_info(call_id)
        
        # Save transcript
        db_operations.save_transcript(call_id, 'customer', transcript)
        
        # Initialize call logs object if not present
        if 'call_logs' not in call_data:
            call_data['call_logs'] = json.dumps({
                'question_responses': [],
                'objections': [],
                'timestamps': {}
            })
        
        # Parse existing call logs
        call_logs = json.loads(call_data.get('call_logs', '{}'))
        if 'question_responses' not in call_logs:
            call_logs['question_responses'] = []
            
        # Create a new response entry
        response_entry = {
            'state': current_state,
            'timestamp': datetime.now().isoformat(),
            'question': get_question_for_state(current_state, customer_info),
            'response': transcript
        }
        
        # Analyze user input with OpenAI
        analysis = openai_client.analyze_response(
            transcript, 
            current_state,
            customer_info
        )
        
        # Update customer info based on analysis
        if 'first_name' in analysis and analysis['first_name']:
            customer_info['first_name'] = analysis['first_name']
        
        if 'last_name' in analysis and analysis['last_name']:
            customer_info['last_name'] = analysis['last_name']
        
        # Process specific fields based on current state
        if current_state == ConversationState.QUALIFICATION or current_state == ConversationState.BILL_RESPONSIBILITY:
            # Process bill responsibility information
            if 'handles_bills' in analysis:
                customer_info['handles_bills'] = analysis['handles_bills']
            
            if 'bill_handler_name' in analysis and analysis['bill_handler_name']:
                customer_info['bill_handler_name'] = analysis['bill_handler_name']
            
            if 'call_transfer_accepted' in analysis:
                customer_info['call_transfer_accepted'] = analysis['call_transfer_accepted']
            
            if 'callback_time' in analysis and analysis['callback_time']:
                customer_info['callback_time'] = analysis['callback_time']
        
        elif current_state == ConversationState.DEBT_AMOUNT:
            # Extract debt amount if mentioned
            if 'debt_amount' in analysis and analysis['debt_amount']:
                debt_info = json.loads(customer_info.get('debt_info', '{}'))
                debt_info['total_amount'] = analysis['debt_amount']
                customer_info['debt_info'] = json.dumps(debt_info)
        
        elif current_state == ConversationState.CARD_COUNT:
            # Extract card count if mentioned
            if 'card_count' in analysis and analysis['card_count']:
                debt_info = json.loads(customer_info.get('debt_info', '{}'))
                debt_info['card_count'] = analysis['card_count']
                customer_info['debt_info'] = json.dumps(debt_info)
        
        elif current_state == ConversationState.PAYMENT_STATUS:
            # Extract payment status if mentioned
            if 'payment_status' in analysis and analysis['payment_status']:
                debt_info = json.loads(customer_info.get('debt_info', '{}'))
                debt_info['payment_status'] = analysis['payment_status']
                customer_info['debt_info'] = json.dumps(debt_info)
        
        elif current_state == ConversationState.EMPLOYMENT:
            # Extract employment status if mentioned
            if 'employment_status' in analysis and analysis['employment_status']:
                debt_info = json.loads(customer_info.get('debt_info', '{}'))
                debt_info['employment_status'] = analysis['employment_status']
                customer_info['debt_info'] = json.dumps(debt_info)
        
        elif current_state == ConversationState.MONTHLY_PAYMENT:
            # Extract monthly payment amount if mentioned
            if 'monthly_payment' in analysis and analysis['monthly_payment']:
                debt_info = json.loads(customer_info.get('debt_info', '{}'))
                debt_info['monthly_payment'] = analysis['monthly_payment']
                customer_info['debt_info'] = json.dumps(debt_info)
        
        elif current_state == ConversationState.INTENT_CHECK:
            # Check if customer confirmed intent
            if 'intent_confirmed' in analysis:
                call_data['intent_verified'] = analysis['intent_confirmed']
                # Also store in customer_info for consistency (fixes qualification check)
                customer_info['intent_verified'] = analysis['intent_confirmed']
        
        # Check for objections
        if 'objection' in analysis and analysis['objection']:
            objections = json.loads(customer_info.get('objections', '[]'))
            objections.append(analysis['objection'])
            customer_info['objections'] = json.dumps(objections)
            
            # Set state to objection handling if an objection is detected
            if analysis['objection_detected']:
                call_data['current_state'] = ConversationState.OBJECTION_HANDLING
                call_data['objection_type'] = analysis['objection']
        
        # Add analysis results to the response entry
        response_entry['analysis'] = {
            'data_points': {}
        }
        
        # Add specific state data based on the current state
        if current_state == ConversationState.QUALIFICATION or current_state == ConversationState.BILL_RESPONSIBILITY:
            response_entry['analysis']['data_points']['handles_bills'] = customer_info.get('handles_bills', False)
            if 'bill_handler_name' in customer_info:
                response_entry['analysis']['data_points']['bill_handler_name'] = customer_info['bill_handler_name']
                
        elif current_state == ConversationState.DEBT_AMOUNT:
            debt_info = json.loads(customer_info.get('debt_info', '{}'))
            if 'total_amount' in debt_info:
                response_entry['analysis']['data_points']['debt_amount'] = debt_info['total_amount']
                
        elif current_state == ConversationState.CARD_COUNT:
            debt_info = json.loads(customer_info.get('debt_info', '{}'))
            if 'card_count' in debt_info:
                response_entry['analysis']['data_points']['card_count'] = debt_info['card_count']
                
        elif current_state == ConversationState.PAYMENT_STATUS:
            debt_info = json.loads(customer_info.get('debt_info', '{}'))
            if 'payment_status' in debt_info:
                response_entry['analysis']['data_points']['payment_status'] = debt_info['payment_status']
                
        elif current_state == ConversationState.EMPLOYMENT:
            debt_info = json.loads(customer_info.get('debt_info', '{}'))
            if 'employment_status' in debt_info:
                response_entry['analysis']['data_points']['employment_status'] = debt_info['employment_status']
                
        elif current_state == ConversationState.MONTHLY_PAYMENT:
            debt_info = json.loads(customer_info.get('debt_info', '{}'))
            if 'monthly_payment' in debt_info:
                response_entry['analysis']['data_points']['monthly_payment'] = debt_info['monthly_payment']
        
        # Add the response entry to call logs
        call_logs['question_responses'].append(response_entry)
        call_data['call_logs'] = json.dumps(call_logs)
        
        # Determine next state based on current state and analysis
        next_state = determine_next_state(current_state, analysis, customer_info)
        
        # Update the call state
        call_data['current_state'] = next_state
        call_data['last_update'] = datetime.now().isoformat()
        
        # Update call record in DynamoDB
        db_operations.update_call(call_data)
        
        # Update customer info in DynamoDB
        db_operations.update_customer_info(call_id, customer_info)
        
        logger.info(f"Processed user input for call_id: {call_id}, current_state: {current_state}, next_state: {next_state}")
        
        # Get the bot's response for the next state
        bot_response = get_bot_response(next_state, customer_info, call_data)
        
        # Save bot response transcript
        db_operations.save_transcript(call_id, 'bot', bot_response)
        
        # If the next state is TRANSFER, trigger transfer Lambda
        if next_state == ConversationState.TRANSFER:
            trigger_transfer(call_data, customer_info)
        
        return {
            'call_id': call_id,
            'current_state': next_state,
            'bot_response': bot_response,
            'intent_verified': call_data.get('intent_verified', False)
        }
    except Exception as e:
        logger.error(f"Error processing user input: {str(e)}")
        call_data['error'] = str(e)
        db_operations.update_call(call_data)
        raise

def determine_next_state(current_state, analysis, customer_info):
    """
    Determine the next conversation state based on the current state and analysis
    """
    # Handle objection if detected
    if 'objection_detected' in analysis and analysis['objection_detected']:
        return ConversationState.OBJECTION_HANDLING
    
    # Normal state progression
    if current_state == ConversationState.GREETING:
        return ConversationState.QUALIFICATION
    
    elif current_state == ConversationState.QUALIFICATION:
        # Check if customer handles bills
        if 'handles_bills' in analysis:
            if analysis['handles_bills']:
                return ConversationState.DEBT_AMOUNT
            else:
                return ConversationState.BILL_RESPONSIBILITY
        return ConversationState.BILL_RESPONSIBILITY
    
    elif current_state == ConversationState.BILL_RESPONSIBILITY:
        # Check if call transfer was accepted
        if 'call_transfer_accepted' in analysis:
            if analysis['call_transfer_accepted']:
                return ConversationState.TRANSFER
            else:
                return ConversationState.CLOSING
        return ConversationState.DEBT_AMOUNT
    
    elif current_state == ConversationState.DEBT_AMOUNT:
        # Check debt amount for qualification
        debt_info = json.loads(customer_info.get('debt_info', '{}'))
        if 'total_amount' in debt_info:
            debt_amount = debt_info['total_amount']
            if debt_amount < MIN_DEBT_AMOUNT:
                # Debt amount too low, disqualify
                return ConversationState.CLOSING
        return ConversationState.CARD_COUNT
    
    elif current_state == ConversationState.CARD_COUNT:
        return ConversationState.PAYMENT_STATUS
    
    elif current_state == ConversationState.PAYMENT_STATUS:
        return ConversationState.EMPLOYMENT
    
    elif current_state == ConversationState.EMPLOYMENT:
        return ConversationState.MONTHLY_PAYMENT
    
    elif current_state == ConversationState.MONTHLY_PAYMENT:
        return ConversationState.QUALIFICATION_COMPLETE
    
    elif current_state == ConversationState.QUALIFICATION_COMPLETE:
        return ConversationState.INTENT_CHECK
    
    elif current_state == ConversationState.INTENT_CHECK:
        # Check if intent was confirmed
        if 'intent_confirmed' in analysis and analysis['intent_confirmed']:
            return ConversationState.TRANSFER
        else:
            return ConversationState.CLOSING
    
    elif current_state == ConversationState.OBJECTION_HANDLING:
        # Check if objection was handled successfully
        if 'objection_handled' in analysis and analysis['objection_handled']:
            # Return to the state before objection
            return customer_info.get('previous_state', ConversationState.QUALIFICATION)
        else:
            return ConversationState.CLOSING
    
    elif current_state == ConversationState.TRANSFER:
        return ConversationState.ENDED
    
    elif current_state == ConversationState.CLOSING:
        return ConversationState.ENDED
    
    else:
        return ConversationState.GREETING

def get_bot_response(state, customer_info, call_data):
    """
    Get the appropriate bot response for a given state
    """
    # For objection handling, use the objection handler
    if state == ConversationState.OBJECTION_HANDLING:
        objection_type = call_data.get('objection_type', 'general')
        return objection_handler.get_objection_response(objection_type, customer_info)
    
    # For other states, use the conversation scripts
    return get_question_for_state(state, customer_info)

def speak_response(room_name, text):
    """
    Speak the response using TTS
    """
    try:
        response = livekit_client.speak_text(room_name, text)
        logger.info(f"TTS response for room {room_name}: {response}")
        return True
    except Exception as e:
        logger.error(f"Error in TTS: {str(e)}")
        return False

def trigger_transfer(call_data, customer_info):
    """
    Trigger the transfer Lambda function
    """
    try:
        # Prepare payload for transfer Lambda
        payload = {
            'call_id': call_data['call_id'],
            'phone_number': call_data.get('phone_number'),
            'customer_info': customer_info,
            'qualification_status': 'qualified',
            'timestamp': datetime.now().isoformat()
        }
        
        # Invoke transfer Lambda
        response = lambda_client.invoke(
            FunctionName=TRANSFER_FUNCTION,
            InvocationType='Event',
            Payload=json.dumps(payload)
        )
        
        logger.info(f"Triggered transfer for call_id: {call_data['call_id']}")
        return True
    except Exception as e:
        logger.error(f"Error triggering transfer: {str(e)}")
        return False

def handle_webhook(event):
    """
    Handle webhook requests for conversation initialization
    """
    try:
        # Parse request data
        body = json.loads(event.get('body', '{}'))
        call_id = body.get('call_id')
        script_id = body.get('script_id', 'debt_reduction_qualification')
        
        if not call_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'call_id is required'})
            }
        
        # Get existing call data or create new entry
        call_data = db_operations.get_call(call_id)
        if not call_data:
            call_data = {
                'call_id': call_id,
                'script_id': script_id,
                'call_state': 'initializing',
                'creation_time': datetime.now().isoformat()
            }
        
        # Update script ID if provided
        if script_id:
            call_data['script_id'] = script_id
        
        # Initialize the conversation
        initialize_conversation(call_data)
        
        # Get the updated call data
        updated_call = db_operations.get_call(call_id)
        
        # Get customer info
        customer_info = db_operations.get_customer_info(call_id)
        
        # Get the initial bot greeting
        initial_state = updated_call.get('current_state', ConversationState.GREETING)
        greeting = get_question_for_state(initial_state, customer_info)
        
        # Save bot greeting transcript
        db_operations.save_transcript(call_id, 'bot', greeting)
        
        # Speak the greeting if room name is available
        if 'room_name' in updated_call:
            speak_response(updated_call['room_name'], greeting)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'call_id': call_id,
                'current_state': initial_state,
                'greeting': greeting
            }),
            'headers': {
                'Content-Type': 'application/json'
            }
        }
    except Exception as e:
        logger.error(f"Error in handle_webhook: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

def handle_transcript(event):
    """
    Handle transcript updates from LiveKit
    """
    try:
        # Parse request data
        body = json.loads(event.get('body', '{}'))
        
        # Extract call_id from path parameter if available
        path_parameters = event.get('pathParameters', {})
        call_id = path_parameters.get('call_id')
        
        # If not in path, try to get from body
        if not call_id:
            call_id = body.get('call_id') or body.get('room_name')
        
        # Extract transcript 
        transcript = body.get('transcript')
        
        # For Deepgram format compatibility
        if not transcript and 'channel' in body and 'alternatives' in body.get('channel', {}):
            alternatives = body.get('channel', {}).get('alternatives', [])
            if alternatives and 'transcript' in alternatives[0]:
                transcript = alternatives[0]['transcript']
        
        if not call_id or not transcript:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'call_id and transcript are required'})
            }
        
        # Get call data
        call_data = db_operations.get_call(call_id)
        if not call_data:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'Call {call_id} not found'})
            }
        
        # Process the transcript
        result = process_user_input(transcript, call_data)
        
        # Speak the response if needed
        if 'room_name' in call_data and 'bot_response' in result:
            speak_response(call_data['room_name'], result['bot_response'])
        
        return {
            'statusCode': 200,
            'body': json.dumps(result),
            'headers': {
                'Content-Type': 'application/json'
            }
        }
    except Exception as e:
        logger.error(f"Error in handle_transcript: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

def handle_voice_events(event):
    """
    Handle voice events from LiveKit (including DTMF)
    """
    try:
        # Parse request data
        body = json.loads(event.get('body', '{}'))
        
        # Extract call_id from path parameter if available
        path_parameters = event.get('pathParameters', {})
        call_id = path_parameters.get('call_id')
        
        # If not in path, try to get from body
        if not call_id:
            call_id = body.get('call_id') or body.get('room_name')
        
        # Check for DTMF events
        dtmf_digit = None
        event_type = body.get('event_type')
        
        if event_type == 'dtmf':
            dtmf_digit = body.get('digit')
        elif 'dtmf' in body:
            dtmf_digit = body.get('dtmf')
        
        if not call_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'call_id is required'})
            }
        
        # Get call data
        call_data = db_operations.get_call(call_id)
        if not call_data:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'Call {call_id} not found'})
            }
        
        # Process voice event
        if dtmf_digit is not None:
            # Process DTMF
            logger.info(f"DTMF digit {dtmf_digit} received for call {call_id}")
            
            # Add to call data
            dtmf_log = json.loads(call_data.get('dtmf_log', '[]'))
            dtmf_log.append({
                'digit': dtmf_digit,
                'timestamp': datetime.now().isoformat()
            })
            call_data['dtmf_log'] = json.dumps(dtmf_log)
            
            # Update call record
            db_operations.update_call(call_data)
            
            return {
                'statusCode': 200,
                'body': json.dumps({'success': True, 'event_type': 'dtmf', 'digit': dtmf_digit}),
                'headers': {
                    'Content-Type': 'application/json'
                }
            }
        else:
            # Handle other voice events (speech start, speech end, etc.)
            logger.info(f"Voice event {event_type} received for call {call_id}")
            
            # Add to call data
            voice_events = json.loads(call_data.get('voice_events', '[]'))
            voice_events.append({
                'event_type': event_type,
                'timestamp': datetime.now().isoformat(),
                'data': body
            })
            call_data['voice_events'] = json.dumps(voice_events)
            
            # Update call record
            db_operations.update_call(call_data)
            
            return {
                'statusCode': 200,
                'body': json.dumps({'success': True, 'event_type': event_type}),
                'headers': {
                    'Content-Type': 'application/json'
                }
            }
    except Exception as e:
        logger.error(f"Error in handle_voice_events: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

def lambda_handler(event, context):
    """
    Main Lambda handler - routes requests based on path
    Compatible with existing API Gateway resources
    """
    try:
        # Log the full event for debugging
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Extract path and HTTP method
        path = event.get('path', '').rstrip('/')
        http_method = event.get('httpMethod', 'POST')
        
        # Log path for debugging
        logger.info(f"Processing request for path: {path}, method: {http_method}")
        
        # Match against existing API Gateway resources
        if path == '/webhook' or path.startswith('/webhook/'):
            # Webhook endpoint used for initialization
            return handle_webhook(event)
            
        elif path == '/transcript' or path.startswith('/transcript/'):
            # Process transcript
            return handle_transcript(event)
            
        elif path == '/voice-events' or path.startswith('/voice-events/'):
            # Process voice events including DTMF
            return handle_voice_events(event)
            
        else:
            # Log unmatched path
            logger.warning(f"Unmatched path: {path}. Check API Gateway configuration.")
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'error': 'Not Found',
                    'message': 'The requested endpoint does not exist',
                    'path': path
                }),
                'headers': {
                    'Content-Type': 'application/json'
                }
            }
    except Exception as e:
        logger.error(f"Unhandled exception in lambda_handler: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }
