import path from 'node:path';
import {pathToFileURL} from 'node:url';
const skill = 'C:/Users/sunlu/.codex/plugins/cache/openai-primary-runtime/presentations/26.1013.11914/skills/presentations';
const root = 'D:/ADC/output/advisor_progress_ppt169_20261016';
const {finalizePresentation} = await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const receipt = await finalizePresentation({
  workspaceDir: root,
  candidatePath: path.join(root,'exports/advisor_progress_reviewed.pptx'),
  finalPath: path.join(root,'deliverables/ADC课题阶段汇报_v1_2026-10-16.pptx'),
  pythonExecutable: 'C:/Users/sunlu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',
  integrityValidatorPath: path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath: path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs: ['--expected-slide-size-emu','12192000,6858000','--expected-slide-count','28','--validate-heading-fit','--validate-bullet-geometry'],
  fontPolicy: {basis:'design',families:['Microsoft YaHei','Arial']},
  verifyArtifactToolImport: true,
  receiptPath: path.join(root,'analysis/final_delivery_validation.json')
});
console.log(JSON.stringify(receipt,null,2));
