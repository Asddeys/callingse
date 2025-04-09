"""
Database Operations Module

Provides functions for interacting with DynamoDB tables.
"""

import os
import json
import logging
import boto3
from datetime import datetime

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB resource
dynamodb = boto3.resource('dynamodb')

# DynamoDB table names
CALLS_TABLE = os.environ.get('CALLS_TABLE', 'DebtReduction_Calls')
CUSTOMER_INFO_TABLE = os.environ.get('CUSTOMER_INFO_TABLE', 'DebtReduction_CustomerInfo')
TRANSCRIPTS_TABLE = os.environ.get('TRANSCRIPTS_TABLE', 'DebtReduction_Transcripts')

def get_call(call_id):
    """
    Retrieve call data from DynamoDB
    """
    table = dynamodb.Table(CALLS_TABLE)
    
    try:
        response = table.get_item(
            Key={
                'call_id': call_id
            }
        )
        
        return response.get('Item')
    
    except Exception as e:
        logger.error(f"Error retrieving call data for call_id {call_id}: {str(e)}")
        raise

def update_call(call_data):
    """
    Update call data in DynamoDB
    """
    table = dynamodb.Table(CALLS_TABLE)
    
    # Ensure last_update timestamp
    if 'last_update' not in call_data:
        call_data['last_update'] = datetime.now().isoformat()
    
    try:
        response = table.put_item(
            Item=call_data
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Error updating call data for call_id {call_data.get('call_id')}: {str(e)}")
        raise

def get_customer_info(call_id):
    """
    Retrieve customer information from DynamoDB
    """
    table = dynamodb.Table(CUSTOMER_INFO_TABLE)
    
    try:
        response = table.get_item(
            Key={
                'call_id': call_id
            }
        )
        
        return response.get('Item')
    
    except Exception as e:
        logger.error(f"Error retrieving customer info for call_id {call_id}: {str(e)}")
        raise

def update_customer_info(customer_info):
    """
    Update customer information in DynamoDB
    """
    table = dynamodb.Table(CUSTOMER_INFO_TABLE)
    
    # Ensure last_update timestamp
    if 'last_update' not in customer_info:
        customer_info['last_update'] = datetime.now().isoformat()
    
    try:
        response = table.put_item(
            Item=customer_info
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Error updating customer info for call_id {customer_info.get('call_id')}: {str(e)}")
        raise

def save_transcript(call_id, speaker, text):
    """
    Save transcript entry to DynamoDB
    """
    table = dynamodb.Table(TRANSCRIPTS_TABLE)
    
    # Generate unique ID for transcript entry
    timestamp = datetime.now().isoformat()
    transcript_id = f"{call_id}_{timestamp}"
    
    transcript_entry = {
        'transcript_id': transcript_id,
        'call_id': call_id,
        'speaker': speaker,
        'text': text,
        'timestamp': timestamp
    }
    
    try:
        response = table.put_item(
            Item=transcript_entry
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Error saving transcript for call_id {call_id}: {str(e)}")
        raise

def get_call_transcripts(call_id):
    """
    Retrieve all transcripts for a call
    """
    table = dynamodb.Table(TRANSCRIPTS_TABLE)
    
    try:
        response = table.query(
            IndexName='call_id-timestamp-index',
            KeyConditionExpression='call_id = :call_id',
            ExpressionAttributeValues={
                ':call_id': call_id
            },
            ScanIndexForward=True  # Sort by timestamp ascending
        )
        
        return response.get('Items', [])
    
    except Exception as e:
        logger.error(f"Error retrieving transcripts for call_id {call_id}: {str(e)}")
        raise
