import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import TermReviewPanel from '../components/TermReviewPanel.vue';

// Every occurrence of a term is listed, each with the complete sentence around it.

const occurrence = (id, sentence, extra = {}) => {
  const start = sentence.toLowerCase().indexOf('subgroup analyses');
  return {
    id, page_no: 1, sentence, source_context: `Before. ${sentence} After.`,
    match_start: start, match_end: start + 'subgroup analyses'.length, ...extra,
  };
};

const TERM = (extra = {}) => ({
  id: 't1', source_term: 'subgroup analyses', observed_target: '', suggested_target: 'Subgroup Analyses', confirmed_target: null,
  term_type: 'general', risk: 'normal', status: 'pending', version: 1, occurrence_count: 4,
  source_context: 'Jiangsu proposed adding relevant primary analysis subgroup analyses for the primary',
  extraction_reason: 'deterministic:phrase',
  occurrences: [
    occurrence('o1', 'Jiangsu proposed adding relevant primary analysis subgroup analyses for the primary endpoint (e.g. age, sex).', { page_no: 2 }),
    occurrence('o2', 'Were subgroup analyses pre-specified?', { page_no: 3 }),
    occurrence('o3', 'The subgroup analyses were repeated in part 2.'),
    occurrence('o4', 'Results of the subgroup analyses are summarized in Table 4.', { truncated: true }),
  ],
  ...extra,
});

const mountPanel = (item) => mount(TermReviewPanel, { props: { items: [item], total: 1, unresolved: 1 } });

describe('term evidence', () => {
  it('lists all four occurrences, each with its complete sentence', () => {
    const wrapper = mountPanel(TERM());
    const rows = wrapper.findAll('[data-term-evidence-item]');
    expect(rows).toHaveLength(4);
    expect(wrapper.find('summary').text()).toContain('4 处');
    expect(rows[0].find('[data-term-sentence]').text()).toContain(
      'Jiangsu proposed adding relevant primary analysis subgroup analyses for the primary endpoint (e.g. age, sex).',
    );
    expect(rows[1].find('[data-term-sentence]').text()).toContain('Were subgroup analyses pre-specified?');
    expect(rows[0].text()).toContain('第 1 处');
    expect(rows[0].text()).toContain('第 2 页');
    expect(rows[3].text()).toContain('第 4 处');
  });

  it('highlights the term in each sentence and starts expanded', () => {
    const wrapper = mountPanel(TERM());
    const marks = wrapper.findAll('[data-term-evidence-item] mark');
    expect(marks).toHaveLength(4);
    expect(marks.every((mark) => mark.text().toLowerCase() === 'subgroup analyses')).toBe(true);
    expect(wrapper.find('details[data-term-evidence]').attributes('open')).toBeDefined();
  });

  it('flags a sentence whose stored context was cut off', () => {
    const wrapper = mountPanel(TERM());
    const rows = wrapper.findAll('[data-term-evidence-item]');
    expect(rows[3].text()).toContain('可能不完整');
    expect(rows[0].text()).not.toContain('可能不完整');
  });

  it('falls back to the single stored context when the server sends no occurrences', () => {
    const wrapper = mountPanel(TERM({ occurrences: undefined, occurrence_count: 1 }));
    const rows = wrapper.findAll('[data-term-evidence-item]');
    expect(rows).toHaveLength(1);
    expect(rows[0].text()).toContain('Jiangsu proposed adding relevant primary analysis subgroup analyses for the primary');
    expect(wrapper.find('summary').text()).toContain('1 处');
  });

  it('shows the plain sentence when the term cannot be located inside it', () => {
    const item = TERM({ occurrences: [{ id: 'o1', sentence: 'A normalised variant appears here.', match_start: null, match_end: null }], occurrence_count: 1 });
    const wrapper = mountPanel(item);
    expect(wrapper.find('[data-term-sentence]').text()).toContain('A normalised variant appears here.');
    expect(wrapper.findAll('mark')).toHaveLength(0);
  });
});
