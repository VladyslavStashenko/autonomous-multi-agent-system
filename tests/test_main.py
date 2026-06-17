from __future__ import annotations

from types import SimpleNamespace

import main as main_module
from config import Settings


def test_main_keeps_auto_mode_selected_after_routed_run(monkeypatch) -> None:
    saved_sessions: list[dict] = []
    pipeline_calls: list[dict] = []
    inputs = iter(["Порахуй рядки у файлі test.py", "exit"])

    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "init", lambda autoreset=False: None)
    monkeypatch.setattr(main_module, "get_settings", lambda: Settings(api_key="x", api_keys=["x"], model="m", max_agent_steps=15))
    monkeypatch.setattr(main_module, "ClientPool", lambda keys: SimpleNamespace(get_client=lambda: None))
    monkeypatch.setattr(main_module, "load_session", lambda: {"agent_type": "auto", "theme": "cyan", "mode": "technical"})
    monkeypatch.setattr(main_module, "get_effective_settings", lambda settings, overrides: settings)
    monkeypatch.setattr(main_module, "clear_screen", lambda: None)
    monkeypatch.setattr(main_module, "print_logo", lambda model, theme: None)
    monkeypatch.setattr(main_module, "framed_input", lambda style: next(inputs))
    monkeypatch.setattr(main_module, "build_prompt_style", lambda theme: None)
    monkeypatch.setattr(main_module, "is_conversational", lambda text: False)
    monkeypatch.setattr(
        main_module,
        "resolve_agent_type",
        lambda selected, task: {
            "selected_agent_type": selected,
            "effective_agent_type": "single",
            "routing_applied": True,
            "score": 1,
            "threshold": 4,
            "reasons": ["simple local action"],
        },
    )
    monkeypatch.setattr(
        main_module,
        "run_pipeline",
        lambda task, theme, mode, settings, agent_type, pool, selected_agent_type=None, routing_info=None: pipeline_calls.append(
            {
                "task": task,
                "agent_type": agent_type,
                "selected_agent_type": selected_agent_type,
                "routing_info": routing_info,
            }
        ),
    )
    monkeypatch.setattr(main_module, "save_session", lambda session: saved_sessions.append(session))

    main_module.main()

    assert pipeline_calls[0]["agent_type"] == "single"
    assert pipeline_calls[0]["selected_agent_type"] == "auto"
    assert saved_sessions[-1]["agent_type"] == "auto"
