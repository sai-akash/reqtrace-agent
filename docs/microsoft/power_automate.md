# OneDrive and Power Automate setup

This connects reqtrace-agent to Microsoft 365 without an app registration. OneDrive syncs a folder to your computer, the Python bridge reviews files there, and a Power Automate flow collects a person's approval.

The same design works with a synced SharePoint library, using the SharePoint versions of the actions. That hasn't been tested, because the account used here had no SharePoint site available.

Use fictional documents only.

## Status

| Check | Result |
|---|---|
| Upload to `Requests` produces a draft | Worked (CR-101) |
| Flow sends an approval request with the findings | Worked |
| Approval writes a decision file and exports the report | Worked: report in `Approved`, approver's email recorded in the audit log |
| Audit logs pass their chain check afterwards | Worked |
| Rejection exports nothing | Covered by automated tests, not yet tried through the flow |
| A hand-edited `findings_digest` is refused | Covered by automated tests, not yet tried through the flow |
| Re-uploading the same file doesn't start a second review | Covered by automated tests, not yet tried through the flow |

## How it works

1. Someone uploads a change request, such as `CR-101.md`, to `Requests`.
2. The bridge on your computer reviews it and writes a draft to `Drafts`, both as Markdown and as JSON.
3. The flow sees the new JSON draft and sends an approval request with the findings.
4. The reviewer approves or rejects it. The flow writes a decision file to `Decisions`.
5. The bridge checks the decision. If it's approved and the findings haven't changed, the bridge exports the report to `Approved`.

Problems, such as a badly named file or a decision that doesn't match, are explained in `Problems`.

## Limits

- **Decision files aren't authentication.** Anyone who can write to `Decisions` could create one. The bridge accepts a decision only if it names the exact findings digest, and it logs the approver, so forgery is harder and visible, but not prevented. Only you and the flow should be able to edit `Decisions`.
- **Your computer must be on.** Reviews run locally with Ollama, so nothing happens while it's off.
- **A new version replaces the old review.** Uploading a changed file with the same name supersedes the pending review, and a decision for the old version is refused.
- **One report name per request.** An approved later version overwrites `CR-101_review.md` in `Approved`.
- **Audit logs stay on your computer** in `runs/bridge`, not in OneDrive, so people with folder access can't edit them. They contain approvers' email addresses, and `runs/` is ignored by Git.
- **OneDrive is personal storage.** This shows one person's workflow, not a shared team library.

## 1. Start the bridge

Create a folder called `ReqTrace` in OneDrive, then run this from the project folder, with Ollama running:

```bash
python -m reqtrace.bridge --shared-dir "C:\Users\<you>\OneDrive - <organisation>\ReqTrace"
```

It creates the `Requests`, `Drafts`, `Decisions`, `Approved`, and `Problems` folders, then checks for new files every 15 seconds. Press Ctrl+C to stop. Add `--once` to check one time and exit.

Files are processed only after they've stopped changing for 10 seconds, so partly synced files are skipped.

## 2. Build the flow

In [Power Automate](https://make.powerautomate.com), create an **Automated cloud flow** with these steps.

1. **When a file is created** (OneDrive for Business), with the folder set to `/ReqTrace/Drafts`.
2. **Condition** (built-in): the expression below, **ends with**, `.json`. The bridge also writes a `.md` copy for people to read, and this skips it.

   ```text
   triggerOutputs()?['headers']?['x-ms-file-name']
   ```

   Don't use the **File name** dynamic value here. In this trigger it gave an encoded name, so the Condition was always false.

3. Inside **True**, add **Get file content** (OneDrive for Business), with **File** set to **File identifier** from the trigger.
4. **Parse JSON**, with **Content** set to the expression below. The **File content** value arrives as raw bytes, which Parse JSON rejects.

   ```text
   json(base64ToString(body('Get_file_content')?['$content']))
   ```

   Use this schema:

   ```json
   {
     "type": "object",
     "properties": {
       "review_id": {"type": "string"},
       "change_request_id": {"type": "string"},
       "findings_digest": {"type": "string"},
       "summary": {"type": "string"}
     },
     "required": ["review_id", "findings_digest", "summary"]
   }
   ```

5. **Start and wait for an approval**: **Approve/Reject - First to respond**, with the title `ReqTrace review: ` followed by **review_id**, assigned to the reviewer, and **summary** in the details.
6. **Compose**, with this input. Insert **review_id** and **findings_digest** from Parse JSON, and **Outcome**, **Responses Approver email**, and **Responses Approver name** from the approval step. Power Automate wraps this step in **For each** because of the responses, which is fine with one approver.

   ```text
   {
     "review_id": "",
     "findings_digest": "",
     "outcome": "",
     "approver_email": "",
     "approver_name": ""
   }
   ```

7. **Create file** (OneDrive for Business), in `/ReqTrace/Decisions`, named **review_id** followed by `_decision.json`, with **Outputs** from Compose as the content.

## 3. Test it

Click **Test**, choose **Manually**, then upload a change request to `Requests`. The flow only reacts to drafts created after it starts listening.

To retest without another review, copy an existing `.json` draft in `Drafts` under a new name. It has the same review ID and findings, so the bridge accepts a decision for it, but only once per review.

A review takes about 3 minutes on a laptop CPU. The flow then waits until someone responds to the approval request in Power Automate, Outlook, or Teams.
