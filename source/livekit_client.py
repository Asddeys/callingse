"""
LiveKit Client Module

Provides functions for interacting with LiveKit services for audio
processing, including room management, voice pipeline setup,
Deepgram integration for STT, Cartesia for TTS, and Silero VAD for
silence detection with noise suppression.

This version includes enhanced support for E.164 phone number format and
updated API endpoints for LiveKit's latest features.
"""

import os
import json
import time
import requests
import logging
import jwt
from datetime import datetime, timedelta
import uuid

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# LiveKit API configuration
LIVEKIT_API_URL = os.environ.get('LIVEKIT_API_URL', 'https://api.livekit.io')
LIVEKIT_API_KEY = os.environ.get('LIVEKIT_API_KEY')
LIVEKIT_API_SECRET = os.environ.get('LIVEKIT_API_SECRET')
LIVEKIT_SIP_DOMAIN = os.environ.get('LIVEKIT_SIP_DOMAIN', '2q4tmd28dgf.sip.livekit.cloud')

# Deepgram configuration
DEEPGRAM_API_KEY = os.environ.get('DEEPGRAM_API_KEY')

# Cartesia TTS configuration
CARTESIA_API_KEY = os.environ.get('CARTESIA_API_KEY')

# Voice settings
DEFAULT_VOICE = os.environ.get('DEFAULT_VOICE', 'alloy') # Using one of the newer voices
VOICE_LANGUAGE = os.environ.get('VOICE_LANGUAGE', 'en-US')

def create_jwt_token(permissions=None):
    """
    Create a JWT token for LiveKit API authentication with correct permissions
    
    Args:
        permissions (dict): Permission claims to include in token
        
    Returns:
        str: JWT token
    """
    api_key = LIVEKIT_API_KEY
    api_secret = LIVEKIT_API_SECRET
    
    if not api_key or not api_secret:
        raise ValueError("LiveKit API credentials not configured")
    
    # Default permissions if none provided
    if permissions is None:
        permissions = {
            "video": {
                "roomCreate": True,
                "roomList": True,
                "roomAdmin": True
            },
            "sip": {
                "create": True,
                "list": True,
                "admin": True
            }
        }
    
    # Create token payload
    now = int(time.time())
    payload = {
        "iss": api_key,
        "nbf": now,
        "exp": now + 3600,  # 1 hour expiration
        "sub": "server"  # Using 'server' as subject for API calls
    }
    
    # Add permissions to payload
    for key, value in permissions.items():
        payload[key] = value
    
    # Create and sign token
    token = jwt.encode(payload, api_secret, algorithm='HS256')
    if isinstance(token, bytes):
        return token.decode('utf-8')
    return token

def make_api_request(endpoint, payload=None, method="POST"):
    """
    Make a request to the LiveKit API
    
    Args:
        endpoint (str): API endpoint
        payload (dict): Request payload
        method (str): HTTP method (GET, POST, etc.)
        
    Returns:
        dict: API response
    """
    api_url = LIVEKIT_API_URL
    
    # Determine token permissions based on endpoint
    permissions = None
    if "rooms" in endpoint and "add_sip" in endpoint:
        permissions = {
            "video": {"roomAdmin": True},
            "sip": {"create": True, "list": True, "admin": True}
        }
    elif "rooms" in endpoint:
        permissions = {"video": {"roomCreate": True, "roomList": True, "roomAdmin": True}}
    elif "sip" in endpoint:
        permissions = {"sip": {"create": True, "list": True, "admin": True}}
    else:
        # Default permissions for other endpoints
        permissions = {
            "video": {"roomCreate": True, "roomList": True, "roomAdmin": True},
            "sip": {"create": True, "list": True, "admin": True}
        }
        
    # Create token with appropriate permissions
    token = create_jwt_token(permissions)
    
    # Ensure endpoint starts with /
    if not endpoint.startswith('/'):
        endpoint = f"/{endpoint}"
    
    # Build full URL
    url = f"{api_url}{endpoint}"
    
    # Set headers
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Make request
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers)
        else:  # POST or other methods
            response = requests.post(url, headers=headers, json=payload)
        
        # Check response
        if response.status_code in [200, 201]:
            # Some LiveKit endpoints return empty responses for success
            if not response.text or response.text.strip() == "":
                return {"status": "success"}
            
            # Try to parse as JSON
            try:
                return response.json()
            except:
                # Return text if not JSON
                return {"status": "success", "text": response.text}
        else:
            # Handle error
            error_msg = f"API request failed: {response.status_code} - {response.text}"
            logger.error(error_msg)
            return {"status": "error", "error": error_msg}
    except Exception as e:
        logger.error(f"Exception in API request: {str(e)}")
        return {"status": "error", "error": str(e)}

def create_room(room_name):
    """
    Create a LiveKit room with updated API
    
    Args:
        room_name (str): Name of the room to create
        
    Returns:
        dict: Room creation response
    """
    # API endpoint for room creation (using TWIRP)
    endpoint = "/twirp/livekit.RoomService/CreateRoom"
    
    # Prepare payload
    payload = {
        "name": room_name,
        "emptyTimeout": 300,  # 5 minutes timeout for empty rooms
        "maxParticipants": 10,
        "metadata": json.dumps({"audio_only": True})
    }
    
    # Make API request
    response = make_api_request(endpoint, payload)
    
    logger.info(f"Created LiveKit room: {room_name}")
    return response

def get_room(room_name):
    """
    Get information about a LiveKit room
    
    Args:
        room_name (str): Name of the room
        
    Returns:
        dict: Room information
    """
    # API endpoint for getting room info (using TWIRP)
    endpoint = "/twirp/livekit.RoomService/GetRoom"
    
    # Prepare payload
    payload = {
        "name": room_name
    }
    
    # Make API request
    response = make_api_request(endpoint, payload)
    
    return response

def close_room(room_name):
    """
    Close a LiveKit room
    
    Args:
        room_name (str): Name of the room to close
        
    Returns:
        dict: Room deletion response
    """
    # API endpoint for deleting room (using TWIRP)
    endpoint = "/twirp/livekit.RoomService/DeleteRoom"
    
    # Prepare payload
    payload = {
        "name": room_name
    }
    
    # Make API request
    response = make_api_request(endpoint, payload)
    
    logger.info(f"Closed LiveKit room: {room_name}")
    return response

def setup_voice_pipeline(room_name, call_id=None):
    """
    Configure voice processing pipeline for a room with latest LiveKit API
    
    Args:
        room_name (str): Name of the room
        call_id (str): Optional call ID for webhook URLs
        
    Returns:
        dict: Configuration response
    """
    # Use room_name as call_id if not provided
    if call_id is None:
        call_id = room_name
        
    # API endpoint for voice processing setup using the latest TWIRP API
    endpoint = "/twirp/livekit.RoomService/CreateEgress"
    
    # API Gateway URL - replace with your actual API Gateway URL
    api_gateway_url = os.environ.get('API_GATEWAY_URL', 'https://your-api-gateway.amazonaws.com')
    
    # Prepare payload with latest LiveKit voice processing options
    payload = {
        "room_name": room_name,
        "audio_only": True,  # Audio-only processing for voice bot
        "egress": {
            "dtmf": {
                "enabled": True  # Enable DTMF detection
            },
            "noise_suppression": {
                "enabled": True,
                "level": "HIGH"  # Options: "OFF", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"
            },
            "vad": {
                "enabled": True,
                "silence_threshold_ms": 1000,  # Time of silence before considering speech ended
                "speech_threshold_ms": 300,    # Time of speech before considering speech detected
                "mode": "QUALITY"              # "QUALITY" or "LOW_BITRATE"
            },
            "transcription": {
                "enabled": True,
                "provider": "deepgram",
                "language": "en-US",
                "model": "nova-2",        # Latest Deepgram model
                "tier": "enhanced",       # Quality tier
                "interim_results": True,  # Get real-time partial results
                "profanity_filter": False,
                "redact_pii": False,
                "webhook_url": f"{api_gateway_url}/v1/transcripts/{call_id}"
            }
        }
    }
    
    # Make API request
    response = make_api_request(endpoint, payload)
    
    # Configure additional voice services (TTS and recording) if needed
    # This maintains backward compatibility with older code while using new API structure
    tts_config = {
        "service": "cartesia",
        "voice": DEFAULT_VOICE
    }
    
    recording_config = {
        "enabled": True,
        "webhook_url": f"{api_gateway_url}/v1/recordings/{call_id}"
    }
    
    # Log the configuration
    logger.info(f"Set up voice pipeline for room: {room_name} with latest API parameters")
    return response

def speak_text(room_name, text):
    """
    Speak text using TTS via LiveKit
    
    Args:
        room_name (str): Name of the room
        text (str): Text to speak
        
    Returns:
        dict: TTS response
    """
    # API endpoint for TTS
    endpoint = f"/v1/rooms/{room_name}/tts/speak"
    
    # Prepare payload
    payload = {
        "text": text,
        "voice": DEFAULT_VOICE
    }
    
    # Make API request
    response = make_api_request(endpoint, payload)
    
    logger.info(f"Speaking text in room: {room_name}")
    return response

def add_sip_participant(room_name, sip_uri):
    """
    Add a SIP participant to a LiveKit room
    Updated to support E.164 phone number format
    
    Args:
        room_name (str): Name of the room
        sip_uri (str): SIP URI to add (can be call_id@ or +phonenumber@ format)
        
    Returns:
        dict: Participant addition response
    """
    # API endpoint for adding SIP participant
    endpoint = f"/v1/rooms/{room_name}/participants/add_sip"
    
    # Determine identity based on SIP URI
    identity = "customer"
    
    # Extract the user part of the SIP URI
    if '@' in sip_uri:
        user_part = sip_uri.split('@')[0]
        if user_part.startswith('sip:'):
            user_part = user_part[4:]  # Remove 'sip:' prefix if present
            
        if user_part.startswith('+'):
            # If it's an E.164 number, use it as the identity
            identity = user_part
        elif user_part.startswith('call_'):
            # If it's a call_id, use it as the identity
            identity = user_part
    
    # Make sure sip_uri has sip: prefix
    if not sip_uri.startswith('sip:'):
        sip_uri = f"sip:{sip_uri}"
    
    # Prepare payload
    payload = {
        "address": sip_uri,
        "identity": identity,
        "client_metadata": json.dumps({
            "type": "customer",
            "auto_subscribe": True
        })
    }
    
    # Make API request
    response = make_api_request(endpoint, payload)
    
    logger.info(f"Added SIP participant {sip_uri} to room: {room_name}")
    return response

def create_e164_dispatch_rule():
    """
    Create a SIP dispatch rule for E.164 phone numbers
    
    Returns:
        dict: Rule creation response
    """
    # API endpoint for dispatch rule creation
    endpoint = "/v1/sip/dispatch/rules/create"
    
    # API Gateway URL - replace with your actual API Gateway URL
    api_gateway_url = os.environ.get('API_GATEWAY_URL', 'https://your-api-gateway.amazonaws.com')
    
    # Prepare payload
    payload = {
        "name": "e164-phone-number-rule",
        "pattern": "^(\\+[0-9]+)@.*$",
        "priority": 200,
        "roomNameRegex": {
            "roomNameRegex": "$1",
            "createIfNotExists": True
        },
        "webhook_url": f"{api_gateway_url}/v1/inbound_sip"
    }
    
    # Make API request
    response = make_api_request(endpoint, payload)
    
    logger.info(f"Created E.164 SIP dispatch rule")
    return response

def create_call_prefix_dispatch_rule():
    """
    Create a SIP dispatch rule for call_id prefix
    
    Returns:
        dict: Rule creation response
    """
    # API endpoint for dispatch rule creation
    endpoint = "/v1/sip/dispatch/rules/create"
    
    # API Gateway URL - replace with your actual API Gateway URL
    api_gateway_url = os.environ.get('API_GATEWAY_URL', 'https://your-api-gateway.amazonaws.com')
    
    # Prepare payload
    payload = {
        "name": "call-prefix-rule",
        "pattern": "^(call_[a-z0-9]+)@.*$",
        "priority": 100,
        "roomNameRegex": {
            "roomNameRegex": "$1",
            "createIfNotExists": True
        },
        "webhook_url": f"{api_gateway_url}/v1/inbound_sip"
    }
    
    # Make API request
    response = make_api_request(endpoint, payload)
    
    logger.info(f"Created call prefix SIP dispatch rule")
    return response

def get_sip_dispatch_rules():
    """
    Get all SIP dispatch rules
    
    Returns:
        dict: List of rules
    """
    # API endpoint for listing rules
    endpoint = "/v1/sip/dispatch/rules/list"
    
    # Make API request
    response = make_api_request(endpoint, {}, "GET")
    
    return response

def format_phone_number_e164(phone_number):
    """
    Format a phone number in E.164 format (required by LiveKit)
    
    Args:
        phone_number (str): Input phone number in any format
        
    Returns:
        str: Phone number in E.164 format (e.g., +14155552671)
    """
    # Skip if None or empty
    if not phone_number:
        return None
        
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

def get_call_status(call_id, room_name=None):
    """
    Get call status from LiveKit
    
    Args:
        call_id (str): Call ID
        room_name (str, optional): Room name. Defaults to call_id.
        
    Returns:
        dict: Room status
    """
    # Use call_id as room_name if not provided
    if room_name is None:
        room_name = call_id
        
    # Get room status using updated TWIRP API
    endpoint = "/twirp/livekit.RoomService/GetRoom"
    
    # Prepare payload
    payload = {
        "name": room_name
    }
    
    # Make API request
    response = make_api_request(endpoint, payload)
    
    return response

def get_sip_uri(call_id):
    """
    Get a SIP URI for a call ID or E.164 phone number
    
    Args:
        call_id (str): Call ID or E.164 phone number
        
    Returns:
        str: SIP URI
    """
    # Check if this is already a SIP URI
    if '@' in call_id:
        if call_id.startswith('sip:'):
            return call_id
        else:
            return f"sip:{call_id}"
            
    # Otherwise format as SIP URI
    return f"sip:{call_id}@{LIVEKIT_SIP_DOMAIN}"
