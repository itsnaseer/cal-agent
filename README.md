# Meet Cal

This a Collaborative Automation Liaison (CAL). 
Cal is mostly an exploration on things we can do in Slack with an agentic interface. Today it can
* Search Slack and summarize the responses
* Summarize a thread
* Recommend workflows to accomplish tasks
Cal is activated either by mentioning the app (`@cal`) or starting a DM/Agent session. 

If you have ideas for how we can make Cal more useful, send a message to `@Naseer Rashid` in Slack. 

## Set-up

### Deploy
This app uses [https://api.slack.com/apis/socket-mode](socket mode). 
Here are the deploy methods that have been tested: 
* Local dev: Socket mode, [https://docs.python.org/3/library/venv.html](venv), and a B+ workspace
* Cloud deploy: Heroku, Socket mode, Slack.0 grid environment. 

### Environment variables (.env)
```
SLACK_USER_TOKEN: `User OAuth Token`
BOT_USER_TOKEN: `Bot User OAUTH Token`
SLACK_APP_TOKEN=`App-Level Token`
OPENAI_API_KEY=`Your OpenAI Key`
SLACK_TEAM_ID=`Workspace ID` - Starts with a T. In grid, just pick a workspace your user is already in. Doesn't really matter which one. 
SLACK_ENTERPRISE_ID=`Grid Enterprise ID` - Leave blank for single-workspace deploys
```

## Additional details
### LLM
Call uses a combination of OpenAI models. Feel free to consolidate to your favorite one. 

### Limitations
Most limitations are related to rate limiting on the LLM side. 
DM experience in a single-workspace environment doesn't always work how we'd expect an agent session to behave.  

### Token management
Installing this app for multiple users in an environment hasn't been tested so do it at your own risk. There's no token managemet mechanism built into this app. 