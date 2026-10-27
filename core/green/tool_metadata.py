"""Tool metadata — domain and capability mapping for all JARVIS tools.

This module provides the canonical mapping from tool names to GREEN metadata
(domain, risk level, capabilities, side effects). It is used by the Tool
Registry to enrich entries and by the parity checker to verify coverage.

Kept separate from tool_registry.py so it can be updated without touching
the registry infrastructure.
"""
from __future__ import annotations

from core.green.tool_registry import ToolDomain, RiskLevel


TOOL_DOMAIN_MAP: dict[str, ToolDomain] = {
    "date_time": ToolDomain.DATE_TIME,
    "open_app": ToolDomain.WINDOWS,
    "web_search": ToolDomain.WEB,
    "weather_report": ToolDomain.WEB,
    "check_messages": ToolDomain.GMAIL,
    "prepare_message_reply": ToolDomain.GMAIL,
    "send_message": ToolDomain.GMAIL,
    "email_control": ToolDomain.GMAIL,
    "reminder": ToolDomain.REMINDERS,
    "youtube_video": ToolDomain.MULTIMEDIA,
    "media_control": ToolDomain.MULTIMEDIA,
    "screen_process": ToolDomain.VISION,
    "computer_settings": ToolDomain.WINDOWS,
    "browser_control": ToolDomain.WEB,
    "file_controller": ToolDomain.FILES,
    "desktop_control": ToolDomain.WINDOWS,
    "code_helper": ToolDomain.DEVELOPMENT,
    "dev_agent": ToolDomain.DEVELOPMENT,
    "agent_task": ToolDomain.AGENT,
    "computer_control": ToolDomain.WINDOWS,
    "game_updater": ToolDomain.WINDOWS,
    "flight_finder": ToolDomain.WEB,
    "graphics_quality": ToolDomain.UI,
    "jarvis_ui_control": ToolDomain.UI,
    "deep_research": ToolDomain.DEVELOPMENT,
    "create_presentation": ToolDomain.PRESENTATIONS,
    "task_status": ToolDomain.AGENT,
    "file_processor": ToolDomain.FILES,
    "save_memory": ToolDomain.MEMORY,
    "local_memory_search": ToolDomain.MEMORY,
    "lilith_memory_search": ToolDomain.LILITH,
    "lilith_memory_store": ToolDomain.LILITH,
    "lilith_memory_delete": ToolDomain.LILITH,
    "lilith_home_action": ToolDomain.LILITH,
    "lilith_request_approval": ToolDomain.LILITH,
    "lilith_resolve_approval": ToolDomain.LILITH,
    "lilith_health": ToolDomain.LILITH,
    "lilith_runtime_status": ToolDomain.LILITH,
    "lilith_docs_list": ToolDomain.LILITH,
    "lilith_docs_read": ToolDomain.LILITH,
    "lilith_docs_search": ToolDomain.LILITH,
    "lilith_source_list": ToolDomain.LILITH,
    "lilith_source_read": ToolDomain.LILITH,
    "lilith_source_search": ToolDomain.LILITH,
    "lilith_git_status": ToolDomain.LILITH,
    "lilith_command_submit": ToolDomain.LILITH,
    "lilith_routine": ToolDomain.LILITH,
    "open_capabilities_catalog": ToolDomain.SYSTEM,
    "calculator": ToolDomain.SYSTEM,
}

TOOL_RISK_MAP: dict[str, RiskLevel] = {
    "date_time": RiskLevel.READ_ONLY,
    "open_app": RiskLevel.LOW,
    "web_search": RiskLevel.READ_ONLY,
    "weather_report": RiskLevel.READ_ONLY,
    "check_messages": RiskLevel.READ_ONLY,
    "prepare_message_reply": RiskLevel.LOW,
    "send_message": RiskLevel.HIGH,
    "email_control": RiskLevel.MEDIUM,
    "reminder": RiskLevel.LOW,
    "youtube_video": RiskLevel.LOW,
    "media_control": RiskLevel.LOW,
    "screen_process": RiskLevel.READ_ONLY,
    "computer_settings": RiskLevel.MEDIUM,
    "browser_control": RiskLevel.MEDIUM,
    "file_controller": RiskLevel.MEDIUM,
    "desktop_control": RiskLevel.LOW,
    "code_helper": RiskLevel.MEDIUM,
    "dev_agent": RiskLevel.MEDIUM,
    "agent_task": RiskLevel.MEDIUM,
    "computer_control": RiskLevel.HIGH,
    "game_updater": RiskLevel.MEDIUM,
    "flight_finder": RiskLevel.READ_ONLY,
    "graphics_quality": RiskLevel.LOW,
    "jarvis_ui_control": RiskLevel.LOW,
    "deep_research": RiskLevel.LOW,
    "create_presentation": RiskLevel.LOW,
    "task_status": RiskLevel.READ_ONLY,
    "file_processor": RiskLevel.MEDIUM,
    "save_memory": RiskLevel.LOW,
    "local_memory_search": RiskLevel.READ_ONLY,
    "lilith_memory_search": RiskLevel.READ_ONLY,
    "lilith_memory_store": RiskLevel.MEDIUM,
    "lilith_memory_delete": RiskLevel.HIGH,
    "lilith_home_action": RiskLevel.HIGH,
    "lilith_request_approval": RiskLevel.LOW,
    "lilith_resolve_approval": RiskLevel.MEDIUM,
    "lilith_health": RiskLevel.READ_ONLY,
    "lilith_runtime_status": RiskLevel.READ_ONLY,
    "lilith_docs_list": RiskLevel.READ_ONLY,
    "lilith_docs_read": RiskLevel.READ_ONLY,
    "lilith_docs_search": RiskLevel.READ_ONLY,
    "lilith_source_list": RiskLevel.READ_ONLY,
    "lilith_source_read": RiskLevel.READ_ONLY,
    "lilith_source_search": RiskLevel.READ_ONLY,
    "lilith_git_status": RiskLevel.READ_ONLY,
    "lilith_command_submit": RiskLevel.HIGH,
    "lilith_routine": RiskLevel.HIGH,
    "open_capabilities_catalog": RiskLevel.READ_ONLY,
    "calculator": RiskLevel.READ_ONLY,
}

TOOL_CAPABILITIES_MAP: dict[str, list[str]] = {
    "date_time": ["system.read"],
    "open_app": ["windows.apps"],
    "web_search": ["network.read"],
    "weather_report": ["network.read"],
    "check_messages": ["communication.read"],
    "prepare_message_reply": ["communication.read"],
    "send_message": ["communication.write"],
    "email_control": ["communication.read", "communication.write"],
    "reminder": ["system.read"],
    "youtube_video": ["multimedia.read", "network.read"],
    "media_control": ["multimedia.read", "multimedia.write"],
    "screen_process": ["vision.screen"],
    "computer_settings": ["windows.keyboard", "system.read"],
    "browser_control": ["browser.read", "browser.interact"],
    "file_controller": ["filesystem.read", "filesystem.write"],
    "desktop_control": ["windows.apps"],
    "code_helper": ["development.read", "development.write", "development.execute"],
    "dev_agent": ["development.read", "development.write", "development.execute"],
    "agent_task": ["development.read"],
    "computer_control": ["windows.keyboard", "windows.mouse"],
    "game_updater": ["windows.apps"],
    "flight_finder": ["network.read"],
    "graphics_quality": ["system.read"],
    "jarvis_ui_control": ["system.read"],
    "deep_research": ["network.read", "development.read"],
    "create_presentation": ["filesystem.write"],
    "task_status": ["system.read"],
    "file_processor": ["filesystem.read", "filesystem.write"],
    "save_memory": ["memory.write"],
    "local_memory_search": ["memory.read"],
    "lilith_memory_search": ["memory.read"],
    "lilith_memory_store": ["memory.write"],
    "lilith_memory_delete": ["memory.write"],
    "lilith_home_action": ["home.control"],
    "lilith_request_approval": ["system.read"],
    "lilith_resolve_approval": ["system.read"],
    "lilith_health": ["system.read"],
    "lilith_runtime_status": ["system.read"],
    "lilith_docs_list": ["system.read"],
    "lilith_docs_read": ["system.read"],
    "lilith_docs_search": ["system.read"],
    "lilith_source_list": ["development.read"],
    "lilith_source_read": ["development.read"],
    "lilith_source_search": ["development.read"],
    "lilith_git_status": ["development.read"],
    "lilith_command_submit": ["system.read"],
    "lilith_routine": ["home.control"],
    "open_capabilities_catalog": ["system.read"],
    "calculator": ["system.read"],
}

TOOL_SIDE_EFFECTS: dict[str, bool] = {
    "date_time": False,
    "open_app": True,
    "web_search": False,
    "weather_report": False,
    "check_messages": False,
    "prepare_message_reply": False,
    "send_message": True,
    "email_control": True,
    "reminder": True,
    "youtube_video": True,
    "media_control": True,
    "screen_process": False,
    "computer_settings": True,
    "browser_control": True,
    "file_controller": True,
    "desktop_control": True,
    "code_helper": True,
    "dev_agent": True,
    "agent_task": True,
    "computer_control": True,
    "game_updater": True,
    "flight_finder": False,
    "graphics_quality": True,
    "jarvis_ui_control": True,
    "deep_research": True,
    "create_presentation": True,
    "task_status": False,
    "file_processor": True,
    "save_memory": True,
    "local_memory_search": False,
    "lilith_memory_search": False,
    "lilith_memory_store": True,
    "lilith_memory_delete": True,
    "lilith_home_action": True,
    "lilith_request_approval": True,
    "lilith_resolve_approval": True,
    "lilith_health": False,
    "lilith_runtime_status": False,
    "lilith_docs_list": False,
    "lilith_docs_read": False,
    "lilith_docs_search": False,
    "lilith_source_list": False,
    "lilith_source_read": False,
    "lilith_source_search": False,
    "lilith_git_status": False,
    "lilith_command_submit": True,
    "lilith_routine": True,
    "open_capabilities_catalog": False,
    "calculator": False,
}


def enrich_registry_from_declarations(
    declarations: list[dict],
) -> "ToolRegistry":  # noqa: F821
    """Build a fully enriched ToolRegistry from TOOL_DECLARATIONS + metadata maps."""
    from core.green.tool_registry import ToolRegistry, ToolDefinition

    registry = ToolRegistry()
    for decl in declarations:
        name = decl.get("name", "")
        if not name:
            continue
        tool = ToolDefinition(
            name=name,
            description=decl.get("description", ""),
            schema=decl.get("parameters", {}),
            domain=TOOL_DOMAIN_MAP.get(name),
            capabilities=TOOL_CAPABILITIES_MAP.get(name, []),
            risk_level=TOOL_RISK_MAP.get(name, RiskLevel.LOW),
            side_effects=TOOL_SIDE_EFFECTS.get(name, False),
        )
        registry.register(tool)
    return registry


def check_parity(declarations: list[dict]) -> dict:
    """Compare TOOL_DECLARATIONS against metadata maps. Returns a report dict."""
    decl_names = {d["name"] for d in declarations if "name" in d}
    meta_names = set(TOOL_DOMAIN_MAP.keys())

    missing_in_meta = decl_names - meta_names
    extra_in_meta = meta_names - decl_names

    missing_risk = decl_names - set(TOOL_RISK_MAP.keys())
    missing_caps = decl_names - set(TOOL_CAPABILITIES_MAP.keys())
    missing_effects = decl_names - set(TOOL_SIDE_EFFECTS.keys())

    return {
        "declaration_count": len(decl_names),
        "metadata_count": len(meta_names),
        "parity": missing_in_meta == set() and extra_in_meta == set(),
        "missing_in_metadata": sorted(missing_in_meta),
        "extra_in_metadata": sorted(extra_in_meta),
        "missing_risk_mapping": sorted(missing_risk),
        "missing_capabilities_mapping": sorted(missing_caps),
        "missing_side_effects_mapping": sorted(missing_effects),
    }
