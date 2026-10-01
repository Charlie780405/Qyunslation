import { describe, expect, it } from 'vitest';
import {
  DEFAULT_VIEW_STATE,
  mergeViewQuery,
  parseViewState,
  serializeViewState,
} from '../stores/runDetail.js';

describe('parseViewState', () => {
  it('returns defaults for an empty query', () => {
    expect(parseViewState({})).toEqual(DEFAULT_VIEW_STATE);
    expect(parseViewState(undefined)).toEqual(DEFAULT_VIEW_STATE);
  });

  it('parses valid values', () => {
    expect(parseViewState({ page: '7', zoom: '1.5', obj: 'obj-9', sync: '0' })).toEqual({
      page: 7, zoom: 1.5, objectId: 'obj-9', sync: false,
    });
    expect(parseViewState({ zoom: 'fit', sync: '1' })).toMatchObject({ zoom: 'fit', sync: true });
  });

  it('falls back to defaults for invalid values', () => {
    const bad = parseViewState({ page: '-3', zoom: 'abc', obj: '', sync: 'maybe' });
    expect(bad).toEqual(DEFAULT_VIEW_STATE);
    expect(parseViewState({ page: '0' }).page).toBe(1);
    expect(parseViewState({ page: '2.5' }).page).toBe(1);
    expect(parseViewState({ page: 'NaN' }).page).toBe(1);
    expect(parseViewState({ zoom: '99' }).zoom).toBe('fit');
    expect(parseViewState({ zoom: '0.01' }).zoom).toBe('fit');
    expect(parseViewState({ obj: 'x'.repeat(500) }).objectId).toBe('');
  });

  it('uses the first value of repeated query keys', () => {
    expect(parseViewState({ page: ['4', '5'] }).page).toBe(4);
  });
});

describe('serializeViewState', () => {
  it('omits defaults', () => {
    expect(serializeViewState(DEFAULT_VIEW_STATE)).toEqual({});
  });

  it('round-trips non-default state', () => {
    const state = { page: 3, zoom: 2, objectId: 'seg:12', sync: false };
    const query = serializeViewState(state);
    expect(query).toEqual({ page: '3', zoom: '2', obj: 'seg:12', sync: '0' });
    expect(parseViewState(query)).toEqual(state);
  });

  it('sanitises invalid state instead of emitting it', () => {
    expect(serializeViewState({ page: -1, zoom: 100, objectId: '', sync: true })).toEqual({});
  });
});

describe('mergeViewQuery', () => {
  it('keeps unrelated query keys and replaces view keys', () => {
    const merged = mergeViewQuery({ page: '9', other: 'keep', obj: 'old' }, { ...DEFAULT_VIEW_STATE, page: 2 });
    expect(merged).toEqual({ other: 'keep', page: '2' });
  });
});
