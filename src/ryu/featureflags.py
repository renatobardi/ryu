"""Feature flags do Ryu — port funcional de server/pkg/featureflag do multica.

Cadeia de providers (precedência: env > defaults em código):
- Env: FF_<KEY>=true|false|42%|<variant> (KEY em UPPER_SNAKE do nome da flag).
- Defaults em código (DEFAULT_FLAGS).

Percent rollout: hash determinístico (sha256) de "key:subject" → bucket 0..99;
o mesmo user/workspace cai sempre no mesmo lado do rollout (multica hash.go).

Uso server-side (Toggle Point):
    from ryu.featureflags import flags
    if flags.is_enabled("usage_hourly_heatmap", subject=user.id, default=True): ...

Flags públicas vão ao frontend via GET /api/auth/config e /api/config
(equivalente a EvaluateFrontendPublicFlags do multica).
"""
from __future__ import annotations

import hashlib
import os

# defaults em código (multica server/internal/featureflags/keys.go)
DEFAULT_FLAGS: dict[str, str] = {
    # namespaces de labels por recurso (agent/skill) — ryu já implementa; on.
    "settings_resource_labels": "true",
    # heatmap horário da página de usage (gate demonstrativo deste ciclo)
    "usage_hourly_heatmap": "true",
}

# compat permanente (multica: chaves que deixaram de ser release flags mas
# continuam publicadas como enabled p/ clientes antigos)
_ALWAYS_ON_COMPAT = ("agents_agent_builder", "agents_skill_toggles")

# flags expostas ao frontend (frontendPublicFlags)
FRONTEND_PUBLIC_FLAGS = ("settings_resource_labels", "usage_hourly_heatmap")

_TRUE_VARIANTS = ("true", "on", "enabled", "1", "yes")
_FALSE_VARIANTS = ("false", "off", "disabled", "0", "no")


def _percent_bucket(key: str, subject: str) -> int:
    """Bucket determinístico 0..99 por (flag, sujeito) — multica hash.go."""
    digest = hashlib.sha256(f"{key}:{subject}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % 100


def _parse_value(raw: str) -> dict:
    """'true' | 'false' | '42%' | '<variant>' → decisão normalizada."""
    v = (raw or "").strip()
    if v.endswith("%"):
        try:
            pct = max(0, min(100, int(v[:-1])))
        except ValueError:
            return {"variant": "false"}
        return {"percent": pct}
    return {"variant": v or "false"}


class FeatureFlagService:
    # ── Providers ─────────────────────────────────────────────────────
    def _env_lookup(self, key: str) -> dict | None:
        raw = os.environ.get(f"FF_{key.upper()}")
        if raw is None or raw.strip() == "":
            return None
        return _parse_value(raw)

    # ── Avaliação ─────────────────────────────────────────────────────
    def decision(self, key: str, *, subject: str = "", default: bool = False) -> dict:
        """Decisão estruturada: {enabled, variant, source, reason}."""
        entry = self._env_lookup(key)
        source = "env"
        if entry is None:
            if key in DEFAULT_FLAGS:
                entry = _parse_value(DEFAULT_FLAGS[key])
                source = "default"
            else:
                return {
                    "enabled": default,
                    "variant": "true" if default else "false",
                    "source": "fallback",
                    "reason": "missing",
                }
        subj = subject or "global"
        if "percent" in entry:
            on = _percent_bucket(key, subj) < entry["percent"]
            return {
                "enabled": on,
                "variant": "true" if on else "false",
                "source": source,
                "reason": f"percent:{entry['percent']}",
            }
        variant = str(entry.get("variant", "false"))
        if variant.lower() in _TRUE_VARIANTS:
            enabled = True
        elif variant.lower() in _FALSE_VARIANTS:
            enabled = False
        else:
            enabled = True  # variant nomeada (A/B) conta como on
        return {"enabled": enabled, "variant": variant, "source": source, "reason": "static"}

    def is_enabled(self, key: str, *, subject: str = "", default: bool = False) -> bool:
        return self.decision(key, subject=subject, default=default)["enabled"]

    def variant(self, key: str, *, subject: str = "", default: str = "false") -> str:
        d = self.decision(key, subject=subject, default=default.lower() in _TRUE_VARIANTS)
        return d["variant"] if d["reason"] != "missing" else default

    def evaluate_frontend_public_flags(self, *, subject: str = "") -> dict[str, bool]:
        """Mapa de flags públicas p/ o frontend (EvaluateFrontendPublicFlags)."""
        out = {key: self.is_enabled(key, subject=subject, default=False) for key in FRONTEND_PUBLIC_FLAGS}
        for key in _ALWAYS_ON_COMPAT:
            out[key] = True
        return out


flags = FeatureFlagService()
