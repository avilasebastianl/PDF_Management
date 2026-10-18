# PDF Management - User guide

Move between sections with the sidebar or with **Ctrl+1** to **Ctrl+9**. Press **F1** to open this guide.

The **☰** button at the top left collapses the sidebar to icons only to save space; hover over an icon to see the section name. Press it again to expand the sidebar. The app remembers your choice.

In almost every file field you can **drag** the file in from File Explorer.

The **status bar** (at the bottom) shows what the app is doing: a gray dot means *ready*, the animated bar means an operation is *in progress* (plus any waiting in the queue), the green dot is the *last file generated* with the **Show in folder**, **Open** and **View in the viewer** buttons, and red means the last operation *did not complete*. Hover over it for details. You can keep working while an operation is in progress.

The app never overwrites a file without asking: if the suggested output name already exists, it automatically picks a free one, for example `informe_firmado (2).pdf`.

The interface is available in **Spanish**, **English** and **Russian** (see **Settings**).

Below the light/dark mode button, the **−** and **+** buttons on either side of **Size** shrink or enlarge the interface (click the percentage to choose it from a list). It is for now only: on restart it returns to the size in **Settings**, which is where the default is changed.

## Viewer

Read any PDF without leaving the app. It is the first section and the one that opens at startup (you can change this in Settings).

- **Open**: the **Open** button, **Ctrl+O**, a click on the empty area, or drag in a PDF. If it is protected, you are asked for the password. **Recent** shows the last 10 files.
- **New PDF**: the **New PDF** button (next to **Open**), **Ctrl+N** or the large button in the empty viewer. Choose a template with its preview (**Blank**, **Lined paper**, **Grid**, **Letter**, **Meeting minutes** or **Invoice**), the size (A4, Letter or Legal), the orientation and, for the first three, how many pages. It opens in a new tab ready to annotate or to write on with **Fixed text**; save it with **Save as** (the output folder is suggested).
- **Tabs**: each document opens in its own tab, as in a browser, and keeps its page, zoom and changes. Tabs have the same width and shrink when there are many; a dot (•) indicates unsaved changes. Switch with a click or **Ctrl+Tab**; close with the **x** (shown when you hover), with a middle mouse button click, or with **Ctrl+W**, and open another document with **+**. If you open a file that is already open, its tab is shown.
- **Merge the open ones**: with two or more documents open, the **Merge N PDFs** button appears next to the tabs. It takes all of them to the **Merge** section, in tab order; those with unsaved changes go with those changes (without saving them). To use a single document in another section, use **Send to...**.
- **Search**: press the **Search** button (or **Ctrl+F**), type and press **Enter**; each **Enter** goes to the next result (**Shift+Enter** to the previous one). The bar shows how many there are; **Aa** matches case, **ab** searches whole words only, and the list button shows all of them with their context in the side panel. **Esc** closes it.
- **View** (eye button): groups the reading options:
  - **Night mode**: shows the pages with inverted colors (light text on a dark background), more comfortable at night.
  - **Two pages**: shows pages in pairs, side by side, like an open book.
  - **Compare with**: choose another tab or **Another PDF...** to see it to the right of the current document (split view). With **Sync pages** on, both views turn pages together. If you edit the compared document in its own tab, the view updates; when its tab is closed (or with **Close comparison**) the comparison ends.
  - **Print...** (**Ctrl+P**): opens the Windows print dialog (printer, pages and copies). The document is printed as you see it, including changes not yet saved.

  Night mode and the two-page view are remembered for next time.
- **Read across the whole window**: the window button (or **Ctrl+Shift+F**) hides the menu, bars and side panel and lets the document fill the whole window, with the tabs within reach. **Esc** goes back.
- **Full screen**: the arrows button (or **F11**) shows only the viewer across the whole screen; **Esc** or **F11** goes back. In full screen you can switch programs with **Alt+Tab** as usual.
- **Side panel** (list button to show or hide it). Its tabs are icons: hover over each one to see its name; the name of the active tab is shown below.
  - **Pages**: thumbnails; click one to go to that page.
  - **Bookmarks**: the document's outline, if it has one.
  - **Search**: the list of results with their context (you can also search from here). **F3** / **Shift+F3** go to the next / previous result.
  - **Notes**: all the annotations in the document (see **Annotate**).
  - **Signatures**: the document's digital signatures and their status (see **Digital signatures in the Viewer**).
- **Text and Hand**: with **Text**, drag over the text to select it (**Ctrl+C** copies and **Ctrl+A** selects the page); with **Hand**, drag to move the page. The middle mouse button also scrolls.
- **Zoom**: **Ctrl + wheel** (centered on the cursor), **Ctrl++** / **Ctrl+-**, **Ctrl+0** to fit the width, or the zoom list (fit width, fit page, 50-400%).
- **Navigate**: wheel or touchpad (scrolls the viewer under the cursor, also when comparing), **PgUp** / **PgDn**, **Home** / **End**, or type the page number.
- **Properties** (the button with the letter i, next to undo and redo): title, author, dates, page size, encryption and signatures of the document. Next to it, the **printer** button prints the document (**Ctrl+P**).
- **Send to...**: opens the document in Merge, Extract, Sign or Protect without having to find it again.
- **Esc** clears the selection and the search highlights.

The viewer only draws the pages you can see, so documents of hundreds of pages open and scroll just as smoothly.

If space is short (longer texts in another language, when comparing documents, or with a small window), the **Search** and **Edit** buttons show only their icon and the annotation bar splits into two rows.

### Organize pages

Press **Edit** (or **Ctrl+E**) to show the tools; **Done** hides them. In the **Pages** panel:

- **Select**: click a thumbnail. **Ctrl+click** adds or removes pages and **Shift+click** selects a range.
- **Reorder**: drag the selected thumbnails; a blue line shows where they will land. Near the edge the panel scrolls by itself.
- **Buttons** above the thumbnails: rotate left or right, delete, insert another PDF, and add a blank page (after the selection).
- **Right-click** a thumbnail or the page to open the same menu, with the option to insert before or after.

Shortcuts: **Ctrl+R** / **Ctrl+Shift+R** rotate, **Del** delete, **Ctrl+Z** undo, **Ctrl+Y** redo, **Ctrl+S** save as.

Everything can be undone without limit; hover over the undo/redo buttons to see which action they revert. While there are unsaved changes, the file name shows a dot (•).

Changes are always saved with **Save as** to a new file: the original is never modified. If the PDF was protected, the copy keeps the same password. If you try to open another file, send it to another section, or close the app with unsaved changes, you are asked whether you want to save them.

If the document has **digital signatures**, you are warned before the first change: any modification makes the signatures in the copy no longer valid.

### Annotate

The **annotation bar** appears below the viewer's navigation when you press **Edit**:

- **Select** (the arrow, first on the bar, active when you press **Edit**): hover to highlight what is underneath, and a click selects it: an **annotation**, a **line of text** or an **image** on the page. Annotations are moved by dragging them; a **double-click** edits the text (of a line or a note) and **Del** deletes the selection (a line is erased by covering it with the background color; an image is removed without touching the text).

- **Highlight, underline and strike out**: choose the tool and drag over the text. If you already have text selected with the **Text** tool, one click on the button marks it instantly.
- **Note**: click where you want the icon and type the comment in the field that appears next to it.
- **Text**: drag to draw the box (or click) and type the text that will appear on the page.

Text is typed **directly on the page**, in a field that appears in its place and at its size, without dialog boxes: **Enter** applies it, **Shift+Enter** adds a line, **Esc** cancels and clicking outside also applies it.
- **Rectangle, ellipse, line and arrow**: drag from one corner to the other.
- **Freehand drawing**: drag to draw.
- **Color** (yellow, green, blue, red or black), **thickness** (thin, medium or thick), **Font** (text size) and **Background** (background color of text boxes: no background, white or a light tone) on the right of the bar. With a text box selected, **Font** and **Background** change that box.
- **Size of a box**: select a text box, a rectangle or an ellipse and drag one of its **corners** (the small colored squares); the text reflows to the new size.
- **Size of a text**: select it with a click and choose the size in **Font**; the box adjusts by itself. When you type a new text, the box also adjusts to what you type.

Press **Esc** or click the tool again to finish.

To **edit** an annotation use **Select** (or the **Text** tool): click it to select it (a dashed outline appears). Then you can drag it to move it, choose another color, double-click a note or a text to change it, or press **Del** to delete it. Right-clicking an annotation offers the same options.

The **Notes** panel lists all the annotations in the document: click one to go to it; the buttons let you edit its text or delete it.

Like all other changes, annotations are undone with **Ctrl+Z** and saved with **Save as**.

### Edit the content

After the annotation tools, the bar has four tools that change the **page content itself** (they are not annotations: they are written into the page):

- **Replace text**: drag over the text you want to change (or select it first with **Text** and press the button; or double-click the line with **Select**). A field appears over the text, with the current text, to correct it right there. It is written in the same place, with the same size, color and direction, but in Helvetica. If the PDF declares a color that is not the one you see (for example, light text on a dark band), the color you see is used, so that it stays readable. If the selection spans several pages, only the first one is replaced.
- **Fixed text**: click where it goes and type the text. It uses the color and the **Font** size chosen in the bar (with yellow, which is unreadable on white, it is written in black).
- **Image**: drag the area where it will go (or click for a standard size) and choose an image (PNG, JPG, BMP, GIF or TIFF). It fits the area while keeping its proportions and stays upright even if the page is rotated.
- **Redact**: drag over what you want to remove. The area is covered with the **color of the background around it** (it looks erased, without a black block) and what is underneath (text, images and drawings) **is really removed**, not just covered: it can no longer be copied, searched or recovered from the saved file.

Everything is undone with **Ctrl+Z** and saved with **Save as**.

Limitation: the Helvetica font only has the Latin alphabet. **Replace text** and **Fixed text** cannot write Cyrillic characters or those of other non-Latin alphabets; if the text contains them, the app tells you and does not write it.

### Digital signatures in the Viewer

The **Signatures** panel verifies the digital signatures of the open document. Each signature shows the signer, the date, the field and one of these statuses:

- **Valid**: the signature is correct and the document has not changed since it was signed.
- **Identity not verified**: the signature is correct and the document has not changed, but the signer's identity could not be checked (for example, a self-signed certificate or one from an authority this computer does not recognize).
- **Modified after signing**: the signature is correct, but the document was modified after it was signed.
- **Not valid**: the signed content changed or the signature is damaged.

Verification is local: it does not query servers on the internet (OCSP or CRL). The saved file is verified; unsaved changes are not included. **Verify** checks them again and **Sign...** sends the document to the **Sign** section.

## Merge

Combine several PDFs into one. The whole section scrolls with a single scroll bar.

1. Press **Add PDFs** or drag files (or whole folders) into the list. You can keep working while they are read: each row shows its pages and size when done.
2. Order them with the arrows on each row or with **Sort A-Z**.
3. Optional, in **Watermark**:
   - **Add a watermark**: the same options as in **Tools** (text, opacity, orientation and whether it goes behind the content).
   - The **Result preview**, to the right of the list, goes through all the pages of the merged PDF with **‹** and **›** (below it says which file each one is from) and shows the watermark.
4. Optional: turn on **Create a bookmark for each file**. The merged PDF will have a bookmark in its side outline with the name of each source file, to jump straight to its start; the original bookmarks are kept nested inside. Hover over the option to see this explanation.
5. Check **Save as** and press **Merge PDFs**. To sign the result use **Merge and sign...**: it merges the PDFs and opens the merged one in the **Sign** section, so you can place the signature with the mouse or sign with a certificate.

If any PDF is protected, the app will ask for its password.

## Organize

Reorder, rotate, delete or insert the pages of a PDF in a grid of large thumbnails.

1. Press **Open PDF**, drag the file onto the grid, or send it from the Viewer with **Send to... > Organize**.
2. **Select**: click a page; **Ctrl+click** adds or removes a page and **Shift+click** selects a range. You can also tick the checkbox on each page or use **Ctrl+A**.
3. **Reorder**: drag a page (or the selected ones) and drop it where you want it; a colored bar shows where it will land.
4. When you hover over a page (or when it is selected), **Rotate left**, **Rotate right** and **Delete** appear. The same buttons at the top act on all selected pages; **Del** deletes them.
5. **Insert**: the **+** buttons between pages add a **Blank page** or **Pages from another PDF...** there.
6. **Ctrl+Z** undoes and **Ctrl+Y** redoes. Save the result with **Save as** (**Ctrl+S**): the original is not modified.

## Extract

Generate a new PDF with only some pages, in the order you specify.

1. Select the source **PDF**. You will see its page count.
2. Type the **Selection** (pages start at 1). Below it you will see how many pages will be extracted.
3. Optional: the source PDF's password and a password to protect the result.
4. Press **Extract pages**.

Selection examples:

- `2,4,7`: only those pages.
- `1-3, 8, 10`: a range and individual pages.
- `8-`: from page 8 to the end.
- `-3`: from the first to the third.
- `all`, `odd`, `even` (also `todo`, `impar`, `par`).

## Convert

Convert Word (`.docx`, `.doc`, `.rtf`) and Excel (`.xlsx`, `.xls`) documents to PDF. Requires Microsoft Office installed.

## Sign

At the top of the panel choose the signature type: **Visual signature** or **Digital signature**.

### Visual signature

Stamp an image of your signature on the document.

1. Select the **PDF to sign**. It opens on the last page.
2. Choose a saved signature, **draw** a new one (pencil icon) or **import** a PNG/JPG image.
3. Click the preview to place the signature and drag it to move it.
4. To resize it, drag any of the **four corners** of the box (the proportions are kept) or use the **Size** control with its slider and the **-** / **+** buttons. You can also type **Page**, **X**, **Y** and **Width** (in points: 72 pt = 1 inch).
5. Optional: **Sign all pages** at the same position and size.
6. Press **Sign PDF**.

Navigate with the page buttons, zoom in or out with **Ctrl + mouse wheel**, and use **Fit page** to see the whole sheet again.

Imported images with a white background become transparent and their margins are trimmed automatically. What you see in the preview is exactly what ends up in the PDF.

A visual signature has no cryptographic validity: anyone could copy the image. For that, use the digital signature.

### Digital signature with a certificate

Sign the PDF with your digital certificate (`.pfx` or `.p12` file). Any PDF program (for example Adobe Acrobat) can check who signed and whether the document changed after the signature.

If you do not have a certificate yet, see **How to get a digital certificate** below.

1. Select the **PDF to sign**.
2. In **Digital certificate**, choose your `.pfx` / `.p12` file.
3. Optional: type the **Reason** (for example "Approved") and the **Location**.
4. With **Show the signature on the document** turned on, place and size the box in the preview as in the visual signature. The box shows your signature image (optional, choose it in **Signature**) and below it the caption "Digitally signed by" with the certificate holder and the date. If you turn the option off, the signature is invisible and only appears in the PDF reader's signature panel.
5. Press **Sign digitally** and enter the **certificate password**. If it is wrong, you are asked again.

Keep in mind:

- **The digital signature must be the last change.** Merging, extracting, protecting, or stamping a visual signature on the PDF after signing it invalidates the signature. Make all the changes first and sign at the end.
- **Several people can sign the same PDF**: sign the already signed file and each signature stays valid.
- The certificate password is **never saved**: it is requested every time you sign.
- If the certificate has expired, does not contain the private key, or the file is damaged, the app tells you before signing.
- With a **self-signed** certificate the signature is valid, but Adobe will show the signer's identity as unknown. For it to appear as trusted, use a certificate issued by a recognized certificate authority.
- The digital signature is placed on a single page.
- The visible signature caption uses a Latin-alphabet font: with the interface in Russian it is written in English ("Digitally signed by").

From the command line: `python main.pyw sign-cert contrato.pdf --cert firma.pfx --x 400 --y 700` (without `--x`/`--y` the signature is invisible).

### How to get a digital certificate

You need a `.pfx` or `.p12` file (it contains your private key and your identity) and the password that protects it.

**For real use (with legal validity).** Get it from a recognized certificate authority. In Colombia, for example, those accredited by ONAC: Certicámara, GSE or Andes SCD. They give you the file and its password. Certificates on a USB token or card are not yet supported by the app.

**For testing (self-signed).** You can create one for free on your own computer with PowerShell. Open PowerShell (Start menu > type *PowerShell*) and run the two commands, one at a time. Replace *Your Name* with the name you want to see in the signature; the second command will ask for the password that will protect the file.

```powershell
$cert = New-SelfSignedCertificate -Type Custom -Subject "CN=Your Name, C=CO" -KeyUsage DigitalSignature, NonRepudiation -KeyAlgorithm RSA -KeyLength 2048 -TextExtension @("2.5.29.37={text}1.3.6.1.4.1.311.10.3.12") -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(1)
```

```powershell
Export-PfxCertificate -Cert $cert -FilePath "$HOME\Documents\firma_prueba.pfx" -Password (Read-Host -AsSecureString "Certificate password")
```

The file ends up in **Documents\firma_prueba.pfx**, ready to choose in **Digital certificate**. You can select the commands in this window and copy them with **Ctrl+C**, or use the **Copy** button on each block.

The certificate is also stored in Windows (Certificate Manager: `certmgr.msc` > Personal > Certificates). If you do not need it there, you can delete it; the `.pfx` file keeps working.

### Verify a digital signature

In the app: open the signed PDF in the **Viewer** and choose the **Signatures** panel (see **Digital signatures in the Viewer**).

In Adobe Acrobat Reader (free):

1. Open the signed PDF.
2. Open the **Signatures panel** (top bar: *Signed and all signatures are valid* or the pen icon).
3. Check the signer, the date, and that the document was not modified after signing.

With a self-signed certificate, Acrobat will say that the **signer's identity is unknown**: the signature is valid, but nobody vouches for the identity. For your tests you can trust it manually: in the signatures panel, right-click the signature > *Show Signature Properties* > *Show Signer's Certificate* > *Trust* tab > *Add to Trusted Certificates*.

## Protect

- **Protect with password**: generates an encrypted copy (AES-256). Type and confirm the password (minimum 4 characters).
- **Remove password**: generates an unprotected copy, as long as you know the current password.

When you select a PDF, the app detects whether it is protected and chooses the right action.

## Tools

Choose the source **PDF** and, at the top, the tool: **Compress**, **Split**, **Number pages** or **Watermark**. Each one generates a new file (Split, several in a folder) and the original is never modified. If the PDF is protected, its password is requested and the result keeps the same password (AES-256).

- **Compress**: reduces the size, ideal for sending by email. Choose the **Level**:
  - **Low (no quality loss)**: removes unused data and compresses the content.
  - **Medium (recommended)**: also lowers the resolution of large images.
  - **High (lighter images)**: reduces images even further.

  When finished, the size before and after is shown. If the result is not lighter (for example, because the images were already compressed), an identical copy of the original is saved instead of a heavier file.
- **Split**: creates several files in the **Folder** you choose. In **How to split**:
  - **By ranges**: groups separated by semicolons, for example `1-3; 4-6; 7-` (one file per group).
  - **Every N pages**: the number of pages in each file, for example `2`.
  - **By bookmarks**: one file for each top-level bookmark in the document (chapters); the file name includes the bookmark's name.
- **Number pages**: writes the number on each page.
  - **Format**: `{n}` is the number and `{total}` the total, for example `Page {n} of {total}` or just `{n}`.
  - **Position**: top or bottom, left, center or right (6 positions).
  - **Start at**: the first number.
  - **Pages**: leave the field empty to number all of them, or type a selection as in Extract (for example `3-`). Only the numbered pages count.
- **Watermark**: writes a large, semi-transparent text across the center of each page, for example CONFIDENTIAL or DRAFT. Choose the **Text**, the **Opacity**, the **Orientation** (**Diagonal**, **Landscape**, **Portrait** or **Reverse diagonal**) and whether it goes **Behind the content** (otherwise it goes in front). On the right, a **preview** of the first page shows how it will look and updates when you change any option. Long texts are shrunk to fit the page.

The **Number pages** and **Watermark** texts are written in Helvetica; if they contain other alphabets (for example Cyrillic), the Windows Arial font is used.

## Settings

Changes are saved automatically, as the notice at the top says: what you choose is saved instantly and becomes the default setting every time you open the app.

- **Mode**: System, Light or Dark (also from the sidebar).
- **Accent color**: applied on restart.
- **Interface size**.
- **Language**: Español, English or Русский. Applied on restart; the **Restart now** button does it immediately.
- **Home page** when opening the app.
- **Open the file when finished**.
- Default **Output folder**.

The window's size and position are remembered when you close it.

In **About** you will find what the app is for, what makes it stand out, how it was made and who developed it, with links to their GitHub, their LinkedIn and the source code.

In **Local data** you can turn on **Detailed logging (for debugging)**: it saves every action in more detail to `log/app.log`, useful if you need to report a problem. It applies instantly and passwords are never logged. The **View log** button opens that file.

## Privacy and security

Everything is processed on this computer; the app does not use the internet, not even when signing digitally or verifying signatures. It never tries to discover passwords: to open or unlock a protected PDF you must know its password.
