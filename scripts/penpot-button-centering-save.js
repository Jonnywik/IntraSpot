if (penpot.currentPage.id !== '2714a049-ae7d-81a2-8008-b3966a11b139' || !storage.buttonCentering || storage.buttonCentering.cursor !== storage.buttonCentering.pairs.length) throw Error('Desktop button centering must be complete before saving');
const version = await penpot.currentFile.saveVersion('Desktop • centered button labels • 2026-10-11');
const board = penpot.currentPage.getShapeById('147a883e-91e3-8095-8008-ba58f3b6ad53');
if (board) penpot.viewport.zoomIntoView([board]);
return {label: version.label, createdAt: version.createdAt, isAutosave: version.isAutosave};
