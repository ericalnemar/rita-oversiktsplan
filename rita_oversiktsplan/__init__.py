"""Rita Översiktsplan – QGIS-plugin för att rita översiktsplaner enligt Boverkets ÖP-modell och nationell specifikation."""


def classFactory(iface):  # noqa: N802 - namnet krävs av QGIS
    from .plugin import OversiktsplanPlugin

    return OversiktsplanPlugin(iface)
