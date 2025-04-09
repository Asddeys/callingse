"""
Transfer Handler Lambda Function

This Lambda function handles transferring qualified calls
back to ViciDial agents.
"""

import json
import os
import boto3
import logging
import requests
from datetime import datetime

# Import shared modules
import sys
sys.path.append('/opt')
from shared import db_operations, livekit_client

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# ViciDial API configuration
VICIDIAL_API_URL = os.environ.get('VICIDIAL_API_URL', 'https://your-vicidial-server.com/api.php')
VICIDIAL_API_USER = os.environ.get('VICIDIAL_API_USER', 'api_user')
VICIDIAL_API_PASS = os.environ.get('VICIDIAL_API_PASS', 'api_pass')
VICIDIAL_AGENT_GROUP = os.environ.get('VICIDIAL_AGENT_GROUP', 'SALES')

def transfer_to_vicidial(call_data, customer_info):
    """
    Transfer the call back to ViciDial and pass customer data
    """
    try:
        call_id = call_data['call_id']
        vicidial_id = call_data.get('vicidial_id', '')
        phone_number = call_data.get('phone_number', '')
        
        # Extract customer information
        first_name = customer_info.get('first_name', '')
        last_name = customer_info.get('last_name', '')
        debt_info = json.loads(customer_info.get('debt_info', '{}'))
        
        # Build transfer payload for ViciDial API
        payload = {
            'user': VICIDIAL_API_USER,
            'pass': VICIDIAL_API_PASS,
            'function': 'external_transfer',
            'call_id': vicidial_id or call_id,
            'phone_number': phone_number,
            'agent_group': VICIDIAL_AGENT_GROUP,
            'customer_data': json.dumps({
                'first_name': first_name,
                'last_name': last_name,
                'debt_amount': debt_info.get('total_amount', ''),
                'card_count': debt_info.get('card_count', ''),
                'payment_status': debt_info.get('payment_status', ''),
                'employment_status': debt_info.get('employment_status', ''),
                'monthly_payment': debt_info.get('monthly_payment', ''),
                'qualification_status': call_data.get('qualification_status', '')
            })
        }
        
        # Call ViciDial API to transfer the call
        response = requests.post(VICIDIAL_API_URL, data=payload)
        response_data = response.json()
        
        # Check if transfer was successful
        if response.status_code == 200 and response_data.get('result') == 'success':
            logger.info(f"Successfully transferred call {call_id} to ViciDial")
            return True, response_data
        else:
            error_msg = f"Failed to transfer call {call_id} to ViciDial: {response_data.get('message', 'Unknown error')}"
            logger.error(error_msg)
            return False, {'error': error_msg}
    
    except Exception as e:
        logger.error(f"Error transferring call to ViciDial: {str(e)}")
        return False, {'error': str(e)}

def update_call_status(call_data, transfer_result, transfer_details):
    """
    Update the call status in DynamoDB with transfer results
    """
    try:
        # Update call data
        call_data['transfer_status'] = 'completed' if transfer_result else 'failed'
        call_data['transfer_details'] = json.dumps(transfer_details)
        call_data['last_update'] = datetime.now().isoformat()
        
        # If transfer failed, update call state to ended
        if not transfer_result:
            call_data['call_state'] = 'ended'
            call_data['end_timestamp'] = datetime.now().isoformat()
        
        # Update call in DynamoDB
        db_operations.update_call(call_data)
        
        return True
    except Exception as e:
        logger.error(f"Error updating call status: {str(e)}")
        raise

def lambda_handler(event, context):
    """
    Main Lambda handler function for transfer handling
    """
    try:
        logger.info(f"Received transfer event: {json.dumps(event)}")
        
        # Extract call ID from event
        call_id = event.get('call_id')
        if not call_id:
            raise ValueError("Missing call_id in event")
        
        # Get call data and customer info
        call_data = db_operations.get_call(call_id)
        customer_info = db_operations.get_customer_info(call_id)
        
        # Execute transfer to ViciDial
        transfer_result, transfer_details = transfer_to_vicidial(call_data, customer_info)
        
        # Update call status
        update_call_status(call_data, transfer_result, transfer_details)
        
        # Return response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Transfer processed',
                'call_id': call_id,
                'success': transfer_result,
                'details': transfer_details
            })
        }
    except Exception as e:
        logger.error(f"Error in transfer handler: {str(e)}")
        
        # Return error response
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f'Error handling transfer: {str(e)}'
            })
        }
