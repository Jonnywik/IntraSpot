const state=storage.finalReviewCheck,detail=storage.finalReviewDetails;
if(penpot.currentPage.id!=='2714a049-ae7d-81a2-8008-b3966a11b139'||state?.cursor!==storage.finalReviewBaseline?.shapes.length||!detail)throw Error('Completed desktop verification required');
if(state.missing.length||state.unexpectedRoutes.length||state.overflow.length||state.invalidGeometry.length||detail.buttonFailures.length||detail.specimenFailures.length||detail.disabledActions.length||detail.headingFooterClearance<8||!detail.helperFitsTwoLines)throw Error('Verification failures must be resolved before saving');
const target='cbf1253a-7ae6-80fe-8008-b57f6f1ab24c',by=id=>penpot.currentPage.getShapeById(id);
const routeIds=(storage.finalReviewEditsB||[]).filter(e=>e.change==='Resume existing scheduled draft instead of creating another').map(e=>e.id);
const incorrectDraftRoutes=routeIds.filter(id=>!by(id).interactions.some(i=>i.trigger==='click'&&i.action.destination?.id===target));
if(incorrectDraftRoutes.length)throw Error('Incorrect draft resume destination');
const captionFaces=['ec34fcb8-3872-805c-8008-b571b9b83af4','ec34fcb8-3872-805c-8008-b571b9e3a5af','ec34fcb8-3872-805c-8008-b571ba14beb4','ec34fcb8-3872-805c-8008-b571ba44c802'];
if(storage.finalReviewCaptions?.length!==4)throw Error('Four component-state captions required');
for(let i=0;i<4;i++){const c=by(storage.finalReviewCaptions[i].id),f=by(captionFaces[i]);if(c.align!=='center'||Math.abs(c.x+c.width/2-f.x-f.width/2)>.1)throw Error('Component-state caption alignment failed');}
const version=await penpot.currentFile.saveVersion('Desktop • Luna reviewed and refined • 2026-10-11');
penpot.viewport.zoomIntoView([by('147a883e-91e3-8095-8008-ba58f3b6ad53')]);
return {label:version.label,createdAt:version.createdAt,isAutosave:version.isAutosave,journeyBoards:71,buttonLabelsChecked:detail.buttonLabelsChecked,authorizedDraftRouteChanges:routeIds.length,unexpectedRouteChanges:0,captionAlignment:'pass',presentationTesting:'Not performed: heuristic review and exported-image verification only'};
