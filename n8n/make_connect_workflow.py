"""Writes n8n\\shritub_connect_workflow.json (import it in n8n; Shri Tools > Connect also serves it with your key)."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))


def nid(n):
    return f"7b1c0e10-2a3d-4e5f-9a00-{n:012d}"


def key_header(expr):
    return {"sendHeaders": True, "headerParameters": {"parameters": [{"name": "X-Api-Key", "value": expr}]}}


NOTE = (
    "## Shri Tools Connect\n"
    "1. Start **Shri Tools** (desktop shortcut). In Shri Tools > **Connect** you can set an API key (optional on this "
    "laptop) and download this workflow with your key already filled in.\n"
    "2. Edit **Your video** (title, idea, season, language) and click **Test workflow**, or call the webhook "
    "**POST /webhook/shritub-connect** with the same fields as JSON.\n"
    "3. Shri Tools writes the story, draws the pictures, makes every scene with MiniMax H3 (voices + sounds), checks "
    "them, joins the final video and makes a Short, thumbnails and YouTube texts. This flow checks every 10 minutes "
    "(one scene takes ~10 min on a 4 GB GPU, an 18-scene episode ~4 h).\n"
    "4. **Download final video** gives the mp4 as binary: connect **YouTube > Upload** after it. Titles, description "
    "and tags are in `video.publish` of the last check.\n\n"
    "Fields: title, idea (or scenes), season (title) or season_id, language (en, hi, kn, kok, mr, ta, te, ml, bn, gu, "
    "pa, ur), style (pixar, cinematic, anime, storybook, clay), cast (names), scenes_wanted, approve_pictures (true = "
    "stop after the pictures until you press Make videos), callback_url.")

CODE = """// Fields come from 'Your video' (manual) or from the webhook body
const keys = ['title', 'idea', 'prompt', 'scenes', 'season', 'season_id', 'language', 'style', 'cast',
  'scenes_wanted', 'approve_pictures', 'music', 'hook_text', 'callback_url'];
return $input.all().map((item) => {
  const src = item.json.body ?? item.json;
  const payload = {};
  for (const k of keys) if (src[k] !== undefined && src[k] !== '') payload[k] = src[k];
  if (!payload.idea && !payload.prompt && !payload.scenes) throw new Error('Send an idea or scenes');
  const key = item.json.api_key === 'PUT-YOUR-API-KEY-HERE-OR-LEAVE-EMPTY' ? '' : (item.json.api_key || '');
  return { json: { payload, base_url: item.json.base_url, api_key: key } };
});"""


def condition(cid, left, right, operator):
    return {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                           "conditions": [{"id": nid(cid), "leftValue": left, "rightValue": right,
                                           "operator": operator}], "combinator": "and"}, "options": {}}


KEY = "={{ $('Make request body').first().json.api_key }}"
nodes = [
    {"parameters": {"content": NOTE, "height": 540, "width": 580}, "id": nid(1), "name": "How to use",
     "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": [-260, -640]},
    {"parameters": {}, "id": nid(2), "name": "Start (manual)", "type": "n8n-nodes-base.manualTrigger",
     "typeVersion": 1, "position": [-260, 0]},
    {"parameters": {"assignments": {"assignments": [
        {"id": nid(31), "name": "title", "value": "Say Thank You, Tuntun!", "type": "string"},
        {"id": nid(32), "name": "idea", "value": "Tuntun meets the vegetable seller and learns to say thank you.",
         "type": "string"},
        {"id": nid(33), "name": "season", "value": "Shri Mama and Tuntun", "type": "string"},
        {"id": nid(34), "name": "language", "value": "en", "type": "string"},
        {"id": nid(35), "name": "scenes_wanted", "value": 18, "type": "number"},
        {"id": nid(36), "name": "approve_pictures", "value": False, "type": "boolean"}]}, "options": {}},
     "id": nid(3), "name": "Your video", "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": [-40, 0]},
    {"parameters": {"httpMethod": "POST", "path": "shritub-connect", "responseMode": "onReceived", "options": {}},
     "id": nid(4), "name": "Webhook (from other flows)", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
     "position": [-40, 220], "webhookId": nid(40)},
    {"parameters": {"assignments": {"assignments": [
        {"id": nid(51), "name": "base_url", "value": "http://127.0.0.1:7880", "type": "string"},
        {"id": nid(52), "name": "api_key", "value": "PUT-YOUR-API-KEY-HERE-OR-LEAVE-EMPTY", "type": "string"}]},
        "includeOtherFields": True, "options": {}},
     "id": nid(5), "name": "Shri Tools settings", "type": "n8n-nodes-base.set", "typeVersion": 3.4,
     "position": [180, 100]},
    {"parameters": {"jsCode": CODE}, "id": nid(6), "name": "Make request body", "type": "n8n-nodes-base.code",
     "typeVersion": 2, "position": [400, 100]},
    {"parameters": {"method": "POST", "url": "={{ $json.base_url }}/api/connect/videos",
                    **key_header("={{ $json.api_key }}"), "sendBody": True, "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify($json.payload) }}", "options": {}},
     "id": nid(7), "name": "Start video", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
     "position": [620, 100]},
    {"parameters": {"amount": 10, "unit": "minutes"}, "id": nid(8), "name": "Wait 10 min",
     "type": "n8n-nodes-base.wait", "typeVersion": 1.1, "position": [840, 100], "webhookId": nid(80)},
    {"parameters": {"url": "={{ $('Start video').first().json.video.status_url }}", **key_header(KEY),
                    "options": {}},
     "id": nid(9), "name": "Check video", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
     "position": [1060, 100]},
    {"parameters": condition(101, "={{ $json.video.state }}", "done", {"type": "string", "operation": "equals"}),
     "id": nid(10), "name": "Done?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [1280, 100]},
    {"parameters": condition(111, "={{ ['failed', 'cancelled'].includes($json.video.state) }}", True,
                             {"type": "boolean", "operation": "true", "singleValue": True}),
     "id": nid(11), "name": "Failed?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [1500, 260]},
    {"parameters": {"errorMessage": "={{ 'Shri Tools: ' + $json.video.title + ' ' + $json.video.state + ': ' + "
                                    "($json.video.error || 'see the Build tab in Shri Tools') }}"},
     "id": nid(12), "name": "Stop: video failed", "type": "n8n-nodes-base.stopAndError", "typeVersion": 1,
     "position": [1720, 200]},
    {"parameters": {"url": "={{ $json.video.files.final }}", **key_header(KEY),
                    "options": {"response": {"response": {"responseFormat": "file"}}}},
     "id": nid(13), "name": "Download final video", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
     "position": [1500, 0]},
]


def to(node):
    return [{"node": node, "type": "main", "index": 0}]


connections = {
    "Start (manual)": {"main": [to("Your video")]},
    "Your video": {"main": [to("Shri Tools settings")]},
    "Webhook (from other flows)": {"main": [to("Shri Tools settings")]},
    "Shri Tools settings": {"main": [to("Make request body")]},
    "Make request body": {"main": [to("Start video")]},
    "Start video": {"main": [to("Wait 10 min")]},
    "Wait 10 min": {"main": [to("Check video")]},
    "Check video": {"main": [to("Done?")]},
    "Done?": {"main": [to("Download final video"), to("Failed?")]},
    "Failed?": {"main": [to("Stop: video failed"), to("Wait 10 min")]},
}

if __name__ == "__main__":
    wf = {"name": "Shri Tools Connect - make a video", "nodes": nodes, "connections": connections, "pinData": {},
          "settings": {"executionOrder": "v1"}}
    with open(os.path.join(HERE, "shritub_connect_workflow.json"), "w", encoding="utf-8") as f:
        json.dump(wf, f, indent=2, ensure_ascii=False)
    print("written", len(nodes), "nodes")
