import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
const mocks=vi.hoisted(()=>({get:vi.fn(),post:vi.fn(),state:{seed:42,pending:0}}))
vi.mock('../p0/client.js',()=>({default:{get:mocks.get,post:mocks.post},p0State:mocks.state}))
import P1AnalysisPanel from '../components/P1AnalysisPanel.vue'
const schema={state_id:'fixed',effective_data:'raw',warning:'Review assumptions',suggested_adjustment:['X'],columns:[{name:'T',suggested_kind:'numeric',levels:['0','1'],unique_count:2},{name:'Y',suggested_kind:'numeric',levels:['0','1'],unique_count:2},{name:'X',suggested_kind:'numeric',levels:[],unique_count:100}],dag:{}}
function app(){return mount(P1AnalysisPanel,{props:{graphId:1,variables:[{id:1,name:'T'},{id:2,name:'Y'},{id:3,name:'X'}],treatmentId:1,outcomeId:2,prepareGraph:async()=>true}})}
function button(w,label){return w.findAll('button').find(b=>b.text()===label)}
describe('P1 comparison review',()=>{
 beforeEach(()=>{vi.clearAllMocks();mocks.get.mockImplementation(url=>Promise.resolve({data:url.includes('schema')?schema:{runs:[]}}))})
 it('review fetch does not estimate',async()=>{const w=app();await button(w,'Review current data and graph').trigger('click');await flushPromises();expect(mocks.post).not.toHaveBeenCalled();expect(button(w,'Run reviewed comparison').attributes('disabled')).toBeDefined()})
 it('binary event is not inferred silently',async()=>{const w=app();await button(w,'Review current data and graph').trigger('click');await flushPromises();const label=w.findAll('label').find(l=>l.text().startsWith('Event coded as 1'));expect(label.find('select').element.value).toBe('')})
 it('sends explicit reviewed comparison',async()=>{const w=app();await button(w,'Review current data and graph').trigger('click');await flushPromises();const event=w.findAll('label').find(l=>l.text().startsWith('Event coded as 1'));await event.find('select').setValue('1');const checkboxes=w.findAll('fieldset').at(-1).findAll('input[type=checkbox]');for(const cb of checkboxes)await cb.setValue(true);mocks.post.mockRejectedValue(new Error('test stop'));await button(w,'Run reviewed comparison').trigger('click');await flushPromises();const payload=mocks.post.mock.calls[0][1];expect(payload.state_id).toBe('fixed');expect(payload.specification.control_value).toBe('0');expect(payload.specification.event_value).toBe('1');expect(payload.specification.reviewed).toBe(true)})
})
