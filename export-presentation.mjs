// Product export engine. Public npm dependency, no Codex runtime required.
import fs from "node:fs/promises";
import pptxgen from "pptxgenjs";

const [input, output] = process.argv.slice(2);
if (!input || !output)
  throw new Error("Uso: node export-presentation.mjs entrada.json salida.pptx");
const data = JSON.parse(await fs.readFile(input, "utf8"));
const p = new pptxgen();
p.layout = "LAYOUT_WIDE";
p.author = "Ala Local";
p.subject = "Programa de reservas de aeronave";
p.title = `Programa de reservas - ${data.settings.aircraft}`;
p.company = "Ala Local";
p.lang = "es-MX";
p.theme = { headFontFace: "Arial", bodyFontFace: "Arial", lang: "es-MX" };
const colors = {
  ink: "18343C",
  green: "176E60",
  muted: "526D71",
  paper: "F6F8F5",
};
function text(slide, value, x, y, w, h, size = 21, extra = {}) {
  slide.addText(String(value), {
    x,
    y,
    w,
    h,
    fontFace: "Arial",
    fontSize: size,
    color: colors.ink,
    margin: 0,
    breakLine: false,
    valign: "top",
    ...extra,
  });
}
function newSlide(title) {
  const s = p.addSlide();
  s.background = { color: colors.paper };
  text(s, "ALA LOCAL / PROGRAMA DE RESERVAS", 0.65, 0.4, 11.8, 0.35, 11, {
    color: colors.green,
    charSpacing: 1.6,
  });
  text(s, title, 0.65, 1.0, 12, 1.25, title.length > 90 ? 24 : 32, {
    bold: true,
  });
  s.addNotes(
    `Datos de la agenda local. Zona horaria: ${data.settings.timezone}. Periodo: ${data.period}.`,
  );
  return s;
}
const cover = newSlide(data.settings.aircraft);
text(cover, data.period, 0.65, 2.6, 11.9, 0.5, 25);
text(
  cover,
  `${data.items.length} ${data.items.length === 1 ? "reserva" : "reservas"} en el periodo`,
  0.65,
  3.5,
  11.9,
  0.6,
  27,
  { color: colors.green },
);
text(
  cover,
  `Zona horaria: ${data.settings.timezone}\nMargen entre usos: ${data.settings.buffer} minutos`,
  0.65,
  4.65,
  11.9,
  0.85,
  18,
  { color: colors.muted },
);
text(
  cover,
  "Resumen de agenda. La confirmación operativa del vuelo se realiza por separado.",
  0.65,
  6.4,
  11.9,
  0.55,
  13,
  { color: colors.muted },
);
for (const b of data.items) {
  const s = newSlide(b.route);
  text(s, `${b.person} / ${b.status}`, 0.65, 2.5, 12, 0.6, 24, {
    color: colors.green,
  });
  text(
    s,
    `Inicio de uso: ${b.startLabel}\nLiberación / regreso: ${b.endLabel}`,
    0.65,
    3.5,
    12,
    1.25,
    23,
    { breakLine: false },
  );
  text(s, `Zona horaria: ${data.settings.timezone}`, 0.65, 5.1, 12, 0.5, 16, {
    color: colors.muted,
  });
  // Notes are never silently truncated. Long notes receive continuation slides.
  if (b.notes) {
    const lines = b.notes
      .replace(/\r\n/g, "\n")
      .split("\n")
      .flatMap((line) => line.match(/.{1,85}/gu) || [""]);
    const chunks = [];
    for (let i = 0; i < lines.length; i += 8)
      chunks.push(lines.slice(i, i + 8).join("\n"));
    for (let i = 0; i < chunks.length; i++) {
      const n = newSlide("Notas de la reserva");
      text(n, `${b.person} / ${b.startLabel}`, 0.65, 2.45, 12, 0.6, 20, {
        color: colors.green,
      });
      text(n, chunks[i], 0.65, 3.25, 11.9, 3.45, 20);
      n.addNotes(`Reserva ${b.id}. Notas ${i + 1} de ${chunks.length}.`);
    }
  }
}
await p.writeFile({ fileName: output, compression: true });
console.log(JSON.stringify({ slides: p._slides.length, output }));
