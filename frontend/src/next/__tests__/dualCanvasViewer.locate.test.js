import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { defineComponent, h } from 'vue';

vi.mock('../api.js', () => ({
  api: { previewUrl: (id, side) => `/api/v1/translation-runs/${id}/preview/${side}` },
}));

const PAGES = { source: 5, translated: 5 };
vi.mock('../lib/pdfjs.js', () => ({
  loadPdfjs: async () => ({
    getDocument: ({ data }) => ({
      promise: Promise.resolve({ numPages: data.byteLength, destroy: async () => {} }),
    }),
  }),
}));

import DualCanvasViewer from '../components/DualCanvasViewer.vue';

const calls = { source: { scroll: [], flash: [] }, translated: { scroll: [], flash: [] } };
const PaneStub = defineComponent({
  props: ['side', 'label', 'content', 'page', 'zoom', 'active'],
  setup(props, { expose }) {
    expose({
      scrollToPage: (n) => calls[props.side].scroll.push(n),
      flashPage: (n) => calls[props.side].flash.push(n),
      setScrollRatio() {},
      currentScale: 1,
    });
    return () => h('div', { 'data-pane': props.side, 'data-active': String(props.active) });
  },
});

function stubFetch(pages) {
  vi.stubGlobal('fetch', vi.fn(async (url) => {
    const side = url.endsWith('/source') ? 'source' : 'translated';
    return {
      ok: true, status: 200, headers: { get: () => 'application/pdf' },
      // numPages comes from the byte length in the pdfjs mock above.
      arrayBuffer: async () => new ArrayBuffer(pages[side]),
    };
  }));
}

function setLayout(kind) {
  const desktop = kind === 'desktop';
  const tablet = kind !== 'phone';
  window.matchMedia = (query) => ({
    matches: query.includes('1024') ? desktop : tablet,
    addEventListener() {}, removeEventListener() {},
  });
}

async function mountViewer(pages = PAGES, layout = 'desktop', props = {}) {
  stubFetch(pages);
  setLayout(layout);
  for (const side of Object.keys(calls)) { calls[side].scroll.length = 0; calls[side].flash.length = 0; }
  const wrapper = mount(DualCanvasViewer, {
    props: { runId: 'run-1', page: 1, ...props },
    attachTo: document.body,
    global: { stubs: { PdfPane: PaneStub } },
  });
  await flushPromises();
  return wrapper;
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

describe('DualCanvasViewer.focusAnchor', () => {
  it('scrolls and highlights the page even when the page did not change', async () => {
    const wrapper = await mountViewer(PAGES, 'desktop', { page: 3 });
    const scrollIntoView = vi.fn();
    wrapper.element.scrollIntoView = scrollIntoView;
    const first = await wrapper.vm.focusAnchor({ page: 3, side: 'source' });
    const second = await wrapper.vm.focusAnchor({ page: 3, side: 'source' });
    expect(first.ok).toBe(true);
    expect(second.ok).toBe(true);
    expect(scrollIntoView).toHaveBeenCalledTimes(2);
    expect(calls.source.scroll.filter((n) => n === 3).length).toBe(2);
    expect(calls.source.flash).toEqual([3, 3]);
    expect(wrapper.find('[data-locate-note]').text()).toContain('已定位到源文第 3 页');
    wrapper.unmount();
  });

  it('switches to the anchor side on tablet and phone layouts', async () => {
    for (const layout of ['tablet', 'phone']) {
      const wrapper = await mountViewer(PAGES, layout);
      await wrapper.vm.focusAnchor({ page: 2, side: 'translated' });
      await flushPromises();
      expect(wrapper.find('[data-pane="translated"]').attributes('data-active')).toBe('true');
      expect(wrapper.find('[data-pane="source"]').attributes('data-active')).toBe('false');
      expect(calls.translated.scroll).toContain(2);
      wrapper.unmount();
    }
  });

  it('refuses a page beyond the target document instead of clamping it', async () => {
    const wrapper = await mountViewer({ source: 5, translated: 3 });
    const result = await wrapper.vm.focusAnchor({ page: 4, side: 'translated' });
    expect(result).toEqual({ ok: false, reason: 'out-of-range' });
    expect(wrapper.find('[data-locate-note]').text()).toContain('超出译文页数（4 > 3）');
    expect(wrapper.emitted('update:page')).toBeUndefined();
    wrapper.unmount();
  });

  it('only scrolls the target side when page counts differ', async () => {
    const wrapper = await mountViewer({ source: 5, translated: 3 });
    await wrapper.vm.focusAnchor({ page: 2, side: 'translated' });
    expect(calls.translated.scroll).toContain(2);
    expect(calls.source.scroll).not.toContain(2);
    wrapper.unmount();
  });

  it('queues the anchor while the preview is loading and runs it when ready', async () => {
    const releases = [];
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => {
      releases.push(() => resolve({ ok: true, status: 200, headers: { get: () => 'application/pdf' }, arrayBuffer: async () => new ArrayBuffer(5) }));
    })));
    setLayout('desktop');
    const wrapper = mount(DualCanvasViewer, {
      props: { runId: 'run-1', page: 1 }, attachTo: document.body, global: { stubs: { PdfPane: PaneStub } },
    });
    const early = await wrapper.vm.focusAnchor({ page: 2, side: 'source' });
    expect(early.reason).toBe('pending');
    expect(wrapper.find('[data-locate-note]').text()).toContain('加载完成后');
    releases.forEach((fn) => fn());
    await flushPromises();
    await flushPromises();
    expect(wrapper.find('[data-locate-note]').text()).toContain('已定位到源文第 2 页');
    wrapper.unmount();
  });

  it('says so when the preview is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, headers: { get: () => '' } })));
    setLayout('desktop');
    const wrapper = mount(DualCanvasViewer, {
      props: { runId: 'run-1', page: 1 }, attachTo: document.body, global: { stubs: { PdfPane: PaneStub } },
    });
    await flushPromises();
    const result = await wrapper.vm.focusAnchor({ page: 1, side: 'translated' });
    expect(result.reason).toBe('unavailable');
    expect(wrapper.find('[data-locate-note]').text()).toContain('预览尚未加载，无法定位');
    wrapper.unmount();
  });
});
