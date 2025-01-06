import os
import logging
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from openai import ChatCompletion
from dotenv import load_dotenv
import ast
import json

# Load environment variables
load_dotenv()

# Initialize Slack App
app = App(token=os.getenv("SLACK_BOT_TOKEN"))

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tokens and API Keys
SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Step 1: OpenAI Query Refinement
def refine_query(user_query, bot_user_id):
    """
    Refine the user's query for Slack search.
    - Strips the bot at-mention before processing.
    - Passes the cleaned query to OpenAI for refinement.
    """
    try:
        # Remove the bot mention (e.g., "<@U12345>")
        if bot_user_id in user_query:
            user_query = user_query.replace(f"<@{bot_user_id}>", "").strip()

        # Send to OpenAI for refinement
        response = ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an intelligent assistant. Simplify and optimize search queries for Slack."},
                {"role": "user", "content": f"Turn this message into a Slack Search query: {user_query}. Only return the query itself. Do not include any commands or filters for Slack to execute. "}
            ],
            api_key=OPENAI_API_KEY
        )

        refined_query = response["choices"][0]["message"]["content"].strip()
        logger.info(f"Refined Query: {refined_query}")

        # Ensure no unnecessary restrictions are added
        if "from:@" in refined_query or not refined_query:
            logger.warning("Refined query was overly restrictive. Falling back to original.")
            return user_query

        return refined_query
    except Exception as e:
        logger.error(f"Error refining query: {e}")
        return user_query  # Fallback to original query

# Step 2: Slack Search Functionality
def search_slack(refined_query, team_id):
    """
    Search Slack using the refined query.
    """
    try:
        response = app.client.search_all(
            token=SLACK_USER_TOKEN,  # Use user token
            query=refined_query,
            count=10,
            team_id=team_id
        )
        logger.info(f"Slack search results: {response}")
        return response.get("messages", {}).get("matches", [])
    except Exception as e:
        logger.error(f"Slack search error: {e}")
        return []

# Step 3: Placeholder for Public API (Future Integration)
def fetch_public_data(refined_query):
    """
    Fetch additional data from a public API (e.g., Google Search).
    Currently a placeholder for future integration.
    """
    # Mock public data for future use
    logger.info("Public API integration is currently disabled.")
    return []  # Empty for now

# Step 4: Combine and Format Results
def format_combined_results(slack_results):
    """
    Summarize and format Slack search results into a user-friendly response.
    """

#    public_data = public_data or []

    # Step 1: Summarize Slack Results using OpenAI
    if slack_results:
        try:
            # Preprocess Slack results into plain text for OpenAI
            plain_text_results = "\n".join(
                [
                    f"- Channel: #{msg['channel']['name']}, User: <@{msg.get('user', 'unknown')}>, Message: {msg.get('text', '').strip()}"
                    for msg in slack_results[:5]
                ]
            )

            # Prepare the messages for OpenAI
            openai_messages = [
                {"role": "system", "content": "You are an assistant that summarizes messages."},
                {"role": "user", "content": f"Summarize these messages in 2-3 sentences:\n{plain_text_results}"}
            ]

            # Call OpenAI for summarization
            response = ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=openai_messages,
                api_key=OPENAI_API_KEY,
            )
            summary = response["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logging.error(f"Error summarizing with OpenAI: {e}")
            summary = "I found some relevant messages in Slack, but I couldn't generate a summary right now. Here are the details:"
    else:
        summary = "I couldn't find any relevant messages in Slack."

    # Step 2: Format Slack Results
    detailed_results = []
    if slack_results:
        for msg in slack_results[:5]:  # Limit to top 5 results
            channel_name = msg["channel"]["name"]
            user_id = msg.get("user", "unknown")
            text_preview = msg.get("text", "").replace("\n", " ").strip()
            permalink = msg.get("permalink", "#")
            detailed_results.append(
                f"- In *#{channel_name}*, <@{user_id}> posted:\n> {text_preview}\n[View Message]({permalink})"
            )
    else:
        detailed_results.append("_No relevant messages found in Slack._")

    # Step 3: Combine Summary and Results
    response = f"{summary}\n\n" + "\n".join(detailed_results)
    return response

def summarize_thread(message_context):
    thread_summary=ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an intelligent Slack assistant."},
                 {
                    "role": "user",
                    "content": (
                        "When referring to a user, format the ID as a Slack Bolt user tag, <@userID>"
                        f"Summarize the following messages:\n{message_context}."
                                
                                ),
                },
            ],
            api_key=OPENAI_API_KEY
        )
    refined_summary=thread_summary["choices"][0]["message"]["content"].strip()
    return refined_summary

# Common Processing Function-- parse the message and prepare for next steps. 
def process_event(event, say):
    thread_ts = event.get("ts")  #Use thread_ts if available, otherwise use message ts
   
    # Determine message subtype
    message_subtype=event.get("subtype")
    logger.info(f"Message subtype: {message_subtype}")



    

    # Proceed if it's not a message_deleted event
    if message_subtype != "message_deleted" and message_subtype != "message_changed":
        try:
            # pull out relevant message details from the payload
            user_message = event.get("text", "").strip()
            # message_ts = event.get("ts")
            bot_user_id = app.client.auth_test()["user_id"]  
            team_id = event.get("team")
            channel_id=event.get("channel")

            #get message context if possible
            message_context = ""
            if "thread_ts" in event:
                # Fetch all messages in the thread
                replies_response = app.client.conversations_replies(
                    channel=channel_id, ts=event["thread_ts"]
                )
                thread_messages = replies_response.get("messages", [])

                # Traverse the thread messages to build the context
                message_context = "\n".join(
                    [
                        f"<@{msg.get('user', 'unknown')}>: {msg.get('text', '').strip()}"
                         for msg in thread_messages[:10] #added [:10] to only take the first 10 messages as context
                        
                    ]
                )
            logger.info(f"Message context {message_context}")

            # Get the user info
            user_id = event.get("user")
            logger.info(user_id)
            if user_id:
                user_info = app.client.users_info(user=user_id)
                user_name = user_info.get("user", {}).get("real_name")  # Default to "unknown" if name not found
            else:
                user_name = "unknown"
            logger.info(f"User Name: {user_name}")
    
            # determine intent
            response = ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an intelligent assistant."},
                    {
                        "role": "user",
                        "content": (
                            f"Here are some messages to use as background: {message_context}. "
                            f"Use those messages context to determine the intent of this message from {user_name}: {user_message}. "
                            f"Only respond with one of the following options: Slack Search, Other, Summarize Thread. Do not include any additional context or commentary in the response."
                        ),
                    },
                ],
                api_key=OPENAI_API_KEY,
            )

            refined_intent = response["choices"][0]["message"]["content"].strip()
            logger.info(f"Refined intent: {refined_intent}")

            # Handle intents
            if refined_intent == "Slack Search":
                refined_query = refine_query(user_message, bot_user_id)
                slack_results = search_slack(refined_query, team_id)
                response = format_combined_results(slack_results)
                say(text=response, thread_ts=thread_ts)
            elif refined_intent == "Summarize Thread":
                response=summarize_thread(message_context)
                say(text=response, thread_ts=thread_ts)
            else:
                say(f"{user_name}: Other - I don't have that skill yet. Tell Naseer to get on it!", thread_ts=thread_ts)

        except Exception as e:
            logger.error(f"Error processing event: {e}")
            say(text="I'm sorry, I couldn't process your request.", thread_ts=thread_ts)

# Event Listener: Handle Mentions
@app.event("app_mention")
def handle_mention(event, say):
    process_event(event,say)

# Handle agent DMs
@app.event("message")
def handle_message_im(event, say):
    process_event(event, say)

# @app.event("assistant_thread_started")
# def handle_assistant_thread_started(event,say):
#     process_event(event,say)

# Start the App
if __name__ == "__main__":
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    handler.start()