"""
Corrige el número de curso "quemado" en los embeds del chat.

Cuando se inserta el chat de Clara en una página vía "Apps" en el editor de
Canvas, queda un iframe tipo:

    <iframe src="https://.../courses/104/external_tools/retrieve?...">

Ese "104" no se actualiza solo cuando la página se duplica a otro curso —
es un límite conocido de Canvas con links internos incrustados en el cuerpo
de una página. Este comando recorre las páginas del curso indicado y
corrige cualquier "/courses/<id>/external_tools/retrieve" que no coincida
con el `canvas_course_id` real de ese curso.

Por defecto corre en modo simulación (no escribe nada) — usar --apply para
aplicar los cambios.

Uso:
    python manage.py fix_retrieve_course_ids <course_pk>
    python manage.py fix_retrieve_course_ids <course_pk> --apply
"""

from django.core.management.base import BaseCommand, CommandError

from apps.chat.services import canvas_pages
from apps.lti_tool.models import Course


class Command(BaseCommand):
    help = "Corrige el course_id incrustado en los embeds 'external_tools/retrieve' de las páginas de un curso."

    def add_arguments(self, parser):
        parser.add_argument("course_pk", type=int, help="PK del Course en Django (no el canvas_course_id).")
        parser.add_argument("--apply", action="store_true", help="Aplica los cambios (por defecto solo simula).")

    def handle(self, *args, **options):
        try:
            course = Course.objects.get(pk=options["course_pk"])
        except Course.DoesNotExist as exc:
            raise CommandError(f"No existe un Course con pk={options['course_pk']}.") from exc

        if not course.canvas_course_id:
            raise CommandError(f"{course} no tiene canvas_course_id — no se puede determinar el valor correcto.")

        self.stdout.write(f"Curso: {course}  (canvas_course_id={course.canvas_course_id})")

        page_urls = canvas_pages.list_page_urls(course)
        self.stdout.write(f"{len(page_urls)} página(s) encontradas. Revisando...")

        fixed, skipped = 0, 0
        for page_url in page_urls:
            new_body = canvas_pages.find_stale_retrieve_urls(course, page_url)
            if new_body is None:
                continue

            if options["apply"]:
                canvas_pages.update_page_body(course, page_url, new_body)
                self.stdout.write(self.style.SUCCESS(f"  [corregida] {page_url}"))
                fixed += 1
            else:
                self.stdout.write(self.style.WARNING(f"  [pendiente] {page_url} — correría con --apply"))
                skipped += 1

        if options["apply"]:
            self.stdout.write(self.style.SUCCESS(f"Listo: {fixed} página(s) corregida(s)."))
        else:
            self.stdout.write(f"Simulación: {skipped} página(s) se corregirían con --apply.")
