import os
import glob
import imaplib
import email
from email.header import decode_header
import time
import sqlite3 # NEW: Import sqlite3
from dotenv import load_dotenv
from agents import Agent, Runner, function_tool
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
import asyncio

# --- 1. SETUP AND CREDENTIALS ---

load_dotenv()
print("INFO: Loading credentials for Reply Agent...")

# Database file for checking outreach recipients
DB_FILE = "outreach_log.db" # UPDATED: Database file name

# Credentials
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_SENDER = os.getenv("SENDGRID_SENDER")
IMAP_SERVER = os.getenv("IMAP_SERVER")
IMAP_EMAIL = os.getenv("IMAP_EMAIL")
IMAP_APP_PASSWORD = os.getenv("IMAP_APP_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME")
IMAP_REPLY_TO_EMAIL = os.getenv("IMAP_REPLY_TO_EMAIL")

if not all([SENDGRID_API_KEY, SENDGRID_SENDER, IMAP_SERVER, IMAP_EMAIL, IMAP_APP_PASSWORD, OPENAI_API_KEY, OPENAI_MODEL_NAME]):
    print("ERROR: One or more environment variables for SendGrid, IMAP, or OpenAI are not set.")
    exit()

sg_client = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
print("INFO: Clients configured.")

def load_all_company_info(directory="company"):
    # This remains useful for the RAG tool
    all_content = ""
    files = glob.glob(os.path.join(directory, "*.md"))
    for file_path in files:
        with open(file_path, 'r') as f:
            all_content += f.read() + "\n\n---\n\n"
    return all_content

ALL_COMPANY_INFO = load_all_company_info()
if not ALL_COMPANY_INFO:
    print("WARNING: No company information found for RAG tool.")

# --- 2. TOOLS (No changes to tool logic) ---

@function_tool
def query_company_knowledge_base(query: str) -> str:
    """
    Searches the company's knowledge base to answer specific questions.
    """
    print(f"INFO: RAG Tool called with query: '{query}'")
    return ALL_COMPANY_INFO

@function_tool
def send_email(to_email: str, subject: str, body: str) -> str:
    """
    Sends an email reply to a specified recipient.
    """
    print(f"INFO: Email Tool called: Sending reply to {to_email}")
    try:
        from_email_obj = Email(SENDGRID_SENDER)
        to_email_obj = To(to_email)
        content = Content("text/plain", body)
        reply_to_email_obj = ReplyTo(IMAP_REPLY_TO_EMAIL)
        mail = Mail(from_email_obj, to_email_obj, subject, content)
        mail.reply_to = reply_to_email_obj
        response = sg_client.client.mail.send.post(request_body=mail.get())
        if response.status_code >= 200 and response.status_code < 300:
            return "Email reply sent successfully."
        else:
            return f"Failed to send email. Status: {response.status_code}"
    except Exception as e:
        return f"An exception occurred: {e}"

# --- 3. AGENT DEFINITION (No changes here) ---

alex_reply_instructions = f"""
You are "Alex," a professional and helpful Business Development Representative for Sentinel AI.
Your goal is to engage in a conversation with a potential customer who has replied to one of your emails.
Read the entire email carefully to understand the context and the user's latest message or question.
Here is comprehensive information about your company, Sentinel AI:
---
{ALL_COMPANY_INFO}
---
RULES:
1.  Read the user's email carefully to understand their question or comment.
2.  If they ask a specific question about Sentinel AI, use the `query_company_knowledge_base` tool to get the information.
3.  Use any quoted content within the email and the information from the RAG tool (if used) to formulate a helpful, context-aware reply.
4.  Ensure your reply's subject line is appropriate (e.g., prepending "Re: " to the original subject).
5.  Once you have the final response crafted, you MUST use the `send_email` tool to send your reply.
"""

alex_reply_agent = Agent(
    name="Alex (Reply)",
    instructions=alex_reply_instructions,
    tools=[query_company_knowledge_base, send_email],
    model=OPENAI_MODEL_NAME,
)

# --- 4. UPDATED LIVE EMAIL CHECKING & DB-POWERED HANDLING ---

def check_for_new_replies():
    new_emails = []
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(IMAP_EMAIL, IMAP_APP_PASSWORD)
        mail.select("inbox")
        status, messages = mail.search(None, '(UNSEEN)')
        if status != 'OK': return []
        for num in messages[0].split():
            status, data = mail.fetch(num, '(RFC822)')
            if status != 'OK': continue
            msg = email.message_from_bytes(data[0][1])
            subject, encoding = decode_header(msg["Subject"])[0]
            if isinstance(subject, bytes): subject = subject.decode(encoding or "utf-8")
            from_ = msg.get("From")
            from_email_address = email.utils.parseaddr(from_)[1]
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain' and 'attachment' not in str(part.get('Content-Disposition')):
                        body = part.get_payload(decode=True).decode()
                        break
            else:
                if msg.get_content_type() == "text/plain": body = msg.get_payload(decode=True).decode()
            new_emails.append({"from": from_email_address, "subject": subject, "body": body.strip()})
            mail.store(num, '+FLAGS', '\Seen')
        mail.logout()
    except Exception as e: print(f"ERROR: Failed to check emails: {e}")
    return new_emails

async def handle_inbound_email(customer_email: str, subject: str, body: str):
    """
    Processes an inbound email, first checking if the sender is in the outreach log.
    """
    print("\n" + "="*50)
    print(f"INFO: New email received from: {customer_email}")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # --- NEW: Check if this is a reply from a known conversation ---
    cursor.execute("SELECT id FROM outreach_recipients WHERE recipient_email = ?", (customer_email,))
    result = cursor.fetchone()
    conn.close() # We can close the connection right after the check

    if not result:
        print(f"INFO: Ignoring email from {customer_email} as they are not in the outreach log.")
        return # Stop processing this email

    # --- If we get here, the email is from a known recipient ---
    print(f"INFO: Sender {customer_email} found in outreach log. Triggering Alex (Reply Agent)...")

    agent_prompt = f"""
A customer with email '{customer_email}' has replied to you.
Their subject line is: '{subject}'.
The full content of their message, which may include previous conversation, is:
---
{body}
---
Please process this email and send a helpful, conversational reply.
"""
    await Runner.run(alex_reply_agent, input=agent_prompt)
    print("INFO: Agent has finished processing the reply.")


# --- 5. MAIN AGENT LOOP (No changes here) ---

def main():
    print("INFO: Starting Sentinel AI Reply Agent (with DB filter)...")
    print("INFO: Press Ctrl+C to stop the agent.")
    
    while True:
        try:
            new_emails = check_for_new_replies()
            if new_emails:
                print(f"INFO: Found {len(new_emails)} new email(s).")
                for email_data in new_emails:
                    asyncio.run(handle_inbound_email(
                        customer_email=email_data['from'],
                        subject=email_data['subject'],
                        body=email_data['body']
                    ))
            else:
                print("INFO: No new replies found. Waiting...")
            time.sleep(60)
        except KeyboardInterrupt:
            print("\nINFO: Agent stopped by user. Goodbye.")
            break
        except Exception as e:
            print(f"ERROR: An unexpected error occurred in the main loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()