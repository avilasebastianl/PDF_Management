# PDF Management - Guia de uso

Navegue entre secciones con la barra lateral o con **Ctrl+1** a **Ctrl+6**. Pulse **F1** para abrir esta guia.

En casi todos los campos de archivo puede **arrastrar** el archivo desde el explorador.

La **barra de estado** (parte inferior) indica que esta haciendo la aplicacion: un punto gris significa *listo*, la barra animada una operacion *en curso* (con las que esperan en cola), el punto verde el *ultimo archivo generado* con los botones **Mostrar en carpeta** y **Abrir**, y el rojo que la ultima operacion *no se completo*. Pase el cursor sobre ella para ver el detalle. Puede seguir trabajando mientras una operacion esta en curso.

La aplicacion nunca sobrescribe un archivo sin preguntar: si el nombre de salida sugerido ya existe, elige automaticamente uno libre, por ejemplo `informe_firmado (2).pdf`.

## Unir

Combine varios PDFs en uno solo.

1. Presione **Agregar PDFs** o arrastre archivos (o carpetas completas) a la lista. Puede seguir trabajando mientras se leen: cada fila muestra sus paginas y tamano al terminar.
2. Ordenelos con las flechas de cada fila o con **Ordenar A-Z**.
3. Opcional: active **Crear un marcador por cada archivo**. El PDF unido tendra en su indice lateral un marcador con el nombre de cada archivo de origen, para saltar directo a su inicio; los marcadores originales se conservan anidados dentro. Pase el cursor sobre la opcion para ver esta explicacion.
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

Arriba del panel elija el tipo de firma: **Firma visual** o **Firma digital**.

### Firma visual

Estampe una imagen de su firma sobre el documento.

1. Seleccione el **PDF a firmar**. Se abre en la ultima pagina.
2. Elija una firma guardada, **dibuje** una nueva (icono de lapiz) o **importe** una imagen PNG/JPG.
3. Haga clic en la vista previa para ubicar la firma y arrastrela para moverla.
4. Para cambiar el tamano, arrastre cualquiera de las **cuatro esquinas** del recuadro (la proporcion se mantiene) o use el control **Tamano** con su deslizador y los botones **-** / **+**. Tambien puede escribir **Pagina**, **X**, **Y** y **Ancho** (en puntos: 72 pt = 1 pulgada).
5. Opcional: **Firmar todas las paginas** en la misma posicion y tamano.
6. Presione **Firmar PDF**.

Navegue con los botones de pagina, acerque o aleje con **Ctrl + rueda del mouse** y use **Ajustar pagina** para volver a ver la hoja completa.

Las imagenes importadas con fondo blanco se vuelven transparentes y se recortan sus margenes automaticamente. Lo que ve en la vista previa es exactamente lo que queda en el PDF.

La firma visual no tiene validez criptografica: cualquiera podria copiar la imagen. Para eso use la firma digital.

### Firma digital con certificado

Firma el PDF con su certificado digital (archivo `.pfx` o `.p12`). Cualquier programa de PDF (por ejemplo Adobe Acrobat) puede comprobar quien firmo y si el documento cambio despues de la firma.

Si aun no tiene un certificado, vea **Como obtener un certificado digital** mas abajo.

1. Seleccione el **PDF a firmar**.
2. En **Certificado digital**, elija su archivo `.pfx` / `.p12`.
3. Opcional: escriba el **Motivo** (por ejemplo "Aprobado") y el **Lugar**.
4. Con **Mostrar la firma en el documento** activado, ubique y dimensione el recuadro en la vista previa como en la firma visual. El recuadro muestra su imagen de firma (opcional, elijala en **Firma**) y debajo la leyenda "Firmado digitalmente por" con el titular del certificado y la fecha. Si desactiva la opcion, la firma es invisible y solo aparece en el panel de firmas del lector de PDF.
5. Presione **Firmar digitalmente** e ingrese la **contrasena del certificado**. Si es incorrecta, se vuelve a pedir.

Tenga en cuenta:

- **La firma digital debe ser el ultimo cambio.** Unir, extraer, proteger o estampar una firma visual sobre el PDF despues de firmarlo invalida la firma. Haga primero todos los cambios y firme al final.
- **Varias personas pueden firmar el mismo PDF**: firme el archivo ya firmado y cada firma sigue siendo valida.
- La contrasena del certificado **nunca se guarda**: se pide en cada firma.
- Si el certificado esta vencido, no contiene la clave privada o el archivo esta danado, la aplicacion lo indica antes de firmar.
- Con un certificado **autofirmado** la firma es valida, pero Adobe mostrara la identidad del firmante como desconocida. Para que aparezca como confiable, use un certificado emitido por una entidad de certificacion reconocida.
- La firma digital se ubica en una sola pagina.

Desde la linea de comandos: `python main.pyw sign-cert contrato.pdf --cert firma.pfx --x 400 --y 700` (sin `--x`/`--y` la firma es invisible).

### Como obtener un certificado digital

Necesita un archivo `.pfx` o `.p12` (contiene su clave privada y su identidad) y la contrasena que lo protege.

**Para uso real (con validez legal).** Adquieralo con una entidad de certificacion reconocida. En Colombia, por ejemplo, las acreditadas por ONAC: Certicamara, GSE o Andes SCD. Le entregan el archivo y su contrasena. Los certificados en token USB o tarjeta aun no son compatibles con la aplicacion.

**Para hacer pruebas (autofirmado).** Puede crear uno gratis en su propio equipo con PowerShell. Abra PowerShell (menu Inicio > escriba *PowerShell*) y ejecute los dos comandos, uno por uno. Cambie *Su Nombre* por el nombre que quiere ver en la firma; el segundo comando le pedira la contrasena con la que protegera el archivo.

```powershell
$cert = New-SelfSignedCertificate -Type Custom -Subject "CN=Su Nombre, C=CO" -KeyUsage DigitalSignature, NonRepudiation -KeyAlgorithm RSA -KeyLength 2048 -TextExtension @("2.5.29.37={text}1.3.6.1.4.1.311.10.3.12") -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(1)
```

```powershell
Export-PfxCertificate -Cert $cert -FilePath "$HOME\Documents\firma_prueba.pfx" -Password (Read-Host -AsSecureString "Contrasena del certificado")
```

El archivo queda en **Documentos\firma_prueba.pfx**, listo para elegirlo en **Certificado digital**. Puede seleccionar los comandos en esta ventana y copiarlos con **Ctrl+C**, o usar el boton **Copiar** de cada bloque.

El certificado tambien queda guardado en Windows (Administrador de certificados: `certmgr.msc` > Personal > Certificados). Si no lo necesita ahi, puede borrarlo; el archivo `.pfx` sigue funcionando.

### Verificar una firma digital

1. Abra el PDF firmado en **Adobe Acrobat Reader** (gratuito).
2. Abra el **Panel de firmas** (barra superior: *Firmado y todas las firmas son validas* o el icono de la pluma).
3. Revise el firmante, la fecha y que el documento no se modifico despues de firmar.

Con un certificado autofirmado, Acrobat indicara que la **identidad del firmante es desconocida**: la firma es valida, pero nadie respalda su identidad. Para sus pruebas puede confiar en el manualmente: en el panel de firmas, clic derecho sobre la firma > *Mostrar propiedades de firma* > *Mostrar certificado del firmante* > pestana *Confianza* > *Agregar a certificados de confianza*.

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

En **Datos locales** puede activar el **Registro detallado (para depurar)**: guarda en `log/app.log` cada accion con mas detalle, util si necesita reportar un problema. Se aplica al instante y las contrasenas nunca se registran. El boton **Ver registro** abre ese archivo.

## Privacidad y seguridad

Todo se procesa en este equipo; la aplicacion no usa internet, tampoco al firmar digitalmente. Nunca intenta descubrir contrasenas: para abrir o desbloquear un PDF protegido debe conocer su clave.
