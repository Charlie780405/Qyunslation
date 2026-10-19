// PLAN-078f f3: stage events are append-only and numbered, so after the first read only the new ones are
// fetched (`after_sequence`). A different task, or a new generation (its numbering starts again), starts over.

export function createEventTail(fetchEvents) {
  let runId = '';
  let generation = null;
  let lastSequence = 0;
  let items = [];

  function reset(nextRunId) {
    runId = nextRunId;
    generation = null;
    lastSequence = 0;
    items = [];
  }

  async function pull(nextRunId) {
    if (!nextRunId) {
      reset('');
      return items;
    }
    if (nextRunId !== runId) reset(nextRunId);
    let response = await fetchEvents(nextRunId, { after_sequence: lastSequence });
    if (generation !== null && response.generation !== undefined && response.generation !== generation) {
      reset(nextRunId);
      response = await fetchEvents(nextRunId, { after_sequence: 0 });
    }
    generation = response.generation ?? generation ?? 0;
    const fresh = (response.items || []).filter((event) => event.sequence > lastSequence);
    if (fresh.length) {
      items = [...items, ...fresh];
      lastSequence = Math.max(lastSequence, ...fresh.map((event) => event.sequence));
    }
    return items;
  }

  return { pull, reset: () => reset(''), get items() { return items; } };
}
