#!/usr/bin/env python3
"""
Sync Copilot chat sessions into the local SQLite database.
Only new/changed sessions (by file hash) are inserted/updated.
"""

import argparse
import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import unquote

from db_manager import BackupDatabase

POSSIBLE_STORAGE_PATHS = [
    Path.home() / ".vscode-server/data/User/workspaceStorage",
    Path.home() / ".config/Code/User/workspaceStorage",
    Path.home() / "Library/Application Support/Code/User/workspaceStorage",  # macOS
    Path.home() / ".config/Code - OSS/User/workspaceStorage",  # OSS
    Path("/mnt/c/Users/dimoss/AppData/Roaming/Code/User/workspaceStorage"),  # Windows via WSL
]

logger = logging.getLogger("chat-sync")


def _find_storage_path() -> Path:
    for path in POSSIBLE_STORAGE_PATHS:
        if path.exists():
            return path
    return Path.home() / ".config/Code/User/workspaceStorage"


def _decode_workspace_path(raw_path: str) -> str:
    if not raw_path:
        return ""
    cleaned = raw_path.replace("file://", "").replace("%20", " ")
    cleaned = re.sub(r"%([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), cleaned)
    return unquote(cleaned)


def _hash_file(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _extract_repo_info(variables: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    repo_name = None
    repo_owner = None
    repo_branch = None
    repo_default_branch = None

    for variable in variables:
        value = variable.get("value")
        if not value or not isinstance(value, str):
            continue

        for line in value.splitlines():
            if "Repository name:" in line:
                repo_name = line.split("Repository name:", 1)[-1].strip() or repo_name
            elif line.startswith("Owner:"):
                repo_owner = line.split("Owner:", 1)[-1].strip() or repo_owner
            elif "Current branch:" in line:
                repo_branch = line.split("Current branch:", 1)[-1].strip() or repo_branch
            elif "Default branch:" in line:
                repo_default_branch = line.split("Default branch:", 1)[-1].strip() or repo_default_branch

    return {
        "repo_name": repo_name,
        "repo_owner": repo_owner,
        "repo_branch": repo_branch,
        "repo_default_branch": repo_default_branch,
    }


def _discover_workspaces(storage_path: Path) -> Dict[str, Dict[str, Any]]:
    workspace_map: Dict[str, Dict[str, Any]] = {}

    if not storage_path.exists():
        logger.warning("VS Code storage path not found: %s", storage_path)
        return workspace_map

    for ws_dir in storage_path.iterdir():
        if not ws_dir.is_dir():
            continue

        workspace_json = ws_dir / "workspace.json"
        ws_path = ""
        project_name = ws_dir.name

        if workspace_json.exists():
            try:
                with open(workspace_json, "r") as f:
                    ws_data = json.load(f)
                ws_path = ws_data.get("folder") or ws_data.get("workspace", "")
                ws_path = _decode_workspace_path(ws_path)
                project_name = Path(ws_path).stem if ws_path else ws_dir.name
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("Error parsing workspace %s: %s", ws_dir.name, exc)

        chat_sessions_dir = ws_dir / "chatSessions"
        chat_files = list(chat_sessions_dir.glob("*.json")) if chat_sessions_dir.exists() else []

        if not chat_files:
            logger.debug("No chat sessions in workspace %s", ws_dir.name)
            continue

        workspace_map[ws_dir.name] = {
            "workspace_id": ws_dir.name,
            "workspace_path": ws_path,
            "project_name": project_name,
            "chat_sessions_dir": chat_sessions_dir,
            "chat_files": chat_files,
            "chat_count": len(chat_files),
        }

    return workspace_map


def _parse_chat_session(
    file_path: Path,
    workspace_info: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]], Optional[str]]:
    try:
        if file_path.stat().st_size == 0:
            logger.debug("Skipping empty file: %s", file_path)
            return None, None, "empty_file"
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        messages: List[Dict[str, Any]] = []
        requests = data.get("requests", [])
        total_content_refs = 0
        total_code_citations = 0
        request_model_id = None
        agent_id = None
        agent_name = None
        repo_info = {
            "repo_name": None,
            "repo_owner": None,
            "repo_branch": None,
            "repo_default_branch": None,
        }

        position = 0
        for req in requests:
            if not request_model_id and req.get("modelId"):
                request_model_id = req.get("modelId")

            if not agent_id or not agent_name:
                agent = req.get("agent") or {}
                if isinstance(agent, dict):
                    agent_id = agent.get("id") or agent.get("name")
                    agent_name = agent.get("fullName") or agent.get("name")

            variable_data = req.get("variableData") or {}
            variables = variable_data.get("variables") if isinstance(variable_data, dict) else None
            if isinstance(variables, list) and variables:
                repo_info = _extract_repo_info(variables)

            content_refs = req.get("contentReferences")
            if isinstance(content_refs, list):
                total_content_refs += len(content_refs)

            code_citations = req.get("codeCitations")
            if isinstance(code_citations, list):
                total_code_citations += len(code_citations)

            user_msg = req.get("message", {})
            user_text = user_msg.get("text", "") if isinstance(user_msg, dict) else str(user_msg)

            if user_text:
                messages.append({
                    "position": position,
                    "role": "user",
                    "content": user_text,
                    "timestamp": req.get("timestamp"),
                    "model": None,
                })
                position += 1

            response = req.get("response", {})
            if isinstance(response, dict):
                response_text = ""
                if "value" in response:
                    response_text = response["value"]
                elif "result" in response:
                    result = response.get("result")
                    if isinstance(result, dict):
                        response_text = result.get("value", "") or result.get("message", "")
                    else:
                        response_text = str(result)
                elif "message" in response:
                    response_text = response["message"]

                if response_text:
                    messages.append({
                        "position": position,
                        "role": "assistant",
                        "content": response_text,
                        "timestamp": response.get("timestamp") or req.get("timestamp"),
                        "model": response.get("model"),
                    })
                    position += 1

        creation_ts = data.get("creationDate", 0)
        last_msg_ts = data.get("lastMessageDate", creation_ts)

        if creation_ts > 1e12:
            creation_ts /= 1000
        if last_msg_ts > 1e12:
            last_msg_ts /= 1000

        creation_date = datetime.fromtimestamp(creation_ts).isoformat() if creation_ts else None
        last_message_date = datetime.fromtimestamp(last_msg_ts).isoformat() if last_msg_ts else None

        selected_model = data.get("selectedModel") or {}
        selected_meta = selected_model.get("metadata") if isinstance(selected_model, dict) else {}
        selected_identifier = selected_model.get("identifier") if isinstance(selected_model, dict) else None
        selected_vendor = selected_meta.get("vendor") if isinstance(selected_meta, dict) else None
        selected_name = selected_meta.get("name") if isinstance(selected_meta, dict) else None
        selected_family = selected_meta.get("family") if isinstance(selected_meta, dict) else None

        mode = data.get("mode") or {}
        mode_id = mode.get("id") if isinstance(mode, dict) else None
        mode_kind = mode.get("kind") if isinstance(mode, dict) else None

        attachments = data.get("attachments") if isinstance(data.get("attachments"), list) else []
        selections = data.get("selections") if isinstance(data.get("selections"), list) else []

        return {
            "session_id": data.get("sessionId", file_path.stem),
            "workspace_id": workspace_info.get("workspace_id"),
            "workspace_name": workspace_info.get("project_name", "unknown"),
            "workspace_path": workspace_info.get("workspace_path", ""),
            "project_name": workspace_info.get("project_name", "unknown"),
            "creation_date": creation_date,
            "last_message_date": last_message_date,
            "requester_username": data.get("requesterUsername", "user"),
            "responder_username": data.get("responderUsername", "GitHub Copilot"),
            "message_count": len(messages),
            "file_path": str(file_path),
            "file_size": file_path.stat().st_size,
            "custom_title": data.get("customTitle"),
            "initial_location": data.get("initialLocation"),
            "mode_id": mode_id,
            "mode_kind": mode_kind,
            "selected_model_identifier": selected_identifier,
            "selected_model_name": selected_name,
            "selected_model_vendor": selected_vendor,
            "selected_model_family": selected_family,
            "request_model_id": request_model_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "has_pending_edits": 1 if data.get("hasPendingEdits") else 0,
            "input_text": data.get("inputText"),
            "attachments_count": len(attachments),
            "selections_count": len(selections),
            "content_references_count": total_content_refs,
            "code_citations_count": total_code_citations,
            **repo_info,
        }, messages, None

    except json.JSONDecodeError:
        logger.debug("Invalid JSON: %s", file_path)
        return None, None, "invalid_json"
    except Exception as exc:
        logger.exception("Error parsing %s: %s", file_path.name, exc)
        return None, None, "parse_error"


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Copilot chat sessions to local DB")
    parser.add_argument("--db", type=str, default="copilot_backup.db", help="SQLite database path")
    parser.add_argument("--workspace", type=str, help="Filter by workspace/project name")
    parser.add_argument("--storage-path", type=Path, help="Override VS Code storage path")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Process all sessions (ignores last sync time)",
    )
    parser.add_argument(
        "--force-retry",
        action="store_true",
        help="Retry all sessions, even unchanged ones (ignores file hash)",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Only retry sessions that previously had errors",
    )
    parser.add_argument(
        "--retry-empty",
        action="store_true",
        help="Retry sessions with 0 messages",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="Process in batches of N sessions (0=all at once)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Write skipped/error details to this JSON file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (very noisy)",
    )

    args = parser.parse_args()

    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG
    if args.debug:
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    storage_path = args.storage_path or _find_storage_path()
    logger.info("Using storage path: %s", storage_path)
    workspace_map = _discover_workspaces(storage_path)

    db = BackupDatabase(args.db)
    last_sync_time = None if args.full else db.get_last_chat_sync_time()

    # Get list of sessions to retry if requested
    retry_session_ids = set()
    if args.retry_errors or args.retry_empty:
        cursor = db.conn.cursor()
        if args.retry_empty:
            cursor.execute("SELECT session_id FROM chat_sessions WHERE message_count = 0")
            retry_session_ids.update(row[0] for row in cursor.fetchall())
            logger.info("Found %s empty sessions to retry", len(retry_session_ids))
        # Note: We don't have error tracking yet, but we can add it later
        cursor.close()

    stats = {
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "total_sessions": 0,
        "inserted_sessions": 0,
        "updated_sessions": 0,
        "skipped_sessions": 0,
        "errors": 0,
    }
    issues: List[Dict[str, Any]] = []

    all_files: List[tuple[Path, Dict[str, Any]]] = []
    for _, ws_info in workspace_map.items():
        project_name = ws_info.get("project_name", "")
        if args.workspace and args.workspace.lower() not in project_name.lower():
            continue
        for chat_file in ws_info.get("chat_files", []):
            all_files.append((chat_file, ws_info))

    total_files = len(all_files)
    logger.info("Found %s chat session files to process", total_files)

    if total_files == 0:
        logger.warning("No files to process. Check storage path or workspace filter.")
        db.close()
        return 0

    # Process in batches if requested
    batch_size = args.batch_size if args.batch_size > 0 else total_files
    num_batches = (total_files + batch_size - 1) // batch_size
    if num_batches > 1:
        logger.info("Processing in %s batches of ~%s files", num_batches, batch_size)

    try:
        for index, (chat_file, ws_info) in enumerate(all_files, start=1):
            session_id = chat_file.stem
            
            # Check if we should retry this session
            force_process = args.force_retry or (session_id in retry_session_ids)
            
            if not force_process and last_sync_time:
                last_sync_ts = datetime.fromisoformat(last_sync_time).timestamp()
                if chat_file.stat().st_mtime <= last_sync_ts:
                    stats["skipped_sessions"] += 1
                    logger.debug("Skipping old file: %s", chat_file)
                    issues.append({
                        "file_path": str(chat_file),
                        "session_id": session_id,
                        "reason": "older_than_last_sync",
                    })
                    continue

            stats["total_sessions"] += 1
            file_hash = _hash_file(chat_file)

            session, messages, error_reason = _parse_chat_session(chat_file, ws_info)
            if not session or messages is None:
                stats["errors"] += 1
                issues.append({
                    "file_path": str(chat_file),
                    "session_id": session_id,
                    "reason": error_reason or "unknown_parse_error",
                    "file_size": chat_file.stat().st_size,
                })
                logger.warning("Failed to parse %s: %s", chat_file.name, error_reason)
                continue

            # Skip unchanged files unless force_process is True
            if not force_process:
                existing_hash = db.get_chat_session_hash(session_id)
                if existing_hash == file_hash:
                    stats["skipped_sessions"] += 1
                    logger.debug("Skipping unchanged file: %s", chat_file)
                    issues.append({
                        "file_path": str(chat_file),
                        "session_id": session.get("session_id"),
                        "reason": "unchanged_hash",
                    })
                    continue

            status = db.upsert_chat_session(session, messages, file_hash)
            if status == "inserted":
                stats["inserted_sessions"] += 1
                logger.debug("Inserted session: %s (%s messages)", session_id, len(messages))
            elif status == "updated":
                stats["updated_sessions"] += 1
                logger.debug("Updated session: %s (%s messages)", session_id, len(messages))
            else:
                stats["skipped_sessions"] += 1

            if index % 250 == 0:
                logger.info(
                    "Processed %s/%s | inserted=%s updated=%s skipped=%s errors=%s",
                    index,
                    total_files,
                    stats["inserted_sessions"],
                    stats["updated_sessions"],
                    stats["skipped_sessions"],
                    stats["errors"],
                )
            
            # Batch commit every batch_size if specified
            if args.batch_size > 0 and index % args.batch_size == 0:
                db.conn.commit()
                logger.info("Committed batch at %s/%s", index, total_files)

        stats["finished_at"] = datetime.now().isoformat()
        log_file = args.log_file
        if not log_file:
            log_dir = Path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = log_dir / f"chat-sync-issues_{stamp}.json"

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "stats": stats,
                    "issues": issues,
                },
                f,
                indent=2,
            )

        run_id = db.record_chat_sync_run(stats)

        logger.info("Chat sync complete")
        logger.info("Run ID: %s", run_id)
        logger.info("Total sessions: %s", stats["total_sessions"])
        logger.info("Inserted: %s", stats["inserted_sessions"])
        logger.info("Updated: %s", stats["updated_sessions"])
        logger.info("Skipped: %s", stats["skipped_sessions"])
        logger.info("Errors: %s", stats["errors"])
        logger.info("Issues log: %s", log_file)
        return 0
    except KeyboardInterrupt:
        stats["finished_at"] = datetime.now().isoformat()
        log_file = args.log_file
        if not log_file:
            log_dir = Path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = log_dir / f"chat-sync-issues_{stamp}.json"

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "stats": stats,
                    "issues": issues,
                },
                f,
                indent=2,
            )

        db.record_chat_sync_run(stats)
        logger.warning("Sync interrupted. Partial results saved.")
        logger.warning("Issues log: %s", log_file)
        return 130
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
