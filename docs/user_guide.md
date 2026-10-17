# PDF Management - Guia de uso

Navegue entre secciones con la barra lateral o con **Ctrl+1** a **Ctrl+6**. Pulse **F1** para abrir esta guia.

En casi todos los campos de archivo puede **arrastrar** el archivo desde el explorador.

La **barra de estado** (parte inferior) indica que esta haciendo la aplicacion: un punto gris significa *listo*, la barra animada una operacion *en curso* (con las que esperan en cola), el punto verde el *ultimo archivo generado* con los botones **Mostrar en carpeta** y **Abrir**, y el rojo que la ultima operacion *no se completo*. Pase el cursor sobre ella para ver el detalle. Puede seguir trabajando mientras una operacion esta en curso.

La aplicacion nunca sobrescribe un archivo sin preguntar: si el nombre de salida sugerido ya existe, elige automaticamente uno libre, por ejemplo `informe_firmado (2).pdf`.

## Unir

Combine varios PDFs en uno solo.

1. Presione **Agregar PDFs** o arrastre archivos (o carpetas completas) a la lista.
2. Ordenelos con las flechas de cada fila o con **Ordenar A-Z**.
3. Opcional: active **Crear un marcador por cada archivo** para navegar el resultado por documento.
4. Revise **Guardar como** y presione **Unir PDFs**.

Si algun PDF esta protegido, la aplicacion pedira su contrasena.

## Extraer

Genere un PDF nuevo con solo algunas paginas, en el orden que indique.

1. Seleccione el **PDF** de origen. Vera su numero de paginas.
2. Escriba la **Seleccion** (las paginas empiezan en 1). Debajo vera cuantas paginas se extraeran.
3. Opcional: contrasena del PDF de origen y contrasena para proteger el resultado.
4. Presione **Extraer paginas**.

Ejemplos de seleccion:

- `2,4,7`: solo esas paginas.
- `1-3, 8, 10`: un rango y paginas sueltas.
- `8-`: desde la pagina 8 hasta el final.
- `-3`: de la primera a la tercera.
- `todo`, `impar`, `par` (tambien `all`, `odd`, `even`).

## Convertir

Convierta documentos de Word (`.docx`, `.doc`, `.rtf`) y Excel (`.xlsx`, `.xls`) a PDF. Requiere Microsoft Office instalado.

## Firmar

Estampe una imagen de su firma sobre el documento.

1. Seleccione el **PDF a firmar**. Se abre en la ultima pagina.
2. Elija una firma guardada, **dibuje** una nueva (icono de lapiz) o **importe** una imagen PNG/JPG.
3. Haga clic en la vista previa para ubicar la firma y arrastrela para ajustarla. Tambien puede escribir **Pagina**, **X**, **Y** y **Ancho** (en puntos: 72 pt = 1 pulgada).
4. Opcional: **Firmar todas las paginas** en la misma posicion.
5. Presione **Firmar PDF**.

Navegue con los botones de pagina, acerque o aleje con **Ctrl + rueda del mouse** y use **Ajustar pagina** para volver a ver la hoja completa.

Las imagenes importadas con fondo blanco se vuelven transparentes y se recortan sus margenes automaticamente. Lo que ve en la vista previa es exactamente lo que queda en el PDF.

Importante: esta es una firma **visual**, no una firma digital con certificado.

## Proteger

- **Proteger con contrasena**: genera una copia cifrada (AES-256). Escriba y confirme la contrasena (minimo 4 caracteres).
- **Quitar contrasena**: genera una copia sin proteccion, siempre que conozca la contrasena actual.

Al seleccionar un PDF, la aplicacion detecta si esta protegido y elige la accion adecuada.

## Ajustes

Los cambios se guardan automaticamente:

- **Modo**: Sistema, Claro u Oscuro (tambien desde la barra lateral).
- **Color de acento**: se aplica al reiniciar.
- **Tamano de la interfaz**.
- **Pagina inicial** al abrir la aplicacion.
- **Abrir el archivo al terminar**.
- **Carpeta de salida** por defecto.

El tamano y la posicion de la ventana se recuerdan al cerrar.

## Privacidad y seguridad

Todo se procesa en este equipo; la aplicacion no usa internet. Nunca intenta descubrir contrasenas: para abrir o desbloquear un PDF protegido debe conocer su clave.
