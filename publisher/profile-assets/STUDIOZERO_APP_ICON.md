# StudioZero app icon

Created for StudioZero on 2026-11-13 using the built-in image-generation tool, without reference images. This is StudioZero brand artwork, excluded from the source-code MIT licence by `LICENSE`.

`studiozero-app-icon.png` is the original 1254 × 1254 opaque image. The teal ribbon forms a zero around an ivory play symbol on charcoal, matching the private studio's existing palette. The mark stays inside the centered maskable safe circle.

The production derivatives live in `publisher/ui/public/`: `icons/studiozero-{16,32,64,192,512,1024}.png`, `icons/studiozero-maskable-512.png`, `apple-touch-icon.png` (180 × 180), and `favicon.ico` (16, 32, 48, 64 and 256 pixel PNG frames). These are resized copies of the original; the maskable copy retains the full opaque background. The existing static build copies them to `publisher/app/static/`.

No external image, font or stock-media licence is required for these generated assets. The public-safety scanner allows only the named production PNG derivatives, alongside its existing own-brand artwork folder.

## Generation prompt

Use case: logo-brand. Create one finished high-quality square app icon for StudioZero, a private creative video studio for making, reviewing and publishing short films. Output only the icon artwork, no mockup or presentation sheet.

Visual idea: a sculptural, continuous ribbon forming a bold vertically rounded zero / camera aperture, surrounding a crisp right-pointing play triangle. Distinctive and disciplined editorial design, simple enough to recognize at 16 pixels. The zero is the hero, not generic lettering. Refined mint-to-teal satin highlights on the ribbon, a warm ivory play triangle, deep charcoal background with an extremely subtle teal glow behind the mark. Precise geometry, restrained depth, clean beautiful edges, generous negative space; sophisticated creative-tool identity rather than a shiny game token.

Palette based on the actual StudioZero UI: charcoal #141416, deep teal #0a5c63, luminous teal #5cc4cc, warm ivory #f6f6f4. No letters, words, captions, watermark, filmstrip holes, camera hardware, tiny details, border or drop shadow outside the icon.

Composition: full-bleed opaque square background extending all the way to each edge; no pre-rounded outer corners. The entire central symbol must fit inside the central 68 percent of the canvas and inside a circle of radius 38 percent of the image width, keeping all important geometry safe for circular and squircle home-screen masks. Centered and optically balanced. The same image will be used for iPhone home screen, Android maskable icon, desktop installed app and browser favicons.
