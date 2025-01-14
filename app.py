import os
import logging
import json
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from openai import ChatCompletion
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

# Initialize Slack App
app = App(token=os.getenv("SLACK_BOT_TOKEN"))

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
event_count=0
logger.info(f"event_count:{event_count}")

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
            model="gpt-3.5-turbo-16k",
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
            team_id=team_id
        )
        responses_count=response.get("messages", {}).get("total",0)
        logger.info(f"Number of results: {responses_count}")
        #logger.info(f"Slack search results: {response}")
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
    plain_text_results = ""
#   public_data = public_data or []

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

        except Exception as e:
            logging.error(f"Error summarizing with OpenAI: {e}")
            plain_text_results = "I found some relevant messages in Slack, but I couldn't generate a summary right now. Here are the sources: "
    else:
        plain_text_results = "I couldn't find any relevant messages in Slack."

    # Step 2: Format Slack Results
    search_links = "Relevant messages: "
    if slack_results:
        message_num=0
        for msg in slack_results[:5]:  # Limit to top 5 results
            """
            This used to generate message previews but that gave us context window issues in the LLM and Slack Block Kit. 
            We're falling back to summary with links to the source material.
            """

            permalink = msg.get("permalink", "https://fake.link")
            message_num+=1
            search_links+=(
                f"<{permalink}|[{message_num}]>, "
            )
    else:
        search_links="_No relevant messages found in Slack._"
    
    return plain_text_results, search_links

def summarize_thread(message_context):
    thread_summary=ChatCompletion.create(
            model="gpt-4o",
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

def get_workflows():
    """
    Search Slack workflows using admin.workflows.search 
    """
    try:
        # Call Slack API to fetch workflows
        response = app.client.admin_workflows_search(
            token=SLACK_USER_TOKEN,
            limit=50  # Adjust the limit as needed
        )
        
        workflows = response.get("workflows", [])
        list_of_workflows = []
        
        # Traverse workflows to collect relevant details
        for workflow in workflows:
            title = workflow.get("title", "Unknown Title")
            description = workflow.get("description", "No Description")
            list_of_workflows.append({"title": title, "description": description})
        
        return list_of_workflows
    except Exception as e:
        logger.error(f"Error searching workflows: {e}")
        return []


# Common Processing Function-- parse the message and prepare for next steps. 
def process_event(event, say):
    
    thread_ts = event.get("ts")  #Get the message timestamp
    logger.info(f"started process_event - event_count: {event_count}") #keeping an eye out for duplicate events

    # Determine message subtype
    message_subtype=event.get("subtype")
    logger.info(f"Message subtype: {message_subtype}")

    # Proceed if it's not a message_deleted event
    if message_subtype != "message_deleted" and message_subtype != "message_changed":
        try:
            # pull out relevant message details from the payload
            user_message = event.get("text", "").strip()
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
                         for msg in thread_messages[:5] #added [:5] to only take the first 5 messages as context
                    ]
                )
            logger.info(f"Message context {message_context}")

            # Get the user info
            user_id = event.get("user")
            
            if user_id:
                user_info = app.client.users_info(user=user_id)
                user_name = user_info.get("user", {}).get("real_name")  
                
            else:
                user_name = "unknown"
            logger.info(user_name)

            logger.info("Determining Intent...")
    
            # determine intent
            response = ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an intelligent assistant."},
                    {
                        "role": "user",
                        "content": (
                            f"Determine the intent of this message from {user_name}: {user_message}. "
                            f"Only respond with one of the following options: Summarize Thread, Other. Do not include any additional context or commentary in the response."
                        ),
                    },
                ],
                api_key=OPENAI_API_KEY,
            )

            refined_intent = response["choices"][0]["message"]["content"].strip()
            
            logger.info(f"Refined intent: {refined_intent}")

            # Handle intents, i.e. "Topics"

            if refined_intent == "Summarize Thread":
                response=summarize_thread(message_context)
                say(text=response, thread_ts=thread_ts)

            else:  # refined_intent == "Other"
                # Search for workflows
                workflows = get_workflows()
                # Format workflows for OpenAI
                workflow_context = "\n".join(
                    [f"Title: {wf['title']}, Description: {wf['description']}" for wf in workflows]
                )

                # Search slack for additional context
                refined_query = refine_query(user_message, bot_user_id)
                slack_results = search_slack(refined_query, team_id)
                search_context, references = format_combined_results(slack_results)
                
                cal_prompt = ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a friendly, intelligent assistant designed to analyze Slack conversations, search relevant Slack data, and recommend workflows or actionable steps to address user requests efficiently."},
                        {
                            "role": "user",
                            "content": (
                                f"Here is the context of the current conversation thread:\n{message_context}"
                                f"Aditinally, I have gathered these relevant Slack search results to agument the context:\n{search_context}"
                                f"Finally, consider these workflows available in the Slack workspace:\n{workflow_context}\n"
                                f"Respond directly to this message from {user_name}: {user_message}. "
                                f"Your response should be 3-5 sentences. Your response should be confident, witty, conversational, intelligent, friendly, helpful, clear, and concise. "
                            ),
                        },
                    ],
                    api_key=OPENAI_API_KEY,
                )
                cal_response = cal_prompt["choices"][0]["message"]["content"].strip()
                try:
                    blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": f"{cal_response}\n{references}"}}]

                    app.client.chat_postMessage(
                        channel=channel_id,
                        blocks=blocks,
                        text="bot response",
                        thread_ts=thread_ts,
                        unfurl_links=False,  # Disable link unfurling
                        unfurl_media=False   # Disable media unfurling
                    )

                except Exception as e:
                    say("I don't have that skill yet. Tell Naseer to get on it!", thread_ts=thread_ts)

        except Exception as e:
            logger.error(f"Error processing event: {e}")
            say(text="I'm sorry, I couldn't process your request.", thread_ts=thread_ts)

# Event Listener: Handle Mentions
@app.event("app_mention")
def handle_mention(event, say):
    global event_count
    event_count+=1
    logger.info(f"started handler_mention {event_count}")
    process_event(event,say)

# Handle agent DMs - removing to focus on agent and app-mention experience
@app.event("message")
def handle_direct_message(event, say):
    if event.get("channel_type") == "im":  # Check if it's a direct message
        global event_count
        event_count+=1
        logger.info(f"started handle_message_im {event_count}")
        process_event(event, say)

@app.event("assistant_thread_started")
def handle_assistant_thread_started(event,say):
    global event_count
    event_count+=1
    logger.info(f"started handle_assitant_thread_started {event_count}")
    #process_event(event,say)

@app.event("app_home_opened")
def app_home_opened(event,say):
    try:
        with open("app_home.json","r") as file:
            app_home_json = json.load(file)
    except Exception as e:
        logger.error(f"Error loading app_home.json to app_home_json: {e}")

    try:

        app.client.views_publish(
            user_id=event["user"],
            view=app_home_json
        )

    except Exception as e:
        logger.error(f"Error publishing home tab: {e}")

# Start the App
if __name__ == "__main__":
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    handler.start()