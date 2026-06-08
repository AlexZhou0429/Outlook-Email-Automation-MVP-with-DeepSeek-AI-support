from __future__ import annotations

from src.ai_classifier import AIClassifier
from src.email_clean import clip, draft_text_to_html, html_to_text
from src.graph_client import GraphClient
from src.settings import load_config, load_settings
from src.tracker import already_processed, append_rows, make_tracker_row


def main() -> None:
    settings = load_settings()
    config = load_config(settings.config_path)

    folder_name = settings.mail_folder or config.get("mail", {}).get("intake_folder", "AI Intake")
    max_body_chars = int(config.get("mail", {}).get("max_body_chars", 6000))
    processed_category = config.get("mail", {}).get("processed_category", "AI Processed")
    needs_review_category = config.get("mail", {}).get("needs_review_category", "AI Draft Ready")
    tracker_path = config.get("tracker", {}).get("path", "ops_email_tracker.csv")

    graph = GraphClient(settings.tenant_id, settings.client_id)
    me = graph.get_me()
    print(f"Signed in as: {me.get('displayName')} <{me.get('mail') or me.get('userPrincipalName')}> ")

    folder = graph.find_folder_by_name(folder_name)
    messages = graph.list_messages_in_folder(folder["id"], top=settings.max_messages)
    processed_ids = already_processed(tracker_path)
    ai = AIClassifier(settings.ai_api_key, settings.ai_model, config, base_url=settings.ai_base_url, provider=settings.provider_label)

    rows_to_append = []
    print(f"Found {len(messages)} message(s) in folder: {folder_name}")

    for message in messages:
        message_id = message["id"]
        if message_id in processed_ids:
            print(f"SKIP already processed: {message.get('subject')}")
            continue

        sender = ((message.get("from") or {}).get("emailAddress") or {})
        body_html = (message.get("body") or {}).get("content", "")
        body_text = clip(html_to_text(body_html) or message.get("bodyPreview", ""), max_body_chars)
        email_payload = {
            "subject": message.get("subject", ""),
            "from_name": sender.get("name", ""),
            "from_address": sender.get("address", ""),
            "receivedDateTime": message.get("receivedDateTime", ""),
            "bodyPreview": message.get("bodyPreview", ""),
            "bodyText": body_text,
            "hasAttachments": message.get("hasAttachments", False),
            "categories": message.get("categories", []),
        }

        print(f"\nProcessing: {email_payload['subject']}")
        result = ai.classify_and_draft(email_payload)
        print(f"  -> {result['task_type_name']} | P{result['priority']} | confidence={result['confidence']}")
        print(f"  -> next_action: {result['next_action']}")

        draft_created = False
        if not settings.dry_run:
            draft_html = draft_text_to_html(result.get("draft_reply", ""))
            graph.create_reply_draft(message_id, draft_html)
            draft_created = True

            categories = list(dict.fromkeys((message.get("categories") or []) + [processed_category, needs_review_category]))
            graph.update_message_categories(message_id, categories)
            graph.mark_read(message_id)

        rows_to_append.append(make_tracker_row(message, result, draft_created=draft_created))

    if rows_to_append:
        append_rows(tracker_path, rows_to_append)
        print(f"\nTracker updated: {tracker_path}")
    else:
        print("\nNo new messages processed.")

    if settings.dry_run:
        print("DRY_RUN=true, so no Outlook drafts/categories were created.")
    else:
        print("Done. Check Outlook Drafts and the local tracker CSV.")


if __name__ == "__main__":
    main()
