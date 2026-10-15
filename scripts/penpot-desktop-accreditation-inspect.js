const page = (await penpotUtils.getPages()).find(p => p.name.startsWith('Desktop'));
if (!page) throw new Error('Desktop prototype page not found');
await penpot.openPage(page.id);
const boards = [...penpot.currentPage.root.children].filter(s => s.type === 'board');
const board = prefix => boards.find(b => b.name.startsWith(prefix));
const shape = (b, name) => b.children.find(s => s.name === name);
const flatten = root => [root, ...[...(root.children || [])].flatMap(flatten)];
const app = board('30 •'), rejected = board('36 •'), assessment = board('41 •'), published = board('49D •');
await penpot.waitForLayoutUpdate();
const routes = [];
for (const prefix of ['37 •','38 •','38F •','39 •','39F •']) {
  const b = board(prefix);
  for (const s of b.children) for (const i of s.interactions || []) {
    const destination = i.action?.destination || i.destination;
    if (destination?.id === b.id) routes.push({ board: b.name, shape: s.name, label: s.type === 'text' ? s.characters : undefined });
  }
}
await new Promise(resolve => setTimeout(resolve, 1200));
const appSvg = penpot.generateMarkup([app], { type: 'svg' });
const publishedSvg = penpot.generateMarkup([published], { type: 'svg' });
return {
  app: {
    title: shape(app, 'Org / title')?.characters,
    step: shape(app, 'Application / step')?.characters,
    submit: shape(app, 'Action / Submit application / label')?.characters,
    growTypes: [shape(app,'Org / title')?.growType,shape(app,'Application / step')?.growType,shape(app,'Action / Submit application / label')?.growType],
    renderChecks: Object.fromEntries(['Request organization approval','Apply for organizer accreditation','APPLICATION DETAILS','STEP 1 OF 2','Submit for review','Continue to document upload'].map(t => [t, appSvg.includes(t)])),
    staleMarkupExcerpt: appSvg.slice(Math.max(0,appSvg.indexOf('Apply for organizer accreditation')-180),appSvg.indexOf('Apply for organizer accreditation')+180),
    oldTextShapesInPage: penpot.currentPage.findShapes({type:'text'}).filter(s => /Apply for organizer accreditation|STEP 1 OF 2|Continue to document upload/.test(s.characters || '')).map(s => ({name:s.name,text:s.characters,id:s.id})),
    matchingTextShapes: flatten(app).filter(s => s.type === 'text' && /Request organization|Apply for organizer|APPLICATION DETAILS|STEP 1 OF 2|Submit for review|Continue to document upload/.test(s.characters || '')).map(s => ({name:s.name,text:s.characters,hidden:s.hidden,id:s.id}))
  },
  rejection: {
    status: shape(rejected, 'Rejected / status')?.characters,
    publishControlHidden: shape(rejected, 'Action / Rejected publish disabled')?.hidden
  },
  assessmentName: assessment.name,
  publishedSave: {
    label: shape(published, 'Action / Save published event / label')?.characters,
    growType: shape(published,'Action / Save published event / label')?.growType,
    target: shape(published, 'Action / Save published event / label')?.interactions?.[0]?.action?.destination?.name,
    renderChecks: Object.fromEntries(['Sign in to save','Save event'].map(t => [t, publishedSvg.includes(t)])),
    staleSaveExcerpt: publishedSvg.slice(Math.max(0,publishedSvg.indexOf('Save event')-180),publishedSvg.indexOf('Save event')+180),
    matchingTextShapes: flatten(published).filter(s => s.type === 'text' && /Sign in to save|Save event/.test(s.characters || '')).map(s => ({name:s.name,text:s.characters,hidden:s.hidden,id:s.id}))
  },
  selfSaveRoutes: routes
};
