import os
import glob
import sqlite3 # NEW: Import sqlite3
from datetime import datetime # NEW: Import datetime for timestamps
from dotenv import load_dotenv
from agents import Agent, Runner, function_tool
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content, ReplyTo
import asyncio

# --- 1. SETUP AND CREDENTIALS ---

load_dotenv()
print("INFO: Loading credentials for Outreach Agent...")

# Database file for logging outreach recipients
DB_FILE = "outreach_log.db" # UPDATED: Database file name

# SendGrid Credentials
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_SENDER = os.getenv("SENDGRID_SENDER") # Must be a verified sender in SendGrid
IMAP_REPLY_TO_EMAIL = os.getenv("IMAP_REPLY_TO_EMAIL") # The email address replies should go to

# OpenAI Credentials
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME")

if not all([SENDGRID_API_KEY, SENDGRID_SENDER, IMAP_REPLY_TO_EMAIL, OPENAI_API_KEY, OPENAI_MODEL_NAME]):
    print("ERROR: One or more environment variables are not set.")
    exit()

# Initialize SendGrid client
sg_client = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
print("INFO: SendGrid client configured for sending.")

# Helper to load all company info for the agent's context
def load_all_company_info(directory="company"):
    all_content = ""
    files = glob.glob(os.path.join(directory, "*.md"))
    for file_path in files:
        with open(file_path, 'r') as f:
            all_content += f.read() + "\n\n---\n\n" # Separator for readability
    return all_content

ALL_COMPANY_INFO = load_all_company_info()
if not ALL_COMPANY_INFO:
    print("ERROR: No company information found in the 'company/' directory. Agent will have limited context.")

# --- 2. UPDATED TOOL DEFINITION WITH DATABASE LOGIC ---

@function_tool
def send_email(to_email: str, subject: str, body: str) -> str:
    """
    Sends an email and records the recipient in the outreach log.
    This is the final action to send an email. The 'Reply-To' header is set
    automatically to direct replies to the dedicated IMAP inbox.
    """
    print(f"INFO: Email Tool called: Preparing to send email to {to_email}")

    # --- Step 1: Send the email via SendGrid ---
    try:
        from_email_obj = Email(SENDGRID_SENDER)
        to_email_obj = To(to_email)
        content = Content("text/plain", body)
        reply_to_email_obj = ReplyTo(IMAP_REPLY_TO_EMAIL)

        mail = Mail(from_email_obj, to_email_obj, subject, content)
        mail.reply_to = reply_to_email_obj
        
        response = sg_client.client.mail.send.post(request_body=mail.get())
        
        if response.status_code >= 200 and response.status_code < 300:
            print(f"INFO: Email sent successfully to {to_email}.")
            
            # --- Step 2: Log the recipient in the database ---
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                # Use INSERT OR IGNORE to add the recipient if not already present
                cursor.execute(
                    "INSERT OR IGNORE INTO outreach_recipients (recipient_email, sent_timestamp) VALUES (?, ?)",
                    (to_email, datetime.now())
                )
                conn.commit()
                conn.close()
                print(f"INFO: Recipient {to_email} logged in outreach_log.db.")
            except Exception as e:
                print(f"ERROR: Database logging failed for {to_email}: {e}")
                # We don't return an error here, as the email was successfully sent.

            return "Email sent successfully and recipient logged."
        else:
            error_message = f"Failed to send email. Status: {response.status_code}. Body: {response.body}"
            print(f"ERROR: {error_message}")
            return error_message

    except Exception as e:
        error_message = f"An exception occurred while sending email to {to_email}: {e}"
        print(f"ERROR: {error_message}")
        return error_message

# --- 3. AGENT DEFINITION (No changes here) ---

alex_outreach_instructions = f"""

You are "Alex," a professional Business Development Representative for Sentinel AI.
Your personality is: knowledgeable, professional, persuasive, and concise.

Your primary goal is to write compelling, first-contact (cold) emails to introduce Sentinel AI to potential clients.
Focus on solving a pain point and clearly stating Sentinel AI's value.

Here is comprehensive information about your company, Sentinel AI:
---
{ALL_COMPANY_INFO}
---

RULES FOR EMAIL COMPOSITION:
- Craft an engaging and professional subject line.
- Introduce Sentinel AI and its core offerings (ThreatPredict, AutoResponse, ComplianceGuard).
- Highlight how Sentinel AI addresses common cybersecurity challenges (e.g., reactive defense, compliance burden, slow incident response).
- End with a clear, low-friction call to action, typically suggesting a brief introductory call or demo.
- Do NOT explicitly mention the 'Reply-To' address or any internal email routing.
- You MUST use the `send_email` tool as the final step to deliver the composed email.
"""

alex_outreach_agent = Agent(
    name="Alex (Outreach)",
    instructions=alex_outreach_instructions,
    tools=[send_email],
    model=OPENAI_MODEL_NAME,
)

# --- 4. MAIN OUTREACH LOGIC (No changes here) ---

async def main():
    print("INFO: Starting Sentinel AI Outreach Campaign with Recipient Logging...")

    prospect_list = [
        {"name": "Client One", "email": "mtsulehri@gmail.com", "company": "Global Corp"},
        {"name": "Client Two", "email": "mhtsulehri@gmail.com", "company": "Future Tech Solutions"},
        {"name": "Your Name", "email": "muhammad.76955@gmail.com", "company": "Testing Solutions"},
    ]

    for prospect in prospect_list:
        print(f"\n--- Processing prospect: {prospect['name']} ---")
        outreach_prompt = f"Compose a cold outreach email to {prospect['name']} who works at {prospect['company']} to email {prospect['email']}."
        await Runner.run(alex_outreach_agent, outreach_prompt)
        print(f"INFO: Outreach process completed for {prospect['name']} of email {prospect['email']}.")

    print("\nINFO: Outreach campaign finished.")

if __name__ == "__main__":
    asyncio.run(main())