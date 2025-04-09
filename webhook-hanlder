import os
import json
import time
import uuid
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Webhook handler for inbound calls
    Now simplified to just generate a call_id without creating a LiveKit room
    """
    try:
        # Parse request
        logger.info(f"Received webhook request: {json.dumps(event)}")
        
        # For API Gateway proxy integration
        if 'body' in event:
            try:
                body = json.loads(event['body'])
            except:
                body = event['body']
        else:
            body = event
        
        # Extract call info
        phone_number = body.get('phone_number', '')
        script_id = body.get('script_id', '')
        ingroup = body.get('ingroup', '')
        vicidial_id = body.get('vicidial_id', '')
        agent_id = body.get('agent_id', '')
        
        # Generate a consistent call_id format
        timestamp = int(time.time())
        random_id = uuid.uuid4().hex[:8]
        call_id = f"call_{timestamp}{random_id}"
        
        # Create a SIP URI
        sip_domain = "2q4tmd28dgf.sip.livekit.cloud"  # Your LiveKit SIP domain
        sip_uri = f"sip:{call_id}@{sip_domain}"
        
        # Store call details if needed (DynamoDB, etc.)
        # ...
        
        # Send event to conversation manager to prepare for the call
        # (but don't wait for it to complete)
        import boto3
        lambda_client = boto3.client('lambda')
        
        conversation_event = {
            'call_id': call_id,
            'phone_number': phone_number,
            'script_id': script_id,
            'ingroup': ingroup,
            'vicidial_id': vicidial_id,
            'agent_id': agent_id,
            'call_type': 'inbound',
            'start_timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.%f', time.gmtime()),
            'call_state': 'initiated',
            'qualification_status': 'pending',
            'intent_verified': False,
            'transfer_status': 'pending',
            'room_name': call_id,
            'source': 'vicidial'
        }
        
        # Invoke asynchronously (don't wait for completion)
        lambda_client.invoke(
            FunctionName='ai-voice-sales-bot-conversation-manager',
            InvocationType='Event',
            Payload=json.dumps(conversation_event)
        )
        
        logger.info(f"Generated call_id: {call_id} and notified conversation manager")
        
        # Return the call_id and SIP URI
        response = {
            'message': 'Call received and processing initiated',
            'call_id': call_id,
            'sip_uri': sip_uri,
            'status': 'success'
        }
        
        # For API Gateway compatibility
        return {
            'statusCode': 200,
            'body': json.dumps(response),
            'headers': {
                'Content-Type': 'application/json'
            }
        }
        
    except Exception as e:
        logger.error(f"Error handling webhook: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f'Error processing webhook: {str(e)}',
                'status': 'error'
            }),
            'headers': {
                'Content-Type': 'application/json'
            }
        }
