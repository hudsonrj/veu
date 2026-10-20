"""Roteador híbrido — OpenAI · DeepSeek · Claude · xAI · OpenRouter · HF · Ollama."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx

Provider = Literal[
    "ollama", "openai", "deepseek", "claude", "xai", "openrouter", "huggingface"
]


@dataclass
class LLMResult:
    provider: Provider
    model: str
    text: str
    ok: bool
    error: str | None = None
    # Assinatura de conta sem API key → handoff para o chat web do provedor
    handoff_url: str | None = None
    handoff_provider: str | None = None


class HybridLLM:
    """
    Política padrão:
    - classify / thinking → Ollama local (rápido)
    - chat / weave reply → OpenAI → Claude → xAI → OpenRouter → Ollama
    """

    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        """Recarrega chaves/modelos do ambiente (após conectar assinatura)."""
        self.openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.xai_key = os.environ.get("XAI_API_KEY", "").strip()
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        self.hf_token = (
            os.environ.get("HF_TOKEN", "").strip()
            or os.environ.get("HUGGINGFACE_HUB_TOKEN", "").strip()
            or os.environ.get("HUGGINGFACE_TOKEN", "").strip()
        )
        self.ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip(
            "/"
        )
        self.openai_model = os.environ.get("VEU_OPENAI_MODEL", "gpt-4.1-nano")
        self.deepseek_model = os.environ.get("VEU_DEEPSEEK_MODEL", "deepseek-chat")
        self.claude_model = os.environ.get("VEU_CLAUDE_MODEL", "claude-sonnet-4-5")
        self.xai_model = os.environ.get("VEU_XAI_MODEL", "grok-3-mini")
        self.openrouter_model = os.environ.get(
            "VEU_OPENROUTER_MODEL", "liquid/lfm-2.5-2.6b:free"
        )
        self.hf_model = os.environ.get(
            "VEU_HF_MODEL", "Qwen/Qwen2.5-7B-Instruct"
        )
        self.ollama_model = os.environ.get("VEU_OLLAMA_MODEL", "qwen3.5:0.8b")

    def pulse(self) -> dict[str, Any]:
        from veu.subscriptions import provider_available

        ollama_ok, ollama_models = self._ollama_tags()
        oa = provider_available("openai")
        cl = provider_available("claude")
        xa = provider_available("xai")
        return {
            "openai": oa["any"],
            "openai_model": self.openai_model,
            "openai_api_key": oa["api_key"],
            "openai_subscription": oa["subscription"],
            "deepseek": bool(self.deepseek_key),
            "deepseek_model": self.deepseek_model,
            "claude": cl["any"],
            "claude_model": self.claude_model,
            "claude_api_key": cl["api_key"],
            "claude_subscription": cl["subscription"],
            "xai": xa["any"],
            "xai_model": self.xai_model,
            "xai_api_key": xa["api_key"],
            "xai_subscription": xa["subscription"],
            "openrouter": bool(self.openrouter_key),
            "openrouter_model": self.openrouter_model,
            "huggingface": bool(self.hf_token),
            "huggingface_model": self.hf_model,
            "ollama": ollama_ok,
            "ollama_model": self.ollama_model,
            "ollama_models": ollama_models[:20],
            "subscriptions": {
                "openai": oa,
                "claude": cl,
                "xai": xa,
            },
        }

    @staticmethod
    def _sanitize_http_error(raw: str, *, provider: str) -> str:
        """Nunca devolve JSON cru da OpenAI/Claude/xAI pro chat."""
        low = (raw or "").lower()
        if "incorrect api key" in low or "invalid_api_key" in low or "invalid x-api-key" in low:
            return f"{provider}: API key inválida"
        if "insufficient_quota" in low or "billing" in low:
            return f"{provider}: cota/billing esgotada"
        if "rate_limit" in low or "429" in low:
            return f"{provider}: rate limit"
        # corta HTML/JSON longo
        clean = (raw or "").replace("\n", " ").strip()
        if clean.startswith("{") or "<html" in low:
            return f"{provider}: erro HTTP do provedor"
        return f"{provider}: {clean[:120]}"

    def _call_provider(self, provider: Provider, prompt: str, *, system: str) -> LLMResult:
        if provider == "ollama":
            # Modelo frio pode levar >8s; 60s evita cair no hint falso
            return self._ollama(prompt, system=system, timeout=60.0)
        if provider == "openai":
            if not self.openai_key or len(self.openai_key) < 40:
                raise RuntimeError("OPENAI_API_KEY ausente ou curta demais")
            return self._openai(prompt, system=system)
        if provider == "deepseek":
            if not self.deepseek_key:
                raise RuntimeError("DEEPSEEK_API_KEY ausente")
            return self._deepseek(prompt, system=system)
        if provider == "claude":
            if not self.anthropic_key:
                raise RuntimeError("ANTHROPIC_API_KEY ausente")
            return self._claude(prompt, system=system)
        if provider == "xai":
            if not self.xai_key:
                raise RuntimeError("XAI_API_KEY ausente")
            return self._xai(prompt, system=system)
        if provider == "openrouter":
            if not self.openrouter_key:
                raise RuntimeError("OPENROUTER_API_KEY ausente")
            return self._openrouter(prompt, system=system)
        if provider == "huggingface":
            if not self.hf_token:
                raise RuntimeError("HF_TOKEN ausente")
            return self._huggingface(prompt, system=system)
        raise RuntimeError(f"provedor desconhecido: {provider}")

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        purpose: str = "chat",
        prefer: Provider | None = None,
        force: Provider | None = None,
        allow_handoff: bool = False,
        fallback_local: bool = True,
    ) -> LLMResult:
        """Tenta provedores na ordem; `prefer` sobe na fila; `force` tenta esse primeiro.

        Por padrão NÃO devolve URL externa (conversa fica no Véu).
        Assinatura/browser NÃO é fallback — se a key falhar, cai pra outros
        provedores com key válida e depois Ollama local.
        """
        # Hard kill: nunca abrir ChatGPT/Claude/Grok em outra aba a partir do kernel
        _ = allow_handoff  # legado — ignorado

        labels = {
            "openai": "ChatGPT/OpenAI",
            "deepseek": "DeepSeek",
            "claude": "Claude",
            "xai": "Grok",
            "openrouter": "OpenRouter",
            "huggingface": "Hugging Face",
            "ollama": "Ollama",
        }

        if force:
            # Preferido primeiro; se falhar e fallback_local, cascata completa.
            # Sem key válida no force → pula direto pro Ollama (evita cascata lenta).
            order: list[Provider] = [force]
            if fallback_local:
                force_ready = True
                if force == "openai" and (not self.openai_key or len(self.openai_key) < 40):
                    force_ready = False
                elif force == "deepseek" and not self.deepseek_key:
                    force_ready = False
                elif force == "claude" and not self.anthropic_key:
                    force_ready = False
                elif force == "xai" and not self.xai_key:
                    force_ready = False
                elif force == "openrouter" and not self.openrouter_key:
                    force_ready = False
                elif force == "huggingface" and not self.hf_token:
                    force_ready = False
                if not force_ready:
                    order = ["ollama", force]
                else:
                    rest = [p for p in self._order_for(purpose) if p != force]
                    order = [force] + [p for p in rest if p != "ollama"] + ["ollama"]
                # dedupe preserving order
                seen: set[str] = set()
                deduped: list[Provider] = []
                for p in order:
                    if p in seen:
                        continue
                    seen.add(p)
                    deduped.append(p)
                order = deduped
        else:
            order = self._order_for(purpose)
            if prefer and prefer in order:
                order = [prefer] + [p for p in order if p != prefer]
            elif prefer:
                order = [prefer] + order

        errors: list[str] = []
        wanted = labels.get(force or prefer or "", "provedor")
        first = force or prefer

        for provider in order:
            try:
                result = self._call_provider(provider, prompt, system=system)
                if not result.ok or not (result.text or "").strip():
                    errors.append(f"{provider}: vazio")
                    continue
                # Se caiu de outro provedor, anota no rodapé (sem falar de assinatura)
                if first and provider != first:
                    note = (
                        f"(no Véu via {labels.get(provider, provider)} — "
                        f"{wanted} indisponível; key em Ajustes se quiser o original)"
                    )
                    return LLMResult(
                        provider=result.provider,
                        model=result.model,
                        text=f"{result.text.strip()}\n\n· {note}",
                        ok=True,
                        error="; ".join(errors) or None,
                    )
                return result
            except Exception as e:  # noqa: BLE001 — fallback chain
                errors.append(f"{provider}: {e}")
                continue

        err_short = (errors[0] if errors else "")[:180]
        if "Incorrect API key" in err_short or "invalid_api_key" in err_short:
            hint = (
                f"A API key de {wanted} foi rejeitada e nenhum outro modelo "
                "respondeu (Claude/Grok/Ollama). Cole uma key válida em "
                "Ajustes → assinaturas — a conversa fica aqui no Véu, "
                "sem precisar de assinatura/browser."
            )
        elif not err_short or "ausente" in err_short or "nenhum" in err_short:
            hint = (
                f"Pra falar com {wanted} aqui no Véu, cole a API key em "
                "Ajustes → assinaturas (ou ligue Ollama local). "
                "Assinatura sozinha não responde dentro do SO."
            )
        else:
            hint = (
                f"Nenhum modelo respondeu aqui no Véu agora. "
                f"({err_short}) Ajuste a key em Ajustes ou suba o Ollama."
            )
        return LLMResult(
            provider=force or prefer or "ollama",  # type: ignore[arg-type]
            model="in-veu",
            text=hint,
            ok=True,
            error="; ".join(errors) or "nenhum provedor disponível",
        )

    def decide(self, purpose: str = "chat") -> dict[str, Any]:
        """Quem assume agora — primeiro provedor usable na ordem."""
        from veu.subscriptions import provider_available

        order = self._order_for(purpose)
        for provider in order:
            if provider == "ollama":
                ok, _ = self._ollama_tags()
                if ok:
                    return {
                        "provider": provider,
                        "model": self.ollama_model,
                        "mode": "local",
                        "label": "Ollama",
                    }
            elif provider == "openai":
                avail = provider_available("openai")
                if avail["api_key"]:
                    return {
                        "provider": "openai",
                        "model": self.openai_model,
                        "mode": "api_key",
                        "label": "ChatGPT",
                    }
                if avail["subscription"]:
                    return {
                        "provider": "openai",
                        "model": "subscription:ChatGPT",
                        "mode": "subscription",
                        "label": "ChatGPT",
                        "url": "https://chatgpt.com/",
                    }
            elif provider == "claude":
                avail = provider_available("claude")
                if avail["api_key"]:
                    return {
                        "provider": "claude",
                        "model": self.claude_model,
                        "mode": "api_key",
                        "label": "Claude",
                    }
                if avail["subscription"]:
                    return {
                        "provider": "claude",
                        "model": "subscription:Claude.ai",
                        "mode": "subscription",
                        "label": "Claude",
                        "url": "https://claude.ai/new",
                    }
            elif provider == "xai":
                avail = provider_available("xai")
                if avail["api_key"]:
                    return {
                        "provider": "xai",
                        "model": self.xai_model,
                        "mode": "api_key",
                        "label": "Grok",
                    }
                if avail["subscription"]:
                    return {
                        "provider": "xai",
                        "model": "subscription:Grok",
                        "mode": "subscription",
                        "label": "Grok",
                        "url": "https://grok.com/",
                    }
            elif provider == "deepseek" and self.deepseek_key:
                return {
                    "provider": "deepseek",
                    "model": self.deepseek_model,
                    "mode": "api_key",
                    "label": "DeepSeek",
                }
            elif provider == "openrouter" and self.openrouter_key:
                return {
                    "provider": "openrouter",
                    "model": self.openrouter_model,
                    "mode": "api_key",
                    "label": "OpenRouter",
                }
            elif provider == "huggingface" and self.hf_token:
                return {
                    "provider": "huggingface",
                    "model": self.hf_model,
                    "mode": "api_key",
                    "label": "Hugging Face",
                }
        return {"provider": None, "model": None, "mode": "none", "label": "nenhum"}

    def _subscription_handoff(self, provider: str, prompt: str) -> LLMResult:
        """Conta ligada sem API key — abre o chat web da assinatura com o pedido."""
        from urllib.parse import quote

        from veu.subscriptions import PROVIDERS

        meta = PROVIDERS[provider]  # type: ignore[index]
        # URLs de compose quando o produto aceita; senão só abre o app logado
        if provider == "openai":
            url = f"https://chatgpt.com/?q={quote(prompt[:1200])}"
        elif provider == "claude":
            url = f"https://claude.ai/new?q={quote(prompt[:800])}" if prompt else "https://claude.ai/new"
        else:
            url = "https://grok.com/"
        text = (
            f"Sua assinatura {meta['name']} ({meta['product']}) está ligada. "
            f"Abro o chat da assinatura pra você continuar o pedido."
        )
        return LLMResult(
            provider=provider,  # type: ignore[arg-type]
            model=f"subscription:{meta['product']}",
            text=text,
            ok=True,
            handoff_url=url,
            handoff_provider=provider,
        )

    def _order_for(self, purpose: str) -> list[Provider]:
        if purpose in {"classify", "thinking", "local"}:
            return [
                "ollama",
                "openai",
                "deepseek",
                "huggingface",
                "claude",
                "xai",
                "openrouter",
            ]
        return [
            "openai",
            "deepseek",
            "huggingface",
            "claude",
            "xai",
            "openrouter",
            "ollama",
        ]

    def _ollama_tags(self) -> tuple[bool, list[str]]:
        try:
            with httpx.Client(timeout=3.0) as client:
                r = client.get(f"{self.ollama_base}/api/tags")
                if r.status_code >= 400:
                    return False, []
                names = [m.get("name", "") for m in r.json().get("models", [])]
                return True, names
        except Exception:  # noqa: BLE001
            return False, []

    def _ollama(self, prompt: str, *, system: str, timeout: float = 45.0) -> LLMResult:
        body: dict[str, Any] = {
            "model": self.ollama_model,
            "stream": False,
            "prompt": prompt if not system else f"{system}\n\n{prompt}",
            "options": {"num_predict": 280, "temperature": 0.4},
        }
        with httpx.Client(timeout=timeout) as client:
            r = client.post(f"{self.ollama_base}/api/generate", json=body)
            r.raise_for_status()
            data = r.json()
            text = (data.get("response") or "").strip()
            if not text:
                raise RuntimeError("resposta vazia do Ollama")
            return LLMResult(provider="ollama", model=self.ollama_model, text=text, ok=True)

    def _openai_compat(
        self,
        *,
        provider: Provider,
        base_url: str,
        key: str,
        model: str,
        prompt: str,
        system: str,
        extra_headers: dict[str, str] | None = None,
    ) -> LLMResult:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.4,
                    "max_tokens": 800,
                },
            )
            if r.status_code >= 400:
                raise RuntimeError(self._sanitize_http_error(r.text[:400], provider=provider))
            data = r.json()
            text = data["choices"][0]["message"]["content"].strip()
            try:
                from veu import usage as veu_usage

                u = data.get("usage") or {}
                veu_usage.record(
                    provider=provider,
                    model=model,
                    tokens_in=int(u.get("prompt_tokens") or 0),
                    tokens_out=int(u.get("completion_tokens") or 0),
                    agent="llm",
                )
            except Exception:  # noqa: BLE001
                pass
            return LLMResult(provider=provider, model=model, text=text, ok=True)

    def _openai(self, prompt: str, *, system: str) -> LLMResult:
        if not self.openai_key:
            raise RuntimeError("OPENAI_API_KEY ausente")
        return self._openai_compat(
            provider="openai",
            base_url="https://api.openai.com/v1",
            key=self.openai_key,
            model=self.openai_model,
            prompt=prompt,
            system=system,
        )

    def _deepseek(self, prompt: str, *, system: str) -> LLMResult:
        if not self.deepseek_key:
            raise RuntimeError("DEEPSEEK_API_KEY ausente")
        return self._openai_compat(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            key=self.deepseek_key,
            model=self.deepseek_model,
            prompt=prompt,
            system=system,
        )

    def _huggingface(self, prompt: str, *, system: str) -> LLMResult:
        if not self.hf_token:
            raise RuntimeError("HF_TOKEN ausente")
        return self._openai_compat(
            provider="huggingface",
            base_url="https://router.huggingface.co/v1",
            key=self.hf_token,
            model=self.hf_model,
            prompt=prompt,
            system=system,
        )

    def _claude(self, prompt: str, *, system: str) -> LLMResult:
        if not self.anthropic_key:
            raise RuntimeError("ANTHROPIC_API_KEY ausente")
        body: dict[str, Any] = {
            "model": self.claude_model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        with httpx.Client(timeout=20.0) as client:
            r = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )
            if r.status_code >= 400:
                raise RuntimeError(self._sanitize_http_error(r.text[:400], provider="claude"))
            data = r.json()
            parts = data.get("content") or []
            text = "".join(
                p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"
            ).strip()
            if not text:
                raise RuntimeError("resposta vazia do Claude")
            try:
                from veu import usage as veu_usage

                u = data.get("usage") or {}
                tin = int(u.get("input_tokens") or 0)
                tout = int(u.get("output_tokens") or 0)
                veu_usage.record(
                    provider="claude",
                    model=self.claude_model,
                    tokens_in=tin,
                    tokens_out=tout,
                    agent="llm",
                )
            except Exception:  # noqa: BLE001
                pass
            return LLMResult(provider="claude", model=self.claude_model, text=text, ok=True)

    def _xai(self, prompt: str, *, system: str) -> LLMResult:
        if not self.xai_key:
            raise RuntimeError("XAI_API_KEY ausente")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        with httpx.Client(timeout=20.0) as client:
            r = client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.xai_key}"},
                json={
                    "model": self.xai_model,
                    "messages": messages,
                    "temperature": 0.4,
                    "max_tokens": 800,
                },
            )
            if r.status_code >= 400:
                raise RuntimeError(self._sanitize_http_error(r.text[:400], provider="xai"))
            data = r.json()
            text = data["choices"][0]["message"]["content"].strip()
            try:
                from veu import usage as veu_usage

                u = data.get("usage") or {}
                veu_usage.record(
                    provider="xai",
                    model=self.xai_model,
                    tokens_in=int(u.get("prompt_tokens") or 0),
                    tokens_out=int(u.get("completion_tokens") or 0),
                    agent="llm",
                )
            except Exception:  # noqa: BLE001
                pass
            return LLMResult(provider="xai", model=self.xai_model, text=text, ok=True)

    def _openrouter(self, prompt: str, *, system: str) -> LLMResult:
        if not self.openrouter_key:
            raise RuntimeError("OPENROUTER_API_KEY ausente")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        with httpx.Client(timeout=20.0) as client:
            r = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "HTTP-Referer": "https://veu.ch8ai.com.br",
                    "X-Title": "Véu",
                },
                json={
                    "model": self.openrouter_model,
                    "messages": messages,
                    "temperature": 0.4,
                    "max_tokens": 800,
                },
            )
            if r.status_code >= 400:
                raise RuntimeError(r.text[:300])
            data = r.json()
            text = data["choices"][0]["message"]["content"].strip()
            try:
                from veu import usage as veu_usage

                u = data.get("usage") or {}
                veu_usage.record(
                    provider="openrouter",
                    model=self.openrouter_model,
                    tokens_in=int(u.get("prompt_tokens") or 0),
                    tokens_out=int(u.get("completion_tokens") or 0),
                    agent="llm",
                )
            except Exception:  # noqa: BLE001
                pass
            return LLMResult(
                provider="openrouter", model=self.openrouter_model, text=text, ok=True
            )


SYSTEM_OS = """Você é o Véu — administrador de IA de um sistema operacional vivo.
Fale em português do Brasil, direto, humano, como um colega.
Respostas curtas. Sem markdown excessivo. Sem emojis a menos que peçam.

NUNCA diga ao usuário: híbrido, formação, barramento, nervo, weave, kernel,
respiração, ECC, connector, adapter, System One, ou jargão interno de engenharia.
Isso é interno. Para o humano, fale de ajudar, fazer, checar, enviar, abrir.

Se for só um cumprimento (oi, olá), responda de forma natural e pergunte no que ajudar.
Não invente que já executou algo. Se precisar de permissão ou token, diga claro.
Não mencione qual modelo ou provedor você está usando."""
