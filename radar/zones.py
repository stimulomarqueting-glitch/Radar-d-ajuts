"""Jerarquia geogràfica per saber a quins clients es pot enviar cada oportunitat.

Cada zona té un pare (p. ex. ES-CT-BCN -> ES-CT-AMB -> ES-CT-B -> ES-CT -> ES -> EU -> INT).
Una convocatòria declara les zones on ha d'estar establert el beneficiari; un client
hi és elegible si alguna d'aquestes zones és ell mateix o un avantpassat de la seva zona.
"""

from __future__ import annotations


class Zones:
    def __init__(self, definicions: dict[str, dict]):
        self.definicions = definicions
        for codi, d in definicions.items():
            pare = d.get("pare")
            if pare is not None and pare not in definicions:
                raise ValueError(f"Zona {codi}: pare desconegut {pare}")

    def nom(self, codi: str) -> str:
        return self.definicions.get(codi, {}).get("nom", codi)

    def existeix(self, codi: str) -> bool:
        return codi in self.definicions

    def avantpassats(self, codi: str) -> list[str]:
        """Retorna [codi, pare, avi, ...] fins a l'arrel."""
        cami = []
        actual = codi
        while actual is not None:
            if actual in cami:
                raise ValueError(f"Cicle a la jerarquia de zones: {cami}")
            cami.append(actual)
            actual = self.definicions.get(actual, {}).get("pare")
        return cami

    def es_elegible(self, zona_client: str, zones_convocatoria: list[str]) -> bool:
        if not zones_convocatoria:
            return True
        cami = set(self.avantpassats(zona_client))
        return any(z in cami for z in zones_convocatoria)

    def etiqueta(self, zones_convocatoria: list[str]) -> str:
        if not zones_convocatoria:
            return "Sense restricció"
        return " · ".join(self.nom(z) for z in zones_convocatoria)
