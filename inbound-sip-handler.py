"""
Inbound SIP Call Handler Lambda Function

This Lambda function handles inbound SIP calls from LiveKit, creates a room,
sets up voice processing pipeline, and starts the conversation.
"""

import os
import re
import json
import time
import logging
import boto3
import uuid
from urllib.parse import parse_qs, urlparse
import sys

# Add the Lambda layer directories to the Python path
sys.path.append('/opt')
sys.path.append('/opt/python')

# Import shared modules
try:
    from shared import livekit_client
except ImportError:
    # For local development or when running without Lambda layers
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("livekit_client", "../shared/livekit_client.py")
    livekit_client = importlib.util.module_from_spec(spec)
    sys.modules["livekit_client"] = livekit_client
    spec.loader.exec_module(livekit_client)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
lambda_client = boto3.client('lambda')
dynamodb = boto3.resource('dynamodb')
calls_table = dynamodb.Table(os.environ.get('CALLS_TABLE', 'ai_voice_bot_calls'))
customer_info_table = dynamodb.Table(os.environ.get('CUSTOMER_INFO_TABLE', 'ai_voice_bot_customer_info'))

def lambda_handler(event, context):
    """Lambda handler for inbound SIP calls"""
    
    logger.info(f"Received inbound SIP event: {event}")
    
    # Extract the SIP URI from the request body
    try:
        # Parse the request body
        if 'body' in event:
            body = json.loads(event['body'])
            
            # Try different formats that LiveKit might send
            sip_uri = None
            
            # Check for sip_uri field
            if 'sip_uri' in body:
                sip_uri = body['sip_uri']
            # Check for address field (LiveKit format)
            elif 'address' in body:
                sip_uri = body['address']
            # Check for fromUri field (another possible format)
            elif 'fromUri' in body:
                sip_uri = body['fromUri']
            # Check for From header in SIP request
            elif 'headers' in body and 'From' in body['headers']:
                from_header = body['headers']['From']
                # Extract URI from From header (format: "<sip:user@domain>")
                if '<' in from_header and '>' in from_header:
                    sip_uri = from_header.split('<')[1].split('>')[0]
            
            # Log the extracted URI for debugging
            logger.info(f"Processing SIP call for URI: {sip_uri}")
            
            # Validate SIP URI format
            if not sip_uri:
                logger.error("No SIP URI found in request")
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'message': 'Missing SIP URI in request',
                        'details': 'Required field sip_uri, address, or fromUri not found'
                    })
                }
                
            # Extract call_id from SIP URI using our improved function
            call_id = extract_call_id_from_sip_uri(sip_uri)
            
            # If no valid pattern was found
            if not call_id:
                logger.error(f"No valid call ID pattern found in SIP URI: {sip_uri}")
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'message': 'Invalid SIP URI format',
                        'details': 'Expected format: +[number]@domain or call_[alphanumeric]@domain'
                    })
                }
            
            # Process the call with the extracted call_id
            # ... rest of your code ...
                
    except Exception as e:
        logger.error(f"Error processing inbound SIP call: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error processing inbound SIP call',
                'error': str(e)
            })
        }
def handle_inbound_sip_call(event):
    """
    Handle inbound SIP call from LiveKit
    
    Args:
        event (dict): Lambda event
        
    Returns:
        dict: Response to the webhook caller
    """
    # Parse the SIP URI to extract call ID or phone number
    # Two supported formats:
    # 1. call_[alphanumeric]@2q4tmd28dgf.sip.livekit.cloud  (legacy)
    # 2. +14155552671@2q4tmd28dgf.sip.livekit.cloud (E.164 format)
    try:
        body = json.loads(event.get('body', '{}'))
        sip_uri = body.get('address', '')
        
        logger.info(f"Processing SIP call for URI: {sip_uri}")
        
        # Extract call ID or phone number from SIP URI
        identifier = extract_call_id_from_sip_uri(sip_uri)
        if not identifier:
            logger.error(f"Invalid SIP URI format: {sip_uri}")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'message': 'Invalid SIP URI format',
                    'details': 'Expected format: +[number]@domain or call_[alphanumeric]@domain'
                })
            }
        
        # Determine if this is a phone number (E.164) or a call_id
        is_e164 = identifier.startswith('+')
        
        # For E.164 numbers, we use the number itself as both the call_id and room_name
        if is_e164:
            call_id = identifier  # Use E.164 formatted number as call_id
            # Ensure the phone number is in E.164 format for LiveKit
            phone_number = identifier
            logger.info(f"Using E.164 phone number as call ID: {call_id}")
        else:
            # Legacy format with call_id
            call_id = identifier
            # Extract phone number from the call_id or use a placeholder
            phone_number = sip_uri.split('@')[0]
            if phone_number == call_id and not phone_number.startswith('+'):
                # Try to format as E.164 if it contains digits
                if any(c.isdigit() for c in phone_number):
                    formatted = format_phone_number_e164(phone_number)
                    if formatted:
                        phone_number = formatted
        
        # Check if call already exists in the database
        call_data = get_call_data(call_id)
        if not call_data:
            # Initialize call data if not exists
            call_data = initialize_call_data(call_id, phone_number)
        
        # Create LiveKit room - use the same identifier for the room name
        room_name = call_id
        
        # Create the room using the verified method from our tests
        create_room_result = livekit_client.create_room(room_name)
        logger.info(f"Created LiveKit room: {room_name}")
        
        # Set up voice processing pipeline
        voice_pipeline_result = livekit_client.setup_voice_pipeline(room_name)
        logger.info(f"Set up voice pipeline for room: {room_name}")
        
        # Add SIP participant to the room
        sip_result = livekit_client.add_sip_participant(room_name, sip_uri)
        logger.info(f"Added SIP participant {sip_uri} to room: {room_name}")
        
        # Update call data with room name
        update_call_data(call_id, {
            'room_name': room_name,
            'call_state': 'active',
            'current_state': 'greeting',  # Initial conversation state
            'phone_number': phone_number  # Ensure phone number is stored
        })
        
        # Start conversation manager
        start_conversation(call_id, room_name)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Inbound SIP call processed successfully',
                'call_id': call_id,
                'room_name': room_name,
                'phone_number': phone_number,
                'e164_format': is_e164
            })
        }
    except Exception as e:
        logger.error(f"Error processing inbound SIP call: {str(e)}")
        raise

def extract_call_id_from_sip_uri(sip_uri):
    """
    Extract the call_id from a SIP URI
    Handles both call_* and +* formats
    """
    if not sip_uri:
        return None
        
    # For call_id format (call_something@domain)
    call_match = re.search(r'sip:call_([a-zA-Z0-9_\-]+)@', sip_uri)
    if call_match:
        return f"call_{call_match.group(1)}"
        
    # For call_id format with sip: in the middle of the URI (sometimes happens)
    call_match2 = re.search(r'call_([a-zA-Z0-9_\-]+)@', sip_uri)
    if call_match2:
        return f"call_{call_match2.group(1)}"
        
    # For phone number format (+123456789@domain)
    phone_match = re.search(r'sip:(\+[0-9]+)@', sip_uri)
    if phone_match:
        return phone_match.group(1)
        
    # For phone number without sip: prefix
    phone_match2 = re.search(r'(\+[0-9]+)@', sip_uri)
    if phone_match2:
        return phone_match2.group(1)
        
    # If no patterns match
    return None

def format_phone_number_e164(phone_number):
    """
    Format a phone number in E.164 format (required by LiveKit)
    
    Args:
        phone_number (str): Input phone number in any format
        
    Returns:
        str: Phone number in E.164 format (e.g., +14155552671)
    """
    # Already has + prefix but may contain non-digits
    if phone_number.startswith('+'):
        # Remove any non-digit characters after the +
        digits_only = ''.join(filter(str.isdigit, phone_number[1:]))
        return f"+{digits_only}"
        
    # Remove any non-digit characters
    digits_only = ''.join(filter(str.isdigit, phone_number))
    
    # Handle country code
    if len(digits_only) == 10:  # US number without country code
        return f"+1{digits_only}"
    elif len(digits_only) > 10:  # Has country code
        if digits_only.startswith('1') and len(digits_only) == 11:  # US number
            return f"+{digits_only}"
        else:
            return f"+{digits_only}"
    
    # Invalid number format
    logger.warning(f"Invalid phone number format: {phone_number}")
    return None

def get_call_data(call_id):
    """
    Get call data from DynamoDB
    
    Args:
        call_id (str): Call ID
        
    Returns:
        dict: Call data
    """
    try:
        response = calls_table.get_item(
            Key={'call_id': call_id}
        )
        return response.get('Item')
    except Exception as e:
        logger.error(f"Error getting call data: {str(e)}")
        return None

def initialize_call_data(call_id, phone_number):
    """
    Initialize call data in DynamoDB
    
    Args:
        call_id (str): Call ID
        phone_number (str): Phone number
        
    Returns:
        dict: Call data
    """
    # Extract actual phone number from SIP URI if present
    if '@' in phone_number:
        phone_number = phone_number.split('@')[0]
    
    # Create timestamp for call start
    timestamp = int(time.time())
    
    # Initialize call data
    call_data = {
        'call_id': call_id,
        'phone_number': phone_number,
        'start_timestamp': timestamp,
        'call_state': 'initiated',
        'current_state': 'init',
        'qualification_status': 'pending',
        'intent_verified': False,
        'transfer_status': 'pending',
        'objection_attempts': 0,
        'last_update': timestamp,
        'room_name': call_id  # Use call_id as room_name for consistency
    }
    
    try:
        # Save to DynamoDB
        calls_table.put_item(Item=call_data)
        
        # Initialize customer info
        customer_info_table.put_item(
            Item={
                'call_id': call_id,
                'phone_number': phone_number,
                'handles_bills': True,  # Default to true until determined otherwise
                'debt_info': {},
                'objections': []
            }
        )
        
        return call_data
    except Exception as e:
        logger.error(f"Error initializing call data: {str(e)}")
        raise

def update_call_data(call_id, updates):
    """
    Update call data in DynamoDB
    
    Args:
        call_id (str): Call ID
        updates (dict): Updates to apply
        
    Returns:
        dict: Updated call data
    """
    try:
        # Prepare update expression
        update_expression = "SET #last_update = :timestamp"
        expression_attribute_names = {
            '#last_update': 'last_update'
        }
        expression_attribute_values = {
            ':timestamp': int(time.time())
        }
        
        # Add updates to the expression
        for key, value in updates.items():
            if key != 'call_id':  # Skip the key
                update_expression += f", #{key} = :{key}"
                expression_attribute_names[f'#{key}'] = key
                expression_attribute_values[f':{key}'] = value
        
        # Update item in DynamoDB
        response = calls_table.update_item(
            Key={'call_id': call_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues='ALL_NEW'
        )
        
        return response.get('Attributes')
    except Exception as e:
        logger.error(f"Error updating call data: {str(e)}")
        raise

def start_conversation(call_id, room_name):
    """
    Start conversation by invoking the conversation manager Lambda
    
    Args:
        call_id (str): Call ID
        room_name (str): LiveKit room name
        
    Returns:
        dict: Lambda invocation result
    """
    try:
        # Invoke conversation manager Lambda asynchronously
        conversation_manager_function = os.environ.get(
            'CONVERSATION_MANAGER_FUNCTION', 
            'ai-voice-bot-conversation-manager'
        )
        
        payload = {
            'call_id': call_id,
            'room_name': room_name,
            'event_type': 'start_conversation'
        }
        
        response = lambda_client.invoke(
            FunctionName=conversation_manager_function,
            InvocationType='Event',  # Asynchronous
            Payload=json.dumps(payload)
        )
        
        logger.info(f"Started conversation for call ID: {call_id}")
        return {
            'status': 'success',
            'message': f"Started conversation for call ID: {call_id}"
        }
    except Exception as e:
        logger.error(f"Error starting conversation: {str(e)}")
        raise
