import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import StageTimeline from '../components/StageTimeline.vue';

function stageStates(wrapper) {
  return Object.fromEntries(
    wrapper.findAll('li').map((li) => [li.attributes('data-stage'), li.attributes('data-state')]),
  );
}

describe('StageTimeline', () => {
  it('renders every stage as pending when the server sent no events', () => {
    const wrapper = mount(StageTimeline, { props: { events: [] } });
    const states = stageStates(wrapper);
    expect(Object.keys(states)).toHaveLength(9);
    expect(new Set(Object.values(states))).toEqual(new Set(['pending']));
    expect(wrapper.findAll('.is-complete')).toHaveLength(0);
  });

  it('shows server event states and keeps stages without events pending', () => {
    const wrapper = mount(StageTimeline, {
      props: {
        events: [
          { stage: 'validation', state: 'completed', message: '预检完成' },
          { stage: 'structure', state: 'running', message: '解析中' },
        ],
      },
    });
    const states = stageStates(wrapper);
    expect(states.validation).toBe('completed');
    expect(states.structure).toBe('running');
    expect(states.text).toBe('pending');
    expect(states.export).toBe('pending');
    expect(wrapper.find('[data-stage="validation"]').text()).toContain('预检完成');
    expect(wrapper.find('[data-stage="text"]').text()).toContain('pending');
    expect(wrapper.findAll('.is-complete')).toHaveLength(1);
  });

  it('never marks a stage completed from currentStage alone', () => {
    const wrapper = mount(StageTimeline, { props: { events: [], currentStage: 'layout' } });
    const states = stageStates(wrapper);
    expect(states.layout).toBe('running');
    expect(states.validation).toBe('pending');
    expect(wrapper.findAll('.is-complete')).toHaveLength(0);
  });
});
