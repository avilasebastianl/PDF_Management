# PDF Management - Guia de uso

## Unir

Use esta seccion para crear un solo PDF a partir de varios archivos.

1. Presione **Agregar PDFs** o arrastre archivos PDF a la lista.
2. Ordene los archivos con los botones **^** y **v**.
3. Elija el archivo de salida.
4. Presione **Unir PDFs**.

Ejemplo: si agrega `parte_1.pdf`, `parte_2.pdf` y `parte_3.pdf`, el PDF final conserva el orden visible en la lista.

## Extraer

Use esta seccion para crear un nuevo PDF con paginas especificas de un archivo existente.

1. Seleccione el PDF origen.
2. Escriba las paginas que desea extraer.
3. Si el PDF origen tiene contrasena, escribala en **Clave PDF origen**. Si no la escribe, la aplicacion la pedira cuando sea necesaria.
4. Si desea proteger el PDF generado, escriba una nueva contrasena en **Clave PDF final**.
5. Elija el archivo de salida.
6. Presione **Crear PDF**.

Ejemplos de paginas:

- `2,4,7,9`: extrae solo esas paginas.
- `1-3,8,10`: extrae un rango y paginas individuales.
- `all`: extrae todas las paginas.
- `odd`: extrae paginas impares.
- `even`: extrae paginas pares.

## Convertir

Use esta seccion para convertir archivos de Office a PDF.

Formatos admitidos:

- `.docx`
- `.xlsx`

Seleccione el archivo de origen, el destino del PDF y presione **Convertir**.

## Firmar

Use esta seccion para agregar una firma visual desde una imagen.

1. Seleccione el PDF a firmar.
2. Seleccione o cree una imagen de firma.
3. Use el visor para ubicar la firma. Puede ir a la primera, anterior, siguiente o ultima pagina.
4. Haga clic sobre el punto donde desea colocarla.
5. Ajuste el zoom con **-**, **+** o **Reiniciar vista** si necesita precision.
6. Active **Firmar todas las hojas** si desea poner la firma en la misma posicion en todo el documento.
7. Presione **Firmar**.

Las firmas creadas o adjuntadas se guardan en la carpeta `signs`. Puede seleccionar **Sin imagen** para limpiar la seleccion o borrar una firma guardada desde el boton **Borrar**.

## Proteger

Use esta seccion para bloquear o desbloquear PDFs.

- **Bloquear**: genera un PDF protegido con la contrasena indicada.
- **Desbloquear**: genera una copia sin proteccion, siempre que conozca la contrasena actual.

## Ajustes

Use esta seccion para cambiar:

- Ancho de ventana.
- Alto de ventana.
- Tema visual.
- Color de tema.
- Escala de la interfaz.
- Pestaña inicial.
- Abrir automaticamente el archivo generado al guardar.

Al aplicar cambios, la aplicacion preguntara si desea reiniciar para tomarlos inmediatamente.

## Ayuda

El boton **Ayuda** abre esta guia dentro de la aplicacion con formato legible.

## Procesamiento

Las operaciones de unir, extraer, convertir, firmar y proteger se ejecutan en
segundo plano. Puede seguir navegando por la aplicacion mientras el indicador
de actividad de la parte inferior muestra que hay un archivo en proceso.

## Seguridad

La aplicacion no intenta descubrir contrasenas desconocidas. Para desbloquear o extraer contenido de PDFs protegidos debe conocer la contrasena.
