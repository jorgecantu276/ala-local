# Verificación de la versión base

Revisión realizada el 30 de octubre de 2026.

- 20 pruebas automatizadas de backend, API, concurrencia, exportaciones y restauración: correctas.
- Comprobación de sintaxis de JavaScript del navegador y exportador: correcta.
- Revisión manual en navegador: agenda, creación de reserva y rechazo de un segundo vuelo en el mismo horario.
- PDF de prueba renderizado y revisado visualmente.
- PPTX de prueba importado con el renderizador de Artifact Tool y sus tres diapositivas revisadas visualmente. No se abrió en Microsoft PowerPoint.
- Dependencias npm revisadas con `npm audit --omit=dev --audit-level=high`: sin vulnerabilidades reportadas en la versión revisada.
- Inicio del servidor local verificado en Windows. La instalación limpia en otra computadora y la apariencia en PowerPoint del destinatario quedan para la recepción.

PptxGenJS 4.0.1 declara una dependencia antigua de `image-size`. Se fija una sustitución a 2.0.4, y el flujo de exportación sin imágenes queda cubierto por una prueba de integración.

Los ejemplos de verificación usan bases temporales. No se incluyen sus datos ni sus reportes en Git.
