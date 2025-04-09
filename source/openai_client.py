"""
OpenAI Client Module

Provides functions for interacting with OpenAI API for conversation
intelligence, including response analysis and intent detection.
"""

import os
import json
import logging
import re
from openai import OpenAI

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize OpenAI client
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Conversation state constants
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
    INTENT_CHECK = 'intent_check'
    OBJECTION_HANDLING = 'objection_handling'
    TRANSFER = 'transfer'
    CLOSING = 'closing'
    ENDED = 'ended'

def extract_numeric_amount(text):
    """
    Extract numeric amount from text
    """
    # Remove commas and dollar signs from text
    text = text.replace('$', '').replace(',', '')
    
    # Look for common patterns like "5000" or "5k" or "five thousand"
    # Dollar amount pattern
    dollar_pattern = r'\b(\d+(?:\.\d+)?)\s*(?:dollars|dollar|k|thousand|grand|g)\b'
    dollar_match = re.search(dollar_pattern, text, re.IGNORECASE)
    
    if dollar_match:
        amount = dollar_match.group(1)
        multiplier = 1
        
        # Check for 'k' or 'thousand' in the match
        if any(suffix in dollar_match.group(0).lower() for suffix in ['k', 'thousand']):
            multiplier = 1000
        
        return float(amount) * multiplier
    
    # Try to extract any number
    numbers = re.findall(r'\b\d+(?:\.\d+)?\b', text)
    if numbers:
        largest_number = max([float(n) for n in numbers])
        return largest_number
    
    return None

def analyze_response(transcript, current_state, customer_info):
    """
    Analyze user response using OpenAI
    """
    try:
        # Prepare context for analysis
        prompt = f"""
        Analyze the following customer response in a debt reduction sales call.
        Current conversation state: {current_state}
        
        Customer response: "{transcript}"
        
        Extract the following information in JSON format:
        
        For all states:
        - first_name: Customer's first name if mentioned
        - last_name: Customer's last name if mentioned
        - objection_detected: true/false if customer has an objection
        - objection: type of objection if detected. Use one of the following categories:
          * not_interested - Customer says they are not interested
          * no_time - Customer says they don't have time to talk
          * who_are_you - Customer asks who we are or about the company
          * how_did_you_get_my_info - Customer asks how we got their information or number
          * company_info - Customer asks for company address or phone number
          * how_program_works - Customer asks how the program works
          * trust_concerns - Customer expresses concerns about scams or trust
          * credit_score_concern - Customer worried about credit score impact
          * credit_impact_duration - Customer asks how long credit will be affected
          * everything_in_writing - Customer wants information in writing
          * cost_concerns - Customer asks about program costs or fees
          * do_not_call - Customer mentions being on do not call list
          * already_working_with_someone - Customer says they're in another program
          * already_zero_interest - Customer says they already have 0% interest
          * need_to_speak_with_spouse - Customer needs to consult spouse
          * cant_afford_payment - Customer concerned about affording payments
          * skeptical - Customer expresses general skepticism
          * considering_bankruptcy - Customer mentions bankruptcy
          * need_to_think - Customer needs time to think
          * debt_too_small - Customer says debt amount is small
          * no_credit_card_debt - Customer says they have no credit card debt
          * bad_timing - Customer says it's a bad time to talk
          * general - Any other objection
        
        For qualification or bill_responsibility state:
        - handles_bills: true if customer confirms they handle the bills, false if they don't
        - bill_handler_name: Name of person who handles bills if not the customer
        - call_transfer_accepted: true if customer agrees to transfer the call to bill handler, false if not
        - callback_time: If customer suggests calling back at a different time for bill handler, include time/date mentioned
        
        For debt_amount state:
        - debt_amount: The total debt amount mentioned (number only, no currency symbols)
        
        For card_count state:
        - card_count: Number of credit cards mentioned
        
        For payment_status state:
        - payment_status: "current" if on-time with payments, "behind" if late or missing payments
        
        For employment state:
        - employment_status: "employed", "self_employed", "retired", or "unemployed"
        
        For monthly_payment state:
        - monthly_payment: The monthly payment amount mentioned (number only)
        
        For intent_check state:
        - intent_confirmed: true if customer confirms interest, false if declines
        
        For objection_handling state:
        - objection_resolved: true if objection appears resolved, false if still an issue
        """
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",  # the newest OpenAI model is "gpt-4o" which was released May 13, 2024
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        analysis = json.loads(response.choices[0].message.content)
        logger.info(f"Analysis result: {json.dumps(analysis)}")
        
        return analysis
    
    except Exception as e:
        logger.error(f"Error analyzing response: {str(e)}")
        # Return minimal analysis with defaults
        return {
            "first_name": "",
            "last_name": "",
            "objection_detected": False,
            "objection": "general"
        }

def get_next_bot_response(transcript_history, current_state, customer_info, script_template):
    """
    Generate next bot response using OpenAI
    """
    try:
        # Format transcript history
        formatted_history = ""
        for entry in transcript_history:
            speaker = entry.get('speaker', '')
            text = entry.get('text', '')
            formatted_history += f"{speaker.upper()}: {text}\n"
        
        prompt = f"""
        You are an AI voice sales bot for a debt reduction company. Your goal is to qualify potential customers
        and transfer qualified leads to human agents. Be professional, empathetic, and persuasive.
        
        Current conversation state: {current_state}
        Script template: "{script_template}"
        
        Conversation history:
        {formatted_history}
        
        Generate the next response for the bot. Follow the script template but adapt naturally to the conversation.
        Keep your response concise (max 3 sentences), conversational, and avoid sounding scripted.
        Be empathetic but professional, and don't be overly apologetic. Sound like a helpful human representative.
        """
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",  # the newest OpenAI model is "gpt-4o" which was released May 13, 2024
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        
        bot_response = response.choices[0].message.content.strip()
        logger.info(f"Generated bot response: {bot_response}")
        
        return bot_response
    
    except Exception as e:
        logger.error(f"Error generating bot response: {str(e)}")
        # Return script template as fallback
        return script_template
