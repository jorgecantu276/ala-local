# Entrega del producto base

## Objetivo confirmado

Coordinar el uso exclusivo de una aeronave por dos personas. Ambas usan una sola computadora. Ningún viaje puede compartir el intervalo de uso de la aeronave con otra reserva. Exportar y conservar resúmenes de la agenda.

## Primera sesión con el usuario

1. Instalar y abrir la aplicación según README.
2. Configurar los dos nombres, matrícula, base, zona horaria y margen entre usos.
3. Crear una reserva tentativa con inicio de uso y regreso.
4. Intentar otra reserva que se cruce y comprobar el rechazo.
5. Confirmar la primera, exportar PDF y PPTX, y descargar un respaldo.
6. Cerrar y volver a abrir para comprobar la persistencia.

No se incluyen datos reales ni reservas de demostración en el repositorio.

## Criterios de aceptación

- Solo hay una aeronave y dos titulares.
- Cada viaje tiene un titular y un intervalo válido.
- El servidor rechaza cruces, incluidos los de mantenimiento y reservas tentativas.
- Dos guardados simultáneos del mismo periodo producen una sola reserva.
- Cancelar libera el intervalo y conserva la reserva.
- Cambios desde otra ventana producen un aviso de versión en vez de perder información.
- PDF y PPTX se crean sin acceso a servicios externos y contienen el periodo y zona horaria.
- El respaldo conserva configuración, reservas e historial y se puede restaurar.
- Al reiniciar, la agenda conserva los datos.

## Decisiones pendientes para la siguiente fase

- Nombres y datos definitivos de la aeronave.
- Si la confirmación requiere una aprobación distinta a quien crea la reserva.
- Si se necesitan vuelos de posicionamiento, varios tramos o reglas de ubicación entre viajes.
- Si hace falta registrar pasajeros, costos, horas de vuelo o documentos adjuntos.
- Plantilla corporativa para los reportes y presentaciones.

## Evolución a SaaS

Esta entrega es una aplicación local. Para un servicio alojado con cuentas: definir la organización y los permisos, incorporar autenticación, API de producción, sesiones y protección CSRF, aislamiento de organizaciones, almacenamiento compartido, migraciones, respaldos automáticos, monitoreo y despliegue. Migrar primero los contratos y las reglas de exclusividad con pruebas de concurrencia.

El servidor HTTP estándar de Python y las identidades por índice resuelven el alcance local. No deben tomarse como base de autenticación o servidor de internet.

## Verificación técnica

Ejecutar las pruebas del README. La comprobación de PDF usa `pypdf` para validar contenido y las comprobaciones de PPTX inspeccionan el paquete OOXML. La revisión visual de una exportación no reemplaza probarla en la versión de PowerPoint del destinatario.

## GitHub y privacidad

El repositorio contiene código, dependencias declaradas, documentación, pruebas y configuración de CI. Los datos de agenda, logs, entornos locales, paquetes instalados y archivos exportados quedan fuera de Git. La sincronización es por commits y pushes, no automática tras cada edición. Revisar `git status` antes de cada entrega.
