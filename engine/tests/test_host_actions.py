"""Planner chat → host local."""

from veu.host_actions import plan_host_actions, wants_host


def test_read_email_focus_and_scrape():
    r = plan_host_actions("leia meu email", breath="semi")
    types = [a["type"] for a in r["actions"]]
    assert wants_host("leia meu email")
    assert "focus_app" in types
    assert "read_surface" in types
    assert any(a.get("app") == "gmail" for a in r["actions"])


def test_read_whatsapp():
    r = plan_host_actions("leia as mensagens do whatsapp")
    assert any(a.get("type") == "read_surface" and a.get("app") == "whatsapp" for a in r["actions"])


def test_list_open():
    r = plan_host_actions("o que está aberto no pc")
    types = [a["type"] for a in r["actions"]]
    assert "list_tabs" in types
    assert any(a.get("preset") == "apps-open" for a in r["actions"])


def test_open_apps():
    r = plan_host_actions("abra o gmail e o notion")
    apps = [a.get("app") for a in r["actions"] if a.get("type") == "focus_app"]
    assert "gmail" in apps and "notion" in apps
