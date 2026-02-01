import os
import glob
from dotenv import load_dotenv
from agents import Agent, Runner, function_tool
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
import asyncio

# --- 1. SETUP AND CREDENTIALS ---

load_dotenv()
print("INFO: Loading credentials...")

# SendGrid Credentials
# - SENDGRID_API_KEY: Your API key from SendGrid.
# - SENDGRID_SENDER: A verified sender email address in your SendGrid account.
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_SENDER = os.getenv("SENDGRID_SENDER")

# OpenAI Credentials
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME")

if not all([SENDGRID_API_KEY, SENDGRID_SENDER, OPENAI_API_KEY, OPENAI_MODEL_NAME]):
    # Note: We are now using SendGrid, so EMAIL_APP_PASSWORD is no longer needed.
    print("ERROR: One or more environment variables (SENDGRID_API_KEY, SENDGRID_SENDER, OPENAI_API_KEY, OPENAI_MODEL_NAME) are not set.")
    exit()

# Initialize SendGrid client
sg_client = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
print("INFO: SendGrid and OpenAI clients configured.")


# --- 2. TOOL DEFINITIONS ---

@function_tool
def query_company_knowledge_base(query: str) -> str:
    """
    Searches the company's knowledge base to answer specific questions about
    the company, its history, founders, products, services, or employees.
    Use this tool to find information before answering a user's question.
    """
    print(f"INFO: RAG Tool called with query: '{query}'")
    
    # 1. Find all knowledge base files
    path = "company/*.md"
    files = glob.glob(path)
    
    if not files:
        return "Error: No knowledge base files found in the company/ directory."

    # 2. Read all content
    all_content = ""
    for file_path in files:
        with open(file_path, 'r') as f:
            all_content += f.read() + "\n\n"

    # 3. Simple keyword search (a more advanced version would use vector embeddings)
    # We will return the whole content for the LLM to summarize, which is effective for this amount of text.
    # This simulates finding the most relevant documents.
    # For a real RAG, you'd return specific chunks.
    print("INFO: Found knowledge base content. Returning to agent for processing.")
    return all_content


@function_tool
def send_email(to_email: str, subject: str, body: str) -> str:
    """
    Sends an email to a specified recipient.
    This should be the final step when you have a complete response for the user.
    """
    print(f"INFO: Email Tool called: Sending email to {to_email}")
    try:
        from_email = Email(SENDGRID_SENDER)
        to_email_obj = To(to_email)
        content = Content("text/plain", body)
        mail = Mail(from_email, to_email_obj, subject, content)
        
        response = sg_client.client.mail.send.post(request_body=mail.get())
        
        if response.status_code >= 200 and response.status_code < 300:
            print(f"INFO: Email sent successfully with status code {response.status_code}.")
            return "Email sent successfully."
        else:
            print(f"ERROR: Failed to send email. Status: {response.status_code}. Body: {response.body}")
            return f"Failed to send email. Status code: {response.status_code}"

    except Exception as e:
        print(f"ERROR: An exception occurred while sending email: {e}")
        return f"An exception occurred: {e}"


# --- 3. AGENT DEFINITION ---

# Instructions for our main agent, "Alex".
alex_instructions = """
You are "Alex," a professional Business Development Representative for Sentinel AI.
Your personality is: knowledgeable, professional, and helpful.

Your primary goal is to engage with potential customers who reply to your emails.

Follow these steps:
1.  Read the user's email carefully to understand their question or comment.
2.  If they ask a specific question about Sentinel AI (e.g., "who are the founders?", "tell me about your products"), you MUST use the `query_company_knowledge_base` tool to get the latest information.
3.  Use the information returned by the tool to formulate a complete, well-written, and conversational response. Do not just output the raw information from the tool.
4.  Once you have the final response crafted, you MUST use the `send_email` tool to send your reply.
"""

# Create the agent instance
alex_agent = Agent(
    name="Alex",
    instructions=alex_instructions,
    tools=[query_company_knowledge_base, send_email],
    model=OPENAI_MODEL_NAME,
)

# --- 4. INBOUND EMAIL HANDLER ---

async def handle_inbound_email(customer_email: str, subject: str, body: str):
    """
    This function simulates the action of a webhook. It takes the data
    of a received email and triggers the agent to process and reply to it.
    """
    print("\n" + "="*50)
    print(f"INFO: New email received from {customer_email}")
    print(f"INFO: Subject: {subject}")
    print(f"INFO: Body: \"{body}\"")
    print("="*50 + "\n")

    # The prompt for the agent combines the instruction with the user's email.
    agent_prompt = f"""
    A customer with email '{customer_email}' has replied to your email thread.
    Their subject line is: '{subject}'.
    Their message is:
    ---
    {body}
    ---
    Your task is to process this email, find the necessary information, and send a reply.
    """
    
    # Run the agent
    await Runner.run(alex_agent, agent_prompt)


# --- 5. SIMULATION ---

async def main():
    """
    Main function to run the simulation.
    """
    print("INFO: Starting agent simulation...")

    # --- SIMULATION 1: A customer asks about the founders ---
    await handle_inbound_email(
        customer_email="mhtsulehri@gmail.com",
        subject="Re: Your Cybersecurity Solutions",
        body="This is interesting. Can you tell me who the founders of Sentinel AI are?"
    )

    # --- SIMULATION 2: A customer asks about a specific product ---
    await handle_inbound_email(
        customer_email="mtsulehri@gmail.com",
        subject="Question about your platform",
        body="What can you tell me about your AutoResponse platform?"
    )

if __name__ == "__main__":
    # This runs our main async function.
    asyncio.run(main())
