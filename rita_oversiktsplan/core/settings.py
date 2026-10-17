"""Pluginets inställningar (sparas i QGIS användarprofil): leveransen till NGP. Från Rita Detaljplan, med egna
nycklar så att de två pluginen inte delar inställningar av misstag."""
from __future__ import annotations

from qgis.core import QgsApplication, QgsSettings

KEY_NGP = "rita_oversiktsplan/ngp/"


def ngp_config():
    """Inställningarna för leverans till NGP (miljö, adresser, autentiseringskonfiguration)."""
    from . import ngp_client as ngp
    store = QgsSettings()
    environment = str(store.value(KEY_NGP + "environment", "ver"))
    defaults = ngp.ENVIRONMENTS.get(environment)
    if defaults is None:
        environment = "egen"
    base = str(store.value(KEY_NGP + "base_url", defaults.base_url if defaults else "") or "")
    token = str(store.value(KEY_NGP + "token_url", defaults.token_url if defaults else "") or "")
    return ngp.NgpConfig(environment=environment, base_url=base, token_url=token,
                         authcfg=str(store.value(KEY_NGP + "authcfg", "") or ""))


def set_ngp_config(config) -> None:
    store = QgsSettings()
    store.setValue(KEY_NGP + "environment", config.environment)
    store.setValue(KEY_NGP + "base_url", config.base_url.strip())
    store.setValue(KEY_NGP + "token_url", config.token_url.strip())
    store.setValue(KEY_NGP + "authcfg", config.authcfg)


def auth_configs() -> list[tuple[str, str]]:
    """QGIS autentiseringskonfigurationer som (id, namn). Tom lista om autentiseringsdatabasen inte kan läsas."""
    try:
        configs = QgsApplication.authManager().availableAuthMethodConfigs()
        return sorted(((cid, cfg.name()) for cid, cfg in configs.items()), key=lambda item: item[1].lower())
    except Exception:  # noqa: BLE001 - till exempel låst databas
        return []
