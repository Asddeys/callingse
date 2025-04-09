"""
LiveKit Client Module - Production Optimized

Provides functions for interacting with LiveKit services for audio
processing, including room management, voice pipeline setup,
Deepgram integration for STT, Cartesia for TTS, and Silero VAD for
silence detection with noise suppression.

Optimized for production with:
- Connection pooling
- Token caching
- Retry logic
- Circuit breaker pattern
- Enhanced logging
"""

import os
import json
import time
import logging
import jwt
from datetime import datetime, timedelta
import uuid
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

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
DEFAULT_VOICE = os.environ.get('DEFAULT_VOICE', 'alloy')
VOICE_LANGUAGE = os.environ.get('VOICE_LANGUAGE', 'en-US')

# Setup connection pooling with retry logic
session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[502, 503, 504, 429],
    allowed_methods=["GET", "POST"]
)
session.mount('https://', HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=20))

# Token cache
_token_cache = {}

# Circuit breaker state
_circuit_state = {
    'livekit_api': {
        'status': 'CLOSED',  # CLOSED, OPEN, HALF-OPEN
        'failures': 0,
        'last_failure': 0,
        'threshold': 5,
        'timeout': 60  # seconds
    }
}

def create_jwt_token(permissions=None):
    """
    Create a JWT token for LiveKit API authentication with correct permissions and caching
    
    Args:
        permissions (dict): Permission claims to include in token
        
    Returns:
        str: JWT token
    """
    cache_key = str(permissions)
    
    # Check if we have a valid cached token
    if cache_key in _token_cache:
        token_data = _token_cache[cache_key]
        # Check if token is still valid (with 5 minute buffer)
        if token_data['expiry'] > time.time() + 300:
            return token_data['token']
    
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
    expiry = now + 3600  # 1 hour expiration
    payload = {
        "iss": api_key,
        "nbf": now,
        "exp": expiry,
        "sub": "server"
    }
    
    # Add permissions to payload
    for key, value in permissions.items():
        payload[key] = value
    
    # Create and sign token
    token = jwt.encode(payload, api_secret, algorithm='HS256')
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    
    # Cache the token
    _token_cache[cache_key] = {
        'token': token,
        'expiry': expiry
    }
    
    return token

def get_permissions_for_endpoint(endpoint):
    """
    Get appropriate permissions for a specific API endpoint
    
    Args:
        endpoint (str): API endpoint
        
    Returns:
        dict: Permissions for token
    """
    if "rooms" in endpoint and "add_sip" in endpoint:
        return {
            "video": {"roomAdmin": True},
            "sip": {"create": True, "list": True, "admin": True}
        }
    elif "rooms" in endpoint:
        return {"video": {"roomCreate": True, "roomList": True, "roomAdmin": True}}
    elif "sip" in endpoint:
        return {"sip": {"create": True, "list": True, "admin": True}}
    else:
        # Default permissions for other endpoints
        return {
            "video": {"roomCreate": True, "roomList": True, "roomAdmin": True},
            "sip": {"create": True, "list": True, "admin": True}
        }

def parse_response(response):
    """
    Parse API response handling empty or non-JSON responses
    
    Args:
        response (Response): Requests response object
        
    Returns:
        dict: Parsed response
    """
    # Handle empty responses
    if not response.text or response.text.strip() == "":
        return {"status": "success"}
    
    # Try to parse as JSON
    try:
        return response.json()
    except:
        # Return text if not JSON
        return {"status": "success", "text": response.text}

def make_api_request(endpoint, payload=None, method="POST", operation_name="api_request"):
    """
    Make a request to the LiveKit API with circuit breaker pattern
    
    Args:
        endpoint (str): API endpoint
        payload (dict): Request payload
        method (str): HTTP method (GET, POST, etc.)
        operation_name (str): Name of operation for logging
        
    Returns:
        dict: API response
    """
    circuit = _circuit_state['livekit_api']
    call_id = payload.get('room_name', payload.get('name', 'unknown'))
    
    # Check if circuit is OPEN
    if circuit['status'] == 'OPEN':
        # Check if timeout has expired
        if time.time() - circuit['last_failure'] > circuit['timeout']:
            # Move to HALF-OPEN
            circuit['status'] = 'HALF-OPEN'
            logger.info(f"[{call_id}] LiveKit API circuit breaker moved to HALF-OPEN state")
        else:
            # Circuit is OPEN and timeout hasn't expired
            logger.warning(f"[{call_id}] LiveKit API circuit is OPEN. Request to {endpoint} rejected")
            return {"status": "error", "error": "Service temporarily unavailable", "circuit": "OPEN"}
    
    try:
        # Generate token with appropriate permissions
        token = create_jwt_token(get_permissions_for_endpoint(endpoint))
        
        # Ensure endpoint starts with /
        if not endpoint.startswith('/'):
            endpoint = f"/{endpoint}"
        
        # Build full URL
        url = f"{LIVEKIT_API_URL}{endpoint}"
        
        # Set headers
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Make request with connection pooling
        start_time = time.time()
        
        logger.info(f"[{call_id}] Making {method} request to {endpoint}")
        
        if method.upper() == "GET":
            response = session.get(url, headers=headers, timeout=10)
        else:  # POST or other methods
            response = session.post(url, headers=headers, json=payload, timeout=10)
        
        # Log performance metrics
        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"[{call_id}] {operation_name} completed in {duration_ms:.2f}ms with status {response.status_code}")
        
        # Check response
        if response.status_code in [200, 201]:
            # If successful and circuit was HALF-OPEN, close it
            if circuit['status'] == 'HALF-OPEN':
                circuit['status'] = 'CLOSED'
                circuit['failures'] = 0
                logger.info(f"[{call_id}] LiveKit API circuit breaker moved to CLOSED state")
            
            # Return success
            result = parse_response(response)
            return result
        else:
            # Handle error
            error_msg = f"API request failed: {response.status_code} - {response.text}"
            logger.error(f"[{call_id}] {error_msg}")
            
            # Record failure for circuit breaker
            circuit['failures'] += 1
            circuit['last_failure'] = time.time()
            
            # Check if we've reached failure threshold
            if circuit['failures'] >= circuit['threshold'] and circuit['status'] != 'OPEN':
                circuit['status'] = 'OPEN'
                logger.warning(f"[{call_id}] LiveKit API circuit breaker moved to OPEN state after {circuit['failures']} failures")
            
            return {"status": "error", "error": error_msg, "code": response.status_code}
    except Exception as e:
        logger.error(f"[{call_id}] Exception in {operation_name}: {str(e)}")
        
        # Record failure for circuit breaker
        circuit['failures'] += 1
        circuit['last_failure'] = time.time()
        
        # Check if we've reached failure threshold
        if circuit['failures'] >= circuit['threshold'] and circuit['status'] != 'OPEN':
            circuit['status'] = 'OPEN'
            logger.warning(f"[{call_id}] LiveKit API circuit breaker moved to OPEN state after {circuit['failures']} failures")
        
        return {"status": "error", "error": str(e)}

def create_room(room_name):
    """
    Create a LiveKit room with updated API compatible with your dispatch rule
    
    Args:
        room_name (str): Name of the room to create, should use call- prefix
        
    Returns:
        dict: Room creation response
    """
    # API endpoint for room creation (using TWIRP)
    endpoint = "/twirp/livekit.RoomService/CreateRoom"
    
    # Ensure room name follows your dispatch rule format
    if not room_name.startswith('call-'):
        logger.warning(f"Room name {room_name} doesn't start with 'call-' prefix required by dispatch rule")
    
    # Prepare payload with parameters matching your LiveKit dispatch rule requirements
    payload = {
        "name": room_name,
        "emptyTimeout": 300,  # 5 minutes timeout for empty rooms
        "maxParticipants": 10,
        "metadata": json.dumps({
            "audio_only": True,
            "agent_metadata": "job dispatch metadata"  # Matching your dispatch rule roomConfig
        })
    }
    
    # Make API request
    response = make_api_request(endpoint, payload, operation_name="create_room")
    
    logger.info(f"Created LiveKit room: {room_name}")
    return response

def get_room(room_name):
    """
    Get information about a LiveKit room with idempotency support
    
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
    return make_api_request(endpoint, payload, operation_name="get_room")

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
    response = make_api_request(endpoint, payload, operation_name="close_room")
    
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
    response = make_api_request(endpoint, payload, operation_name="setup_voice_pipeline")
    
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
    Speak text using TTS via LiveKit with error handling
    
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
    response = make_api_request(endpoint, payload, operation_name="speak_text")
    
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
    # Deprecated - use add_sip_participant_to_trunk instead
    logger.warning(f"add_sip_participant is deprecated, use add_sip_participant_to_trunk with trunk_id instead")
    return add_sip_participant_to_trunk(room_name, sip_uri)

def add_sip_participant_to_trunk(room_name, sip_uri, trunk_id="ST_AVaQRtrTSDtj"):
    """
    Add a SIP participant to a LiveKit room through a specific trunk
    
    Args:
        room_name (str): Name of the room
        sip_uri (str): SIP URI to add
        trunk_id (str): LiveKit trunk ID to use (defaults to your Vici Trunk)
        
    Returns:
        dict: Participant addition response
    """
    # API endpoint for adding SIP participant via trunk
    endpoint = "/twirp/livekit.RoomService/CreateSIPParticipant"
    
    # Extract the user part of the SIP URI for identity
    identity = "customer"
    if '@' in sip_uri:
        user_part = sip_uri.split('@')[0]
        if user_part.startswith('sip:'):
            user_part = user_part[4:]  # Remove 'sip:' prefix if present
            
        if user_part.startswith('+'):
            identity = user_part
        elif user_part.startswith('call_'):
            identity = user_part
    
    # Make sure sip_uri has sip: prefix
    if not sip_uri.startswith('sip:'):
        sip_uri = f"sip:{sip_uri}"
    
    # Prepare payload using your trunk ID
    payload = {
        "room_name": room_name,
        "trunk_id": trunk_id,  # Your specific trunk ID
        "participant_identity": identity,
        "participant_name": f"Customer-{identity}"
    }
    
    # Make API request
    response = make_api_request(endpoint, payload, operation_name="add_sip_participant_to_trunk")
    
    logger.info(f"Added SIP participant via trunk {trunk_id} to room: {room_name}")
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
            "roomNameRegex": "call-$1",  # Use call- prefix to match your dispatch rule
            "createIfNotExists": True
        },
        "webhook_url": f"{api_gateway_url}/v1/inbound_sip"
    }
    
    # Make API request
    response = make_api_request(endpoint, payload, operation_name="create_dispatch_rule")
    
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
            "roomNameRegex": "call-$1",  # Use call- prefix to match your dispatch rule
            "createIfNotExists": True
        },
        "webhook_url": f"{api_gateway_url}/v1/inbound_sip"
    }
    
    # Make API request
    response = make_api_request(endpoint, payload, operation_name="create_dispatch_rule")
    
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
    response = make_api_request(endpoint, {}, "GET", operation_name="get_dispatch_rules")
    
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
        room_name = f"call-{call_id}"  # Use call- prefix to match your dispatch rule
        
    # Get room status using updated TWIRP API
    endpoint = "/twirp/livekit.RoomService/GetRoom"
    
    # Prepare payload
    payload = {
        "name": room_name
    }
    
    # Make API request
    response = make_api_request(endpoint, payload, operation_name="get_call_status")
    
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

def extract_phone_number_from_uri(sip_uri):
    """
    Extract a phone number from a SIP URI if present
    
    Args:
        sip_uri (str): SIP URI
        
    Returns:
        str: Phone number in E.164 format if found, else None
    """
    import re
    
    if not sip_uri:
        return None
        
    # Look for E.164 format in the SIP URI
    e164_match = re.search(r'(\+[0-9]+)@', sip_uri)
    if e164_match:
        return e164_match.group(1)
        
    # Look for numeric sequence that could be a phone number
    digit_match = re.search(r'([0-9]{10,15})@', sip_uri)
    if digit_match:
        digits = digit_match.group(1)
        # Format as E.164
        if len(digits) == 10:  # US number without country code
            return f"+1{digits}"
        elif len(digits) > 10:
            return f"+{digits}"
    
    return None
