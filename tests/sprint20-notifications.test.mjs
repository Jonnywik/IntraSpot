import assert from 'node:assert/strict';
import test from 'node:test';
import {notificationCategory, notificationDestination} from '../Code/Frontend/features/notifications/inbox.ts';

test('ownership notices use clubs and current role rather than historical creator authority', () => {
  const base = {id:'notice',org_id:'club-id',event_id:null,message:'Transfer notice',created_at:'2026-10-23T00:00:00Z',read_at:null};
  const staff = {grants:[{org_id:'club-id',role:'owner'}]};
  const formerOwner = {grants:[{org_id:'club-id',role:'member'}]};
  for (const action of ['requested','accepted','declined','revoked','expired']) {
    const kind = `ownership_transfer_${action}`;
    assert.equal(notificationCategory(kind), 'clubs');
    assert.deepEqual(notificationDestination({...base,kind},staff),{
      href:'/workspace?orgId=club-id',label:'Open organization workspace',
    });
    assert.deepEqual(notificationDestination({...base,kind},formerOwner),{
      href:'/organizations?orgId=club-id',label:'View club',
    });
    assert.equal(notificationDestination({...base,org_id:null,kind},staff),null);
  }
});
