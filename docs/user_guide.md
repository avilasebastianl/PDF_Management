# PDF Management - Guía de uso

Navegue entre secciones con la barra lateral o con **Ctrl+1** a **Ctrl+8**. Pulse **F1** para abrir esta guía.

El botón **☰** arriba a la izquierda contrae la barra lateral para dejar solo los iconos y ganar espacio; al pasar el cursor por un icono se ve el nombre de la sección. Vuelva a pulsarlo para expandirla. La aplicación recuerda su elección.

En casi todos los campos de archivo puede **arrastrar** el archivo desde el explorador.

La **barra de estado** (parte inferior) indica qué está haciendo la aplicación: un punto gris significa *listo*, la barra animada una operación *en curso* (con las que esperan en cola), el punto verde el *último archivo generado* con los botones **Mostrar en carpeta**, **Abrir** y **Ver en el visor**, y el rojo que la última operación *no se completó*. Pase el cursor sobre ella para ver el detalle. Puede seguir trabajando mientras una operación está en curso.

La aplicación nunca sobrescribe un archivo sin preguntar: si el nombre de salida sugerido ya existe, elige automáticamente uno libre, por ejemplo `informe_firmado (2).pdf`.

La interfaz está disponible en **español**, **inglés** y **ruso** (vea **Ajustes**).

## Visor

Lea cualquier PDF sin salir de la aplicación. Es la primera sección y la que se abre al iniciar (puede cambiarlo en Ajustes).

- **Abrir**: botón **Abrir**, **Ctrl+O**, clic en el área vacía o arrastre un PDF. Si está protegido se pide la contraseña. **Recientes** muestra los últimos 10 archivos.
- **Pestañas**: cada documento se abre en su propia pestaña, como en un navegador, y conserva su página, zoom y cambios. Las pestañas tienen el mismo ancho y se encogen cuando hay muchas; un punto (•) indica cambios sin guardar. Cambie con un clic o **Ctrl+Tab**; cierre con la **x** (aparece al pasar el cursor), con un clic con el botón central del ratón o con **Ctrl+W**, y abra otro documento con **+**. Si abre un archivo que ya está abierto, se muestra su pestaña.
- **Buscar**: pulse el botón **Buscar** (o **Ctrl+F**), escriba y pulse **Enter**; cada **Enter** va al siguiente resultado (**Mayús+Enter** al anterior). La barra muestra cuántos hay; **Aa** distingue mayúsculas, **ab** busca palabras completas y el botón de lista los muestra todos con su contexto en el panel lateral. **Esc** la cierra.
- **Ver** (botón del ojo): reúne las opciones de lectura:
  - **Modo nocturno**: muestra las páginas con los colores invertidos (texto claro sobre fondo oscuro), más cómodo de noche.
  - **Dos páginas**: muestra las páginas de a pares, lado a lado, como un libro abierto.
  - **Comparar con**: elija otra pestaña u **Otro PDF...** para verlo a la derecha del documento actual (vista dividida). Con **Sincronizar páginas** activado, las dos vistas pasan de página juntas. Si edita el documento comparado en su pestaña, la vista se actualiza; al cerrar su pestaña (o con **Cerrar la comparación**) la comparación termina.
  - **Imprimir...** (**Ctrl+P**): abre el diálogo de impresión de Windows (impresora, páginas y copias). Se imprime el documento tal como se ve, incluidos los cambios aún no guardados.

  El modo nocturno y la vista de dos páginas se recuerdan para la próxima vez.
- **Leer en toda la ventana**: el botón de la ventana (o **Ctrl+Mayús+F**) oculta el menú, las barras y el panel lateral y deja el documento ocupando toda la ventana, con las pestañas a mano. **Esc** vuelve.
- **Pantalla completa**: el botón de las flechas (o **F11**) deja solo el visor en toda la pantalla; **Esc** o **F11** vuelven.
- **Panel lateral** (botón de lista para mostrarlo u ocultarlo). Sus pestañas son iconos: pase el cursor por cada uno para ver su nombre; el de la pestaña activa se muestra debajo.
  - **Páginas**: miniaturas; haga clic en una para ir a esa página.
  - **Marcadores**: el índice del documento, si lo tiene.
  - **Buscar**: la lista de resultados con su contexto (también puede buscar desde aquí). **F3** / **Mayús+F3** van al resultado siguiente / anterior.
  - **Notas**: todas las anotaciones del documento (vea **Anotar**).
  - **Firmas**: las firmas digitales del documento y su estado (vea **Firmas digitales en el Visor**).
- **Texto y Mano**: con **Texto** arrastre sobre el texto para seleccionarlo (**Ctrl+C** copia y **Ctrl+A** selecciona la página); con **Mano** arrastre para mover la página. El botón central del ratón también desplaza.
- **Zoom**: **Ctrl + rueda** (centrado en el cursor), **Ctrl++** / **Ctrl+-**, **Ctrl+0** para ajustar al ancho, o la lista de zoom (ajustar ancho, ajustar página, 50-400 %).
- **Navegar**: rueda, **Re Pág** / **Av Pág**, **Inicio** / **Fin**, o escriba el número de página.
- **Propiedades** (botón con la letra i, junto a deshacer y rehacer): título, autor, fechas, tamaño de página, cifrado y firmas del documento. A su lado, el botón de la **impresora** imprime el documento (**Ctrl+P**).
- **Enviar a...**: abre el documento en Unir, Extraer, Firmar o Proteger sin buscarlo de nuevo.
- **Esc** borra la selección y los resaltados de la búsqueda.

El visor solo dibuja las páginas que se ven, así que los documentos de cientos de páginas abren y se desplazan con la misma fluidez.

Si falta espacio (textos más largos en otro idioma, al comparar documentos o con la ventana pequeña), los botones **Buscar** y **Editar** quedan solo con su icono y la barra de anotación se reparte en dos filas.

### Organizar páginas

Pulse **Editar** (o **Ctrl+E**) para mostrar las herramientas; **Listo** las oculta. En el panel **Páginas**:

- **Seleccionar**: clic en una miniatura. **Ctrl+clic** agrega o quita páginas y **Mayús+clic** selecciona un rango.
- **Reordenar**: arrastre las miniaturas seleccionadas; una línea azul indica dónde quedarán. Cerca del borde el panel se desplaza solo.
- **Botones** sobre las miniaturas: rotar a la izquierda o a la derecha, eliminar, insertar otro PDF y agregar una página en blanco (después de la selección).
- **Clic derecho** en una miniatura o en la página abre el mismo menú, con la opción de insertar antes o después.

Atajos: **Ctrl+R** / **Ctrl+Mayús+R** rotar, **Supr** eliminar, **Ctrl+Z** deshacer, **Ctrl+Y** rehacer, **Ctrl+S** guardar como.

Todo se puede deshacer sin límite; pase el cursor por los botones de deshacer/rehacer para ver qué acción revierten. Mientras haya cambios sin guardar, el nombre del archivo muestra un punto (•).

Los cambios se guardan siempre con **Guardar como** en un archivo nuevo: el original nunca se modifica. Si el PDF estaba protegido, la copia conserva la misma contraseña. Si intenta abrir otro archivo, enviarlo a otra sección o cerrar la aplicación con cambios sin guardar, se le pregunta si desea guardarlos.

Si el documento tiene **firmas digitales**, se le avisa antes del primer cambio: cualquier modificación hace que las firmas dejen de ser válidas en la copia.

### Anotar

La **barra de anotación** aparece debajo de la navegación del visor al pulsar **Editar**:

- **Resaltar, subrayar y tachar**: elija la herramienta y arrastre sobre el texto. Si ya tiene texto seleccionado con la herramienta **Texto**, un clic en el botón lo marca al instante.
- **Nota**: haga clic donde quiere el icono y escriba el comentario.
- **Texto**: arrastre para dibujar el cuadro (o haga clic) y escriba el texto que aparecerá en la página.
- **Rectángulo, elipse, línea y flecha**: arrastre de una esquina a otra.
- **Dibujo a mano**: arrastre para trazar.
- **Color** (amarillo, verde, azul, rojo o negro), **grosor** (fino, medio o grueso) y **Letra** (tamaño del texto) a la derecha de la barra.
- **Tamaño de un texto**: selecciónelo con un clic y elija el tamaño en **Letra**; el cuadro se ajusta solo. Al escribir un texto nuevo, el cuadro también se ajusta a lo escrito.

Pulse **Esc** o vuelva a pulsar la herramienta para terminar.

Para **editar** una anotación use la herramienta **Texto**: haga clic sobre ella para seleccionarla (aparece un contorno discontinuo). Después puede arrastrarla para moverla, elegir otro color, hacer doble clic en una nota o un texto para cambiarlo, o pulsar **Supr** para eliminarla. El clic derecho sobre una anotación ofrece las mismas opciones.

El panel **Notas** lista todas las anotaciones del documento: haga clic en una para ir a ella; los botones permiten editar su texto o eliminarla.

Como el resto de cambios, las anotaciones se deshacen con **Ctrl+Z** y se guardan con **Guardar como**.

### Editar el contenido

Después de las herramientas de anotación, la barra tiene cuatro herramientas que cambian el **contenido mismo de la página** (no son anotaciones: quedan escritas en ella):

- **Reemplazar texto**: arrastre sobre el texto que quiere cambiar (o selecciónelo antes con **Texto** y pulse el botón) y escriba el texto nuevo. Se escribe en el mismo lugar, con el mismo tamaño, color y dirección, pero con letra Helvetica. Si la selección abarca varias páginas, solo se reemplaza la primera.
- **Texto fijo**: haga clic donde va y escriba el texto. Usa el color y el tamaño de **Letra** elegidos en la barra (con el amarillo, que no se lee sobre blanco, se escribe en negro).
- **Imagen**: arrastre el área donde irá (o haga clic para un tamaño estándar) y elija una imagen (PNG, JPG, BMP, GIF o TIFF). Se ajusta al área conservando su proporción y queda derecha aunque la página esté girada.
- **Tapar**: arrastre sobre lo que quiere eliminar. La zona se pinta de negro y lo que hay debajo (texto, imágenes y dibujos) **se elimina de verdad**, no solo queda cubierto: ya no se puede copiar, buscar ni recuperar desde el archivo guardado.

Todo se deshace con **Ctrl+Z** y se guarda con **Guardar como**.

Limitación: la letra Helvetica solo tiene el alfabeto latino. **Reemplazar texto** y **Texto fijo** no pueden escribir caracteres cirílicos ni de otros alfabetos no latinos; si el texto los contiene, la aplicación lo indica y no lo escribe.

### Firmas digitales en el Visor

El panel **Firmas** verifica las firmas digitales del documento abierto. Cada firma muestra el firmante, la fecha, el campo y uno de estos estados:

- **Válida**: la firma es correcta y el documento no cambió desde que se firmó.
- **Identidad no verificada**: la firma es correcta y el documento no cambió, pero no se pudo comprobar la identidad del firmante (por ejemplo, un certificado autofirmado o de una entidad que este equipo no reconoce).
- **Modificado después de firmar**: la firma es correcta, pero el documento se modificó después de firmarse.
- **No válida**: el contenido firmado cambió o la firma está dañada.

La verificación es local: no consulta servidores en internet (OCSP ni CRL). Se verifica el archivo guardado; los cambios sin guardar no se incluyen. **Verificar** vuelve a comprobarlas y **Firmar...** envía el documento a la sección **Firmar**.

## Unir

Combine varios PDFs en uno solo.

1. Presione **Agregar PDFs** o arrastre archivos (o carpetas completas) a la lista. Puede seguir trabajando mientras se leen: cada fila muestra sus páginas y tamaño al terminar.
2. Ordénelos con las flechas de cada fila o con **Ordenar A-Z**.
3. Opcional: active **Crear un marcador por cada archivo**. El PDF unido tendrá en su índice lateral un marcador con el nombre de cada archivo de origen, para saltar directo a su inicio; los marcadores originales se conservan anidados dentro. Pase el cursor sobre la opción para ver esta explicación.
4. Revise **Guardar como** y presione **Unir PDFs**.

Si algún PDF está protegido, la aplicación pedirá su contraseña.

## Extraer

Genere un PDF nuevo con solo algunas páginas, en el orden que indique.

1. Seleccione el **PDF** de origen. Verá su número de páginas.
2. Escriba la **Selección** (las páginas empiezan en 1). Debajo verá cuántas páginas se extraerán.
3. Opcional: contraseña del PDF de origen y contraseña para proteger el resultado.
4. Presione **Extraer páginas**.

Ejemplos de selección:

- `2,4,7`: solo esas páginas.
- `1-3, 8, 10`: un rango y páginas sueltas.
- `8-`: desde la página 8 hasta el final.
- `-3`: de la primera a la tercera.
- `todo`, `impar`, `par` (también `all`, `odd`, `even`).

## Convertir

Convierta documentos de Word (`.docx`, `.doc`, `.rtf`) y Excel (`.xlsx`, `.xls`) a PDF. Requiere Microsoft Office instalado.

## Firmar

Arriba del panel elija el tipo de firma: **Firma visual** o **Firma digital**.

### Firma visual

Estampe una imagen de su firma sobre el documento.

1. Seleccione el **PDF a firmar**. Se abre en la última página.
2. Elija una firma guardada, **dibuje** una nueva (icono de lápiz) o **importe** una imagen PNG/JPG.
3. Haga clic en la vista previa para ubicar la firma y arrástrela para moverla.
4. Para cambiar el tamaño, arrastre cualquiera de las **cuatro esquinas** del recuadro (la proporción se mantiene) o use el control **Tamaño** con su deslizador y los botones **-** / **+**. También puede escribir **Página**, **X**, **Y** y **Ancho** (en puntos: 72 pt = 1 pulgada).
5. Opcional: **Firmar todas las páginas** en la misma posición y tamaño.
6. Presione **Firmar PDF**.

Navegue con los botones de página, acerque o aleje con **Ctrl + rueda del ratón** y use **Ajustar página** para volver a ver la hoja completa.

Las imágenes importadas con fondo blanco se vuelven transparentes y se recortan sus márgenes automáticamente. Lo que ve en la vista previa es exactamente lo que queda en el PDF.

La firma visual no tiene validez criptográfica: cualquiera podría copiar la imagen. Para eso use la firma digital.

### Firma digital con certificado

Firma el PDF con su certificado digital (archivo `.pfx` o `.p12`). Cualquier programa de PDF (por ejemplo Adobe Acrobat) puede comprobar quién firmó y si el documento cambió después de la firma.

Si aún no tiene un certificado, vea **Cómo obtener un certificado digital** más abajo.

1. Seleccione el **PDF a firmar**.
2. En **Certificado digital**, elija su archivo `.pfx` / `.p12`.
3. Opcional: escriba el **Motivo** (por ejemplo "Aprobado") y el **Lugar**.
4. Con **Mostrar la firma en el documento** activado, ubique y dimensione el recuadro en la vista previa como en la firma visual. El recuadro muestra su imagen de firma (opcional, elíjala en **Firma**) y debajo la leyenda "Firmado digitalmente por" con el titular del certificado y la fecha. Si desactiva la opción, la firma es invisible y solo aparece en el panel de firmas del lector de PDF.
5. Presione **Firmar digitalmente** e ingrese la **contraseña del certificado**. Si es incorrecta, se vuelve a pedir.

Tenga en cuenta:

- **La firma digital debe ser el último cambio.** Unir, extraer, proteger o estampar una firma visual sobre el PDF después de firmarlo invalida la firma. Haga primero todos los cambios y firme al final.
- **Varias personas pueden firmar el mismo PDF**: firme el archivo ya firmado y cada firma sigue siendo válida.
- La contraseña del certificado **nunca se guarda**: se pide en cada firma.
- Si el certificado está vencido, no contiene la clave privada o el archivo está dañado, la aplicación lo indica antes de firmar.
- Con un certificado **autofirmado** la firma es válida, pero Adobe mostrará la identidad del firmante como desconocida. Para que aparezca como confiable, use un certificado emitido por una entidad de certificación reconocida.
- La firma digital se ubica en una sola página.
- La leyenda visible de la firma usa una letra con alfabeto latino: con la interfaz en ruso se escribe en inglés ("Digitally signed by").

Desde la línea de comandos: `python main.pyw sign-cert contrato.pdf --cert firma.pfx --x 400 --y 700` (sin `--x`/`--y` la firma es invisible).

### Cómo obtener un certificado digital

Necesita un archivo `.pfx` o `.p12` (contiene su clave privada y su identidad) y la contraseña que lo protege.

**Para uso real (con validez legal).** Adquiéralo con una entidad de certificación reconocida. En Colombia, por ejemplo, las acreditadas por ONAC: Certicámara, GSE o Andes SCD. Le entregan el archivo y su contraseña. Los certificados en token USB o tarjeta aún no son compatibles con la aplicación.

**Para hacer pruebas (autofirmado).** Puede crear uno gratis en su propio equipo con PowerShell. Abra PowerShell (menú Inicio > escriba *PowerShell*) y ejecute los dos comandos, uno por uno. Cambie *Su Nombre* por el nombre que quiere ver en la firma; el segundo comando le pedirá la contraseña con la que protegerá el archivo.

```powershell
$cert = New-SelfSignedCertificate -Type Custom -Subject "CN=Su Nombre, C=CO" -KeyUsage DigitalSignature, NonRepudiation -KeyAlgorithm RSA -KeyLength 2048 -TextExtension @("2.5.29.37={text}1.3.6.1.4.1.311.10.3.12") -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(1)
```

```powershell
Export-PfxCertificate -Cert $cert -FilePath "$HOME\Documents\firma_prueba.pfx" -Password (Read-Host -AsSecureString "Contrasena del certificado")
```

El archivo queda en **Documentos\firma_prueba.pfx**, listo para elegirlo en **Certificado digital**. Puede seleccionar los comandos en esta ventana y copiarlos con **Ctrl+C**, o usar el botón **Copiar** de cada bloque.

El certificado también queda guardado en Windows (Administrador de certificados: `certmgr.msc` > Personal > Certificados). Si no lo necesita ahí, puede borrarlo; el archivo `.pfx` sigue funcionando.

### Verificar una firma digital

En la aplicación: abra el PDF firmado en el **Visor** y elija el panel **Firmas** (vea **Firmas digitales en el Visor**).

En Adobe Acrobat Reader (gratuito):

1. Abra el PDF firmado.
2. Abra el **Panel de firmas** (barra superior: *Firmado y todas las firmas son válidas* o el icono de la pluma).
3. Revise el firmante, la fecha y que el documento no se modificó después de firmar.

Con un certificado autofirmado, Acrobat indicará que la **identidad del firmante es desconocida**: la firma es válida, pero nadie respalda su identidad. Para sus pruebas puede confiar en él manualmente: en el panel de firmas, clic derecho sobre la firma > *Mostrar propiedades de firma* > *Mostrar certificado del firmante* > pestaña *Confianza* > *Agregar a certificados de confianza*.

## Proteger

- **Proteger con contraseña**: genera una copia cifrada (AES-256). Escriba y confirme la contraseña (mínimo 4 caracteres).
- **Quitar contraseña**: genera una copia sin protección, siempre que conozca la contraseña actual.

Al seleccionar un PDF, la aplicación detecta si está protegido y elige la acción adecuada.

## Herramientas

Elija el **PDF** de origen y, arriba, la herramienta: **Comprimir**, **Dividir**, **Numerar páginas** o **Marca de agua**. Cada una genera un archivo nuevo (Dividir, varios en una carpeta) y el original nunca se modifica. Si el PDF está protegido, se pide su contraseña y el resultado conserva la misma contraseña (AES-256).

- **Comprimir**: reduce el tamaño, ideal para enviar por correo. Elija el **Nivel**:
  - **Baja (sin perder calidad)**: quita datos sin uso y comprime el contenido.
  - **Media (recomendada)**: además reduce la resolución de las imágenes grandes.
  - **Alta (imágenes más livianas)**: reduce todavía más las imágenes.

  Al terminar se muestra el tamaño antes y después. Si el resultado no es más liviano (por ejemplo, porque las imágenes ya estaban comprimidas), se guarda una copia idéntica al original en lugar de un archivo más pesado.
- **Dividir**: crea varios archivos en la **Carpeta** que elija. En **Cómo dividir**:
  - **Por rangos**: grupos separados por punto y coma, por ejemplo `1-3; 4-6; 7-` (un archivo por grupo).
  - **Cada N páginas**: la cantidad de páginas de cada archivo, por ejemplo `2`.
  - **Por marcadores**: un archivo por cada marcador principal del documento (capítulos); el nombre del archivo incluye el del marcador.
- **Numerar páginas**: escribe el número en cada página.
  - **Formato**: `{n}` es el número y `{total}` el total, por ejemplo `Página {n} de {total}` o solo `{n}`.
  - **Posición**: arriba o abajo, a la izquierda, al centro o a la derecha (6 posiciones).
  - **Empezar en**: el primer número.
  - **Páginas**: deje el campo vacío para numerar todas, o escriba una selección como en Extraer (por ejemplo `3-`). Solo cuentan las páginas numeradas.
- **Marca de agua**: escribe un texto grande y semitransparente en diagonal en el centro de cada página, por ejemplo CONFIDENCIAL o BORRADOR. Elija el **Texto**, la **Opacidad** y si va **Detrás del contenido** (si no, va delante). Los textos largos se reducen para que quepan en la página.

Los textos de **Numerar páginas** y **Marca de agua** se escriben con Helvetica; si contienen otros alfabetos (por ejemplo cirílico), se usa la letra Arial de Windows.

## Ajustes

Los cambios se guardan automáticamente, como indica el aviso en la parte superior: lo que elija queda guardado al instante y es la configuración predeterminada cada vez que abra la aplicación.

- **Modo**: Sistema, Claro u Oscuro (también desde la barra lateral).
- **Color de acento**: se aplica al reiniciar.
- **Tamaño de la interfaz**.
- **Idioma**: Español, English o Русский. Se aplica al reiniciar; el botón **Reiniciar ahora** lo hace de inmediato.
- **Página inicial** al abrir la aplicación.
- **Abrir el archivo al terminar**.
- **Carpeta de salida** por defecto.

El tamaño y la posición de la ventana se recuerdan al cerrar.

En **Acerca de** encontrará para qué sirve la aplicación, en qué se destaca, cómo se hizo y quién la desarrolló, con enlaces a su GitHub, su LinkedIn y el código fuente.

En **Datos locales** puede activar el **Registro detallado (para depurar)**: guarda en `log/app.log` cada acción con más detalle, útil si necesita reportar un problema. Se aplica al instante y las contraseñas nunca se registran. El botón **Ver registro** abre ese archivo.

## Privacidad y seguridad

Todo se procesa en este equipo; la aplicación no usa internet, tampoco al firmar digitalmente ni al verificar firmas. Nunca intenta descubrir contraseñas: para abrir o desbloquear un PDF protegido debe conocer su clave.
