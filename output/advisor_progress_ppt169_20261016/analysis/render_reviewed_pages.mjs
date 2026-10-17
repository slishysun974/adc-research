import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const skill = 'C:/Users/sunlu/.codex/plugins/cache/openai-primary-runtime/presentations/26.1013.11914/skills/presentations';
const root = 'D:/ADC/output/advisor_progress_ppt169_20261016';
const {importRuntimeModule} = await import(pathToFileURL(path.join(skill,'container_tools/runtime_helpers.mjs')).href);
const {FileBlob,PresentationFile} = await importRuntimeModule('@oai/artifact-tool');
const deck = await PresentationFile.importPptx(await FileBlob.load(path.join(root,'exports/advisor_progress_reviewed.pptx')));
const pages = [2,20,24];
for (const page of pages) {
  const png = await deck.export({slide:deck.slides.items[page-1],format:'png',scale:1});
  await fs.writeFile(path.join(root,`analysis/pptx_render/slide-${page}.png`),Buffer.from(await png.arrayBuffer()));
}
console.log(JSON.stringify({rendered:pages}));
