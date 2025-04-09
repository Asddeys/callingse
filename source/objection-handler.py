"""
Objection Handler Module

Provides responses for handling various customer objections.
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
        return "I understand"
    
    return f"I understand, {first_name}"

def get_objection_response(objection_type, customer_info):
    """
    Get response for specific objection type
    """
    salutation = get_gender_salutation(customer_info)
    last_name = customer_info.get('last_name', 'there')
    first_name = customer_info.get('first_name', '')
    name_address = f"{first_name}" if first_name else f"Mr./Ms. {last_name}"
    
    # Objection response templates
    objection_responses = {
        # Who are you / who are you with
        'who_are_you': f"{salutation}, {name_address}. We are Consumer Services, and we collaborate with the nation's top-rated debt management companies to provide free advice and information to help you get out of credit card debt in just 12-36 months with no interest. Our services are available across all 50 states. We work with all major creditors like Chase, Citi, Capital One, Bank of America, American Express, Discover and we've been in business for over 20 years.",
        
        # How did you get my number/information
        'how_did_you_get_my_info': f"{salutation}, {name_address}. Our marketing team conducts free rate analysis, surveys, and inquiries across all 50 states. This proactive approach allows us to reach out to individuals who might benefit from our services. We comply with all legal requirements regarding consumer outreach. I'm here to provide you with valuable information that could help you achieve financial freedom sooner than you might think possible.",
        
        # Not interested
        'not_interested': f"{salutation}, {name_address}. I completely understand that you might not be interested because you don't yet know how this could benefit you. We offer a free consultation to provide information on how you can become debt-free within 12 to 36 months without any interest, potentially saving you a significant amount. There's absolutely no obligation - it's just information to help you make educated decisions about your financial future. Many of our clients initially felt the same way until they learned how much they could save.",
        
        # No time
        'no_time': f"{salutation}, {name_address}. I understand you're busy. My call might have caught you at an inconvenient time, and I apologize for that. I promise I won't take much of your time—just a few minutes to explain how we could help reduce your credit card interest rates to zero and potentially save you thousands on your outstanding balance. Most people find that these few minutes are well worth it when they hear how much they could save. Would right now work, or would another time be better?",
        
        # Company information (address, phone number)
        'company_info': f"{name_address}, as we work with multiple debt management companies based on your individual situation and location, I would recommend speaking with one of our debt counselors who can provide specific company information for your state. They'll ensure you're paired with the right company that's licensed to operate in your area and specializes in your particular debt situation. Would you like me to connect you with a counselor who can provide that information?",
        
        # How the program works
        'how_program_works': f"{name_address}, I'd be happy to explain how our program works. We have working relationships with almost every major creditor nationwide. Based on years of experience and established relationships with these credit card companies, we use proven debt mediation techniques to help get these debts paid off for less. The program typically works in three steps: First, we conduct a free analysis of your debt situation. Second, we create a customized plan to reduce your debt with zero interest. Third, you make affordable monthly payments to one place instead of multiple creditors. Would you like to know more about how this might work specifically for your situation?",
        
        # Trust/scam concerns
        'trust_concerns': f"{salutation}, {name_address}. I completely understand your apprehensions. In today's world, it's difficult to trust financial offers, and these aren't the good old days. That's exactly why I'm not asking you to make any decisions or join anything right now. My goal is simply to provide information about this debt savings program and give you enough details to do your own research. We've been in business for over 20 years and have helped thousands of people become debt-free. Would it be okay if I share some information that you can verify on your own time?",
        
        # Credit impact concerns
        'credit_score_concern': f"{name_address}, that's an excellent question. We offer multiple options based on your specific situation. Your current debt-to-income ratio is likely already having a negative impact on your credit score. Our program may have a temporary effect on your credit score at the beginning, but it's often the most aggressive solution for eliminating debt quickly. Once you complete the program in 12-36 months, your debt-to-income ratio dramatically improves, which typically has a positive effect on your overall credit profile. Many clients see their scores begin to recover even during the program as their debt balances decrease. Would you like to hear about the specific options that might work best for your situation?",
        
        # Want everything in writing
        'everything_in_writing': f"{salutation}, {name_address}. I completely understand wanting documentation. Since we offer multiple options tailored to individual situations, I'd like to connect you with one of our counselors who can provide specific, personalized information for your review. They'll explain the best options based on your situation and then send you all the documentation you need to make an informed decision. This allows you to review everything carefully and do your own due diligence. There's absolutely no obligation, and you'll have everything in writing before making any decisions. Would that work for you?",
        
        # Cost/fee concerns
        'cost_concerns': f"{name_address}, that's a great question. There is no upfront fee and no enrollment fee either. Technically, the program costs you nothing out-of-pocket. We get paid out of your savings. For example, if you owe $20,000 and end up paying only $12,000 to settle all your debts, that $12,000 already includes our fee. So nothing comes directly out of your pocket whatsoever. You're only paying a portion of what you would have paid anyway, and our fee is built into those savings. Does that make sense?",
        
        # Do Not Call list
        'do_not_call': f"I sincerely apologize for the inconvenience, {name_address}. I'll make sure to remove your number from our calling list immediately. Thank you for letting me know, and I wish you all the best with your financial journey.",
        
        # Credit impact duration
        'credit_impact_duration': f"{salutation}, {name_address}. That's an important question. The program typically has the least impact on your credit during the early stages. As you progress through the program and start settling debts, your credit profile often begins to improve because your debt-to-income ratio gets better. Once you complete the program, usually within 12-36 months, many clients see significant improvement in their credit scores because they're debt-free with a much healthier financial profile. The temporary effects are often outweighed by the long-term benefits of eliminating high-interest debt completely. Would you like to know more about how this might affect your specific situation?",
        
        # Already in another program
        'already_working_with_someone': f"{salutation}, {name_address}. I understand that exploring multiple options is important. There are various programs available to help with debt, but the one I'm presenting has been among the most effective solutions for over 20 years. Many of our clients actually come to us after trying other programs that didn't deliver the results they needed. What sets us apart is our established relationships with creditors and our ability to negotiate significant reductions in principal balance, not just interest rates. Would you be interested in a free comparison to see if our program could save you more time and money than your current solution?",
        
        # Already on 0% interest
        'already_zero_interest': f"{salutation}, {name_address}. That's great that you've secured a 0% interest rate. However, it's important to understand that most promotional 0% rates on credit cards typically last only 12-18 months. After this period, banks usually begin charging high interest rates again, often 18-29%. Our program offers 0% interest permanently until your debts are completely paid off. Additionally, we often negotiate reductions in your principal balance, potentially saving you 40-50% of what you currently owe. Would you like to know how much you could save beyond just the interest?",
        
        # Need to speak with spouse
        'need_to_speak_with_spouse': f"{salutation}, {name_address}. That makes perfect sense. Financial decisions should absolutely be made together. The good news is that the initial consultation is completely free with no obligation whatsoever. Many of our clients gather the information first and then discuss it with their spouse. This way, you have all the facts to share when you talk about it together. Would it be helpful if I provided you with the details so you can discuss them later, or would you prefer to schedule a time when both of you could participate in the call?",
        
        # Can't afford payment
        'cant_afford_payment': f"{salutation}, {name_address}. That's precisely why our program exists. Many clients come to us because they're struggling with their current payments. We typically reduce monthly payments by 30-50% compared to what you're currently paying. This reduction happens by eliminating interest and often reducing the principal balance as well. Would you be interested in hearing what your new single monthly payment might be? It's likely to be much more affordable than what you're currently managing.",
        
        # Suspicious or skeptical
        'skeptical': f"{salutation}, {name_address}. I completely appreciate your caution. It's smart to be careful about financial decisions. Our company has an A+ rating with the Better Business Bureau and has helped thousands of clients become debt-free over the past 20+ years. We're not asking for any payment information today - just offering a chance to show you your options with no obligation. Many clients felt exactly as you do until they saw the specifics of how much they could save. Would it be alright if I shared some information that you can verify independently?",
        
        # Considering bankruptcy
        'considering_bankruptcy': f"{salutation}, {name_address}. Bankruptcy is certainly an option, but it has long-term consequences for your credit and financial future, typically affecting your credit for 7-10 years and potentially impacting your ability to get loans, housing, or even certain jobs. Our program helps many people avoid bankruptcy while still reducing their debt burden significantly. Before making such an important decision, wouldn't it be worth exploring all your options? I'd be happy to connect you with a counselor who can explain how our program compares to bankruptcy in your specific situation.",
        
        # Need to think about it
        'need_to_think': f"{salutation}, {name_address}. Taking time to think is absolutely reasonable and shows you're careful with financial decisions. The free consultation with our debt counselor doesn't obligate you to anything - it simply gives you more information to consider. Many people find it helpful to have all the facts before making a decision. Our counselors are excellent at answering specific questions about how the program works and how it might benefit your particular situation. Could I schedule you for a quick consultation to get those details, which you can then think about at your own pace?",
        
        # Debt amount too small
        'debt_too_small': f"{salutation}, {name_address}. I understand. While our program often provides the most dramatic benefits for larger debt amounts, even with smaller balances, we can still offer valuable advantages like consolidated payments, zero interest, and potentially reduced balances. The free consultation would clarify exactly what benefits would apply in your specific situation. Many clients are surprised to learn how much they can save even on modest debt amounts. Would you be interested in learning what might be possible in your case?",
        
        # No credit card debt
        'no_credit_card_debt': f"{salutation}, {name_address}. Thank you for letting me know. Our program can also help with other types of unsecured debt like personal loans, medical bills, and collection accounts. Do you have any of these other types of debt that you're working to pay off? If not, I appreciate your time, and please feel free to keep our contact information in case your situation changes in the future.",
        
        # Bad timing
        'bad_timing': f"{salutation}, {name_address}. I completely understand, and I apologize for catching you at an inconvenient time. I'd be happy to call back when it works better for you. Would tomorrow be more convenient, or is there a specific day and time that would work best for a brief 5-minute conversation? This call could save you thousands of dollars, so I want to make sure we connect when you have a moment to discuss it.",
        
        # General objection
        'general': f"{salutation}, {name_address}. Many people have concerns when first hearing about debt relief programs, which is completely understandable. What specific aspect concerns you the most? Is it how the program might affect your credit, how the payments work, or something else? I'd be happy to address any questions you have, as each situation is unique. Our goal is to provide you with clear information so you can make the best decision for your financial future."
    }
    
    # Return appropriate response or default to general
    return objection_responses.get(objection_type, objection_responses['general'])
