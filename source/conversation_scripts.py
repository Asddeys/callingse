"""
Conversation Scripts Module

Provides script templates for different stages of the conversation.
"""

import json
import logging
import re

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_gender_salutation(customer_info):
    """
    Return an appropriate gender-based salutation based on customer name
    """
    first_name = customer_info.get('first_name', '')
    
    if not first_name:
        return "Hello there"
    
    return f"Hello, {first_name}"

def get_greeting(customer_info):
    """
    Generate greeting script
    """
    script = "Good Day, My name is Rachel, and I'm calling from Consumer Services. The reason I'm calling you today is that, according to our records, it looks like you still have more than ten thousand dollars in credit card debt, and you have been making your monthly payments on time, right?"
    
    return script

def get_qualification_intro(customer_info):
    """
    Generate qualification intro script
    """
    script = "Based on your track records of making payments and your situation, your total debts can be reduced by 20-40% and you can be on a zero-interest monthly payment plan. For example, if you owe $20000, you will save $8000 which you don't have to pay back ever, that's your savings. You will end up paying only half of what you owe, that's it. Not only this, your monthly payments can be reduced by almost half as well. And the best part is that you will be on a no interest payment plan so you can get out of these debts in no time rather paying them for years and years."
    
    return script

def get_bill_responsibility_question(customer_info):
    """
    Generate bill responsibility question script
    """
    script = "So to give you more information about YOUR debt savings plan, I am sure you are THE ONE who handles the bills and takes care of these CREDIT CARDS? Right!"
    
    return script

def get_debt_amount_question(customer_info):
    """
    Generate debt amount question script
    """
    script = "We have multiple options for 12 to 36 months wherein monthly payments can be very low. So to let you know more about your lower monthly payment options, how much in total do you owe on all these credit cards combined together? Just a ballpark number, like $15 Thousand, 20, 25 Thousand or more?"
    
    return script

def get_card_count_question(customer_info):
    """
    Generate card count question script
    """
    # Extract debt amount if we have it
    debt_info = json.loads(customer_info.get('debt_info', '{}'))
    debt_amount = debt_info.get('total_amount', '')
    
    if debt_amount:
        script = f"And that's on how many cards you owe this {debt_amount} balance? Just a ball park number like 3-4 5 or more"
    else:
        script = "And that's on how many cards you owe this balance? Just a ball park number like 3-4 5 or more"
    
    return script

def get_payment_status_question(customer_info):
    """
    Generate payment status question script
    """
    script = "Are you current on your monthly payments or by any chance are you behind?"
    
    return script

def get_employment_question(customer_info):
    """
    Generate employment question script
    """
    script = "Are you currently Employed/Self Employed or retired?"
    
    return script

def get_monthly_payment_question(customer_info):
    """
    Generate monthly payment question script
    """
    # Extract debt amount if we have it
    debt_info = json.loads(customer_info.get('debt_info', '{}'))
    debt_amount = debt_info.get('total_amount', '')
    
    if debt_amount:
        script = f"How much are you paying monthly on these credit cards with the {debt_amount} balance?"
    else:
        script = "How much are you paying monthly on these credit cards?"
    
    return script

def get_qualification_complete_message(customer_info):
    """
    Generate message to be played after all qualification questions are answered
    """
    script = "OK, all right, thanks for your answers. This is the only information needed. Now it's our turn to get you more information on lower monthly payment plans and savings. Please hold for a moment while I gather the information needed to assist you. Once again, it's a free consultation with no obligation. I will be right back with the details."
    
    return script

def get_intent_check(customer_info):
    """
    Generate intent check script
    """
    first_name = customer_info.get('first_name', '')
    
    # Extract debt amount if we have it
    debt_info = customer_info.get('debt_info', {})
    # Handle string/JSON format if that's what we got
    if isinstance(debt_info, str):
        debt_info = json.loads(debt_info)
    
    debt_amount = debt_info.get('total_amount', '')
    card_count = debt_info.get('card_count', '')
    monthly_payment = debt_info.get('monthly_payment', '')
    
    if first_name and debt_amount and monthly_payment:
        script = f"{first_name}, based on your {debt_amount} balance across {card_count} cards and monthly payment of {monthly_payment}, you may qualify for our program. Would you be interested in options to reduce your debt and potentially save thousands in interest by consolidating your payments?"
    elif debt_amount:
        script = f"Based on your {debt_amount} balance, you may qualify for our program. Would you be interested in options to reduce your debt and potentially save thousands in interest?"
    else:
        script = "Based on what you've shared, you may qualify for our program. Would you be interested in options to reduce your debt and potentially save thousands in interest?"
    
    return script

def get_transfer_message(customer_info):
    """
    Generate transfer message script
    """
    first_name = customer_info.get('first_name', '')
    
    if first_name:
        script = f"Great! I'll connect you with a debt counselor who can provide a free consultation, {first_name}. They'll explain all your options and potential savings. Please hold while I transfer you."
    else:
        script = "Great! I'll connect you with a debt counselor who can provide a free consultation. They'll explain all your options and potential savings. Please hold while I transfer you."
    
    return script

def get_closing_message(customer_info):
    """
    Generate closing message script for non-qualified customers
    """
    first_name = customer_info.get('first_name', '')
    
    if first_name:
        script = f"Thank you for your time, {first_name}. Feel free to reach out if your situation changes, and we'll be happy to help you then."
    else:
        script = "Thank you for your time. Feel free to reach out if your situation changes, and we'll be happy to help you then."
    
    return script
