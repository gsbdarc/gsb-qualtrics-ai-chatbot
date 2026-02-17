 # Integrating a Stanford AI Chatbot into Qualtrics

*Adapted from [Tey et al. (2024, PNAS Nexus)](https://osf.io/preprints/psyarxiv/p9stw_v3) for use with GCP Cloud Functions and Stanford AI API.*

---

## Prerequisites

Before starting, you need:
- A deployed Cloud Function URL (e.g., `https://us-west1-your-project.cloudfunctions.net/stanford-proxy-v2`)
- Access to edit your Qualtrics survey

---

## Step 1: Set Up a "Text / Graphic" Item in Qualtrics

1. In your Qualtrics survey, add a new question
2. Change the question type to **"Text / Graphic"**
3. This will house your chatbot interface

---

## Step 2: Copy + Paste the HTML into the Item

This code creates the chat interface for participants.

1. Select the question you created in Step 1
2. Click on **"HTML View"** (top-right of the editor)
3. Copy and paste the code from `view.html`:

```html
<div id="chat-container">
  <div id="chat-history-1">&nbsp;</div>
  <div id="chat-input">
    <input type="text" placeholder="Type your message here..." id="message-input-1">
    <button id="send-button-1">Send</button>
  </div>
</div>
```

---

## Step 3: Copy + Paste the CSS Styling Code

This prettifies the chat interface.

1. Go to **"Look and Feel"** on the left taskbar
2. Select **"Style"**
3. Click **"Edit"** next to **"Custom CSS"**
4. Copy and paste the contents of `styling.css`

**Alternative:** If you prefer to only modify CSS for this specific item, you can place the CSS inside `<style>` tags before the HTML in Step 2.

---

## Step 4: Copy + Paste the JavaScript Code

This sets up the connection with your Cloud Function and manages the conversation.

1. Select the question you created in Step 1
2. Click the **gear icon** → **"Add JavaScript"**
3. Copy and paste the contents of `question.js`
4. **Important:** Update the proxy URL on this line:

```javascript
fetch("YOUR_CLOUD_FUNCTION_URL_HERE", {
```

Replace `YOUR_CLOUD_FUNCTION_URL_HERE` with your deployed Cloud Function URL, for example:
```javascript
fetch("https://us-west1-your-project.cloudfunctions.net/stanford-proxy-v2", {
```

---

## Step 5: Set Embedded Variables for Configuration

Set the following embedded variables in your **Survey Flow**. Make sure these are set **before** the block containing the chatbot.

1. Go to **Survey Flow**
2. Click **"Add a New Element Here"** → **"Embedded Data"**
3. Add these variables:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `prompt` | System prompt - tells the chatbot its role and rules | `You are a helpful assistant` |
| `temperature` | Randomness (0-1). Higher = more creative, Lower = more focused | `0.7` |
| `max_tokens` | Maximum length of chatbot response | `1000` |
| `model` | The AI model to use | `gpt-4-turbo` |
| `delay_per_word` | Seconds of delay per word in the bot response, to simulate human typing speed (0 for instant). Total delay = word count x this value, capped at 10 seconds. | `0.05` |

**Note:** Available models depend on your Stanford AI API access. Common options include `gpt-4-turbo`, `gpt-4o`, `gpt-4o-mini`.

---

## Step 6: Set Embedded Variables for Transcripts

This records the conversation between participants and the chatbot.

1. In the same **Embedded Data** element (or a new one), add variables for transcripts
2. Add as many as you expect interactions:

**User messages:**
- `msg_1`, `msg_2`, `msg_3`, ... `msg_20`

**Bot responses:**
- `response_1`, `response_2`, `response_3`, ... `response_20`

Leave the values blank - they will be set automatically during the conversation.

---

## Testing Your Setup

1. **Preview** your survey in Qualtrics
2. Type a message and click Send
3. You should see the chatbot respond

**If it's not working**, check:
- Browser console (F12 → Console) for JavaScript errors
- Your Cloud Function logs in GCP Console
- That all embedded variables are set correctly
- That the proxy URL is correct in the JavaScript

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No response" or empty reply | Check Cloud Function logs in GCP Console |
| CORS error in console | Verify your Cloud Function has CORS headers configured |
| "Service Temporarily Unavailable" | Check `SERVICE_ENABLED` environment variable in Cloud Function |
| Slow responses | This is normal - AI responses take 2-10 seconds |

---

## Automated Build Notes

When using the automated build script (`build_survey.py` or the GitHub Actions workflow), the following behaviors apply:

- **Dedicated block (landing zone):** When a chatbot question is **first created**, it is placed into its own block named "AI Chatbot - {question_name}" near the top of the survey flow. This serves as a landing zone so you can easily find the new question in a complex survey. You are free to move the question into any other block, reorder it, or delete the landing-zone block entirely. On subsequent builds (e.g. updating the prompt or model), the script will **not** move the question back — your arrangement is preserved. If you delete the block and the question inside it, re-running the build will recreate both from scratch.
- **Dynamic typing delay:** The `delay_per_word` value is multiplied by the number of words in each bot response. For example, with `delay_per_word = 0.05`, a 50-word response will show a typing indicator for 2.5 seconds before the message appears. The total delay is capped at 10 seconds regardless of response length.

---

## Credits

This integration is adapted from:

> Tey, K. S.\*, Mazar, A.\*, Tomaino, G.\*, Duckworth, A. L., & Ungar, L. H. (2024). People Judge Others More Harshly After Talking to Bots. *PNAS Nexus*.

Original tutorial by Kian Siong Tey (University of Hong Kong), Asaf Mazar (Complete Behavioral Science Consulting), and Geoff Tomaino (University of Florida).

Modified for GCP Cloud Functions and Stanford AI API.