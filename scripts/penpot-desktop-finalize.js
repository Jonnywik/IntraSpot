const pages=await penpotUtils.getPages();
const page=pages.find(p=>p.name.startsWith('Desktop'));
await penpot.openPage(page.id);
const boards=[...penpot.currentPage.root.children].filter(s=>s.type==='board');
const board=prefix=>boards.find(b=>b.name.startsWith(prefix));
const required=(b,name)=>{const s=b.children.find(x=>x.name===name);if(!s)throw new Error(`Missing ${b.name} / ${name}`);return s;};
const setText=(b,name,value)=>{required(b,name).characters=value;};
const hide=(b,name)=>{required(b,name).hidden=true;};
const setDestination=(shape,destination)=>{for(const interaction of [...(shape.interactions||[])])shape.removeInteraction(interaction);shape.addInteraction('click',{type:'navigate-to',destination});};
const changed=[];

const app=board('30 •'),pending=board('32 •'),draft=board('33 •'),rejected=board('36 •');
const queue=board('40 •'),review=board('41 •'),ready=board('42 •'),approve=board('43 •'),decline=board('44 •');
const feed=board('10 •'),details=board('11 •'),eligibility=board('12 •');
setText(app,'Org / title','Request organization approval');
setText(app,'Application / step','APPLICATION DETAILS');
const submitAction=app.children.find(s=>['Action / Next upload','Action / Submit application'].includes(s.name));
const submitLabel=app.children.find(s=>['Action / Next upload / label','Action / Submit application / label'].includes(s.name));
if(!submitAction||!submitLabel)throw new Error('Organization application submit action is missing');
submitLabel.characters='Submit for review';
setText(app,'Application / help body','A platform admin assesses your organization’s PLM accreditation with the academy offline. No document is needed.');
setDestination(submitAction,pending);setDestination(submitLabel,pending);
submitAction.name='Action / Submit application';
submitLabel.name='Action / Submit application / label';
changed.push('organization application');

setText(pending,'Org / subtitle','A PLM platform admin is assessing your organization’s accreditation with the academy offline.');
setText(pending,'Pending / banner body','No document upload is needed for this review.');
changed.push('pending organizer state');

const saveDraft=required(draft,'Action / Save draft'),saveDraftLabel=required(draft,'Action / Save draft / label');
setText(draft,'Action / Save draft / label','Save and return');
setDestination(saveDraft,pending);setDestination(saveDraftLabel,pending);

setText(queue,'Admin / subtitle','Assess PLM accreditation with the academy offline, then record the decision.');
setText(queue,'Queue / doc','PLM accreditation assessment · Offline review pending');
setText(queue,'Queue / note title','Offline review');
setText(queue,'Queue / note copy','Assess only the organization’s accreditation with the academy. No additional evidence is collected.');
setText(review,'Admin / subtitle','Review the application details, complete the offline assessment, then record a decision.');
setText(review,'Review / doc label','APPLICATION DETAILS');
setText(review,'Review / sample heading','Organization profile');
setText(review,'Review / sample copy','Type: Recognized student organization\nContact: Jordan Dela Cruz\nSubmitted: Sep 29, 2026');
setText(review,'Review / filename','Sample application · fictional data');
setText(review,'Review / checklist heading','Offline assessment');
setText(review,'Review / offline label','Assess accreditation only');
setText(review,'Review / offline hint','Check the organization’s PLM accreditation with the academy offline. No document is uploaded or reviewed here.');
setText(review,'Review / gate','Record outcome, admin, and date/time.');
setText(review,'Action / Continue decision / label','Continue to decision');
for(const name of ['Review / online checkbox','Review / online label','Review / online hint','Review / offline checkbox'])hide(review,name);
const assessmentLabel=required(review,'Review / offline label'),assessmentHint=required(review,'Review / offline hint');
assessmentLabel.x=review.x+1008;assessmentLabel.y=review.y+366;
assessmentHint.x=review.x+1008;assessmentHint.y=review.y+403;
changed.push('admin offline assessment');

setText(ready,'Admin / title','Ready to record decision');
setText(ready,'Admin / subtitle','The offline assessment is complete in this sample flow.');
setText(ready,'Decision / check','✓  Offline assessment complete · Sample');
setText(ready,'Decision / check two','Decision record includes outcome, admin, and date/time');
setText(ready,'Decision / evidence','Review basis: organization accreditation with the academy');
setText(ready,'Decision / caution','Choose Approved or Not approved to preview the recorded status.');
setText(ready,'Decision / simulation','Sample workflow · no real decision or timestamp is saved.');
setText(approve,'Approve / impact','Confirming enables publishing for PLM Culture & Arts. The decision record includes the admin and date/time.');
setText(decline,'Reject / impact','The organizer sees the decision status only. No reason is shown; publishing remains disabled.');

setText(rejected,'Org / title','Accreditation decision');
setText(rejected,'Org / subtitle','PLM Culture & Arts');
for(const s of rejected.children){if(/^(Rejected \/ (body|no reason|footer|why|disabled)|Action \/ Edit rejected draft)/.test(s.name||''))s.hidden=true;}
changed.push('decision and status screens');

for(const name of ['31 •','31P •','31R •']){const old=board(name);if(old){old.name=`ARCHIVE • ${old.name}`;old.hidden=true;}}
const component=penpot.library.local.components.find(c=>c.name==='Accreditation Upload');
if(component){const main=component.mainInstance();component.name='Accreditation status';main.name='Field / Accreditation status';const field=main.children.find(s=>s.name==='Upload / field');if(field)field.name='Status / surface';const primary=main.children.find(s=>s.name==='Upload / field text');if(primary){primary.name='Status / primary label';primary.characters='◷  Accreditation review pending';}const secondary=main.children.find(s=>s.name==='Upload / actions');if(secondary){secondary.name='Status / supporting copy';secondary.characters='Drafts available  ·  Publishing disabled';}}
const components=board('01 •');
setText(components,'Upload / heading','05  Accreditation status');
setText(components,'Upload / note','Organization application · simulated offline assessment');
changed.push('reusable accreditation status component');

for(const b of [feed,details])for(const s of b.children){if(/^Event art \/ /.test(s.name||'')&&s.name!=='Event art / sky')s.hidden=true;}
const saveEvent=required(details,'Action / Save event'),saveEventLabel=required(details,'Action / Save event / label');
setText(details,'Action / Save event / label','Sign in to save');
setDestination(saveEvent,eligibility);setDestination(saveEventLabel,eligibility);
changed.push('event photography and member-action path');

const approvedWorkspace=board('34 •'),publishedDetails=board('49D •'),flashPreview=board('39FP •'),assessment=board('41 •');
for(const prefix of ['37 •','38 •','38F •','39 •','39F •']){
  const current=board(prefix);
  for(const shape of current.children){
    const label=shape.type==='text'?shape.characters:shape.name;
    if(/save.*draft|save.*venue/i.test(label||'')&&(shape.interactions||[]).some(i=>(i.action?.destination?.id||i.destination?.id)===current.id))setDestination(shape,approvedWorkspace);
  }
}
for(const shape of publishedDetails.children){
  if(/^Action \/ Save published event(?: \/ label)?$/.test(shape.name||''))setDestination(shape,eligibility);
}
setText(publishedDetails,'Action / Save published event / label','Sign in to save');
for(const shape of flashPreview.children){
  if((shape.interactions||[]).some(i=>(i.action?.destination?.name||i.destination?.name)==='38F • Organizer / Flash essentials'))setDestination(shape,board('39F •'));
}
assessment.name='41 • Admin / Offline accreditation assessment';
hide(rejected,'Action / Rejected publish disabled');
changed.push('save routes, assessment naming, and rejection-state cleanup');

await penpot.waitForLayoutUpdate();
const appMarkup=penpot.generateMarkup([app],{type:'svg'}),publishedMarkup=penpot.generateMarkup([publishedDetails],{type:'svg'});
return {page:page.name,updated:changed,archived:boards.filter(b=>b.hidden&&b.name.startsWith('ARCHIVE')).map(b=>b.name),component:component?.name,saveEventTarget:eligibility.name,draftReturnTarget:pending.name,renderedCopy:{application:appMarkup.includes('Request organization approval')&&appMarkup.includes('Submit for review'),publishedSave:publishedMarkup.includes('Sign in to save')}};
