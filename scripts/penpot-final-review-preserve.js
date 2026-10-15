if(penpot.currentPage.id!=='2714a049-ae7d-81a2-8008-b3966a11b139'||!storage.finalReviewBaseline)throw Error('Live desktop baseline required');
const version=await penpot.currentFile.saveVersion('Before Luna final desktop review fixes • 2026-10-11');
storage.finalReviewBackup=version.label;
return {label:version.label,createdAt:version.createdAt,isAutosave:version.isAutosave,baselineShapes:storage.finalReviewBaseline.shapes.length};
