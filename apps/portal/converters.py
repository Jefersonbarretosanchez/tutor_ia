"""Convertidor de URL: muestra slugs en español (/portal/cursos/) y entrega la clave interna del recurso."""

SLUGS = {
    "courses": "cursos",
    "gates": "paginas-bloqueadas",
    "default_gates": "bloqueos-por-defecto",
    "students": "estudiantes",
    "ledger": "registro-de-tokens",
    "launch_logs": "lanzamientos-lti",
    "audit": "auditoria",
}
_BY_SLUG = {v: k for k, v in SLUGS.items()}


class ResourceConverter:
    regex = "|".join(SLUGS.values())

    def to_python(self, value):
        return _BY_SLUG[value]

    def to_url(self, value):
        return SLUGS[value]
