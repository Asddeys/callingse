"""
Shared utility functions for AI Voice Sales Bot
"""

import re
import logging

logger = logging.getLogger()

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

def extract_call_id_from_sip_uri(sip_uri):
    """
    Extract call ID from SIP URI
    
    Args:
        sip_uri (str): SIP URI (could be in E.164 format like +14155552671@domain or call_[alphanumeric]@domain)
        
    Returns:
        str: Call ID (either in E.164 format or with call_ prefix)
    """
    # Skip if None or empty
    if not sip_uri:
        return None
        
    try:
        # Extract user part from SIP URI
        generic_pattern = r'^([^@]+)@'
        if sip_uri.startswith('sip:'):
            generic_pattern = r'^sip:([^@]+)@'
            
        match = re.search(generic_pattern, sip_uri)
        
        if not match:
            logger.error(f"No valid call ID pattern found in SIP URI: {sip_uri}")
            return None
            
        call_id = match.group(1)
        
        # Check if it's an E.164 formatted number (starts with +)
        if call_id.startswith('+'):
            logger.info(f"Extracted E.164 phone number from SIP URI: {call_id}")
            return call_id
            
        # Check if it's the call_[alphanumeric] format we previously used
        elif call_id.startswith('call_'):
            logger.info(f"Extracted call ID from SIP URI: {call_id}")
            return call_id
            
        # For any other format, add call_ prefix for backwards compatibility
        else:
            # Ensure it has the call_ prefix
            logger.warning(f"Call ID {call_id} does not have call_ prefix or E.164 format, adding call_ prefix")
            return f"call_{call_id}"
            
    except Exception as e:
        logger.error(f"Error extracting call ID from SIP URI: {str(e)}")
        return None
